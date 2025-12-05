import datetime
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitoring_app import models
from monitoring_app.cache_conf import register_preload, warmup_cache
from monitoring_app import utils

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Прогревает кэш для популярных API endpoints (холодный и горячий кэш)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Принудительно обновить кэш (горячий кэш)",
        )
        parser.add_argument(
            "--keys",
            nargs="+",
            help="Список ключей для предзагрузки (если не указан, загружаются все)",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        keys = options.get("keys")

        self.stdout.write(
            self.style.SUCCESS(f"Начинаем прогрев кэша (force={force})...")
        )

        def get_parent_departments():
            roots = (
                models.ChildDepartment.objects.filter(parent__isnull=True)
                .order_by("id")
                .values_list("id", flat=True)
            )
            return [str(pk) for pk in roots]

        register_preload("parent_department_ids", get_parent_departments)

        def get_map_locations_today():
            today = timezone.now().date()
            locations = models.ClassLocation.objects.only(
                "address", "name", "latitude", "longitude"
            )
            result_with_employees = utils.generate_map_data(
                locations, today, search_staff_attendance=True, filter_empty=False
            )
            result_without_employees = utils.generate_map_data(
                locations, today, search_staff_attendance=False, filter_empty=True
            )
            return {
                "with_employees": result_with_employees,
                "without_employees": result_without_employees,
            }

        register_preload("map_locations_today", get_map_locations_today)

        def get_popular_departments():
            parent_ids = get_parent_departments()
            popular_ids = parent_ids[:10]

            from monitoring_app import serializers

            def calculate_staff_count(department):
                rows = list(
                    models.ChildDepartment.objects.values_list("id", "parent_id")
                )
                children_by_parent = {}
                for cid, pid in rows:
                    children_by_parent.setdefault(pid, []).append(cid)

                visited = set()
                stack = [department.id]
                subtree_ids = []

                while stack:
                    cur = stack.pop()
                    if cur in visited:
                        continue
                    visited.add(cur)
                    subtree_ids.append(cur)
                    stack.extend(children_by_parent.get(cur, []))

                total = (
                    models.Staff.objects.filter(department_id__in=subtree_ids)
                    .values("id")
                    .distinct()
                    .count()
                )
                return total

            results = {}
            for dept_id in popular_ids:
                try:
                    department = models.ChildDepartment.objects.get(id=dept_id)
                    total_staff_count = calculate_staff_count(department)
                    child_departments_data = models.ChildDepartment.objects.filter(
                        parent=department
                    )
                    child_departments_data_serialized = (
                        serializers.ChildDepartmentSerializer(
                            child_departments_data, many=True
                        ).data
                    )

                    results[dept_id] = {
                        "name": department.name,
                        "date_of_creation": department.date_of_creation,
                        "child_departments": child_departments_data_serialized,
                        "total_staff_count": total_staff_count,
                    }
                except models.ChildDepartment.DoesNotExist:
                    continue

            return results

        register_preload("popular_departments", get_popular_departments)

        def get_today_attendance_stats():
            today = timezone.now().date()
            from monitoring_app.views import StaffAttendanceStatsView

            view = StaffAttendanceStatsView()
            target_date = view.get_last_working_day(today)
            next_date = target_date + datetime.timedelta(days=1)

            return view.query_data(target_date, next_date, None)

        register_preload("today_attendance_stats", get_today_attendance_stats)

        def get_root_departments_batch():
            from monitoring_app.views import _fetch_root_departments_data

            return _fetch_root_departments_data()

        register_preload("root_departments_batch", get_root_departments_batch)

        results = warmup_cache(keys=keys, force=force)

        self.stdout.write(self.style.SUCCESS("\nРезультаты прогрева кэша:"))
        for key, result in results.items():
            if result.get("status") == "success":
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ {key}: успешно загружен в кэш")
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"  ✗ {key}: ошибка - {result.get('message', 'Unknown error')}"
                    )
                )

        success_count = sum(1 for r in results.values() if r.get("status") == "success")
        total_count = len(results)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nПрогрев завершен: {success_count}/{total_count} ключей успешно загружены"
            )
        )
