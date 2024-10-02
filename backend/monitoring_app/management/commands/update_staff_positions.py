from django.db import transaction
from django.core.management.base import BaseCommand
from monitoring_app.models import ChildDepartment, Staff, Position


class Command(BaseCommand):
    """
    Команда для обновления позиций всех сотрудников в указанном родительском отделе и его дочерних отделах на позицию "Сотрудник".
    """

    help = 'Обновляет позиции всех сотрудников на "Сотрудник" для заданного родительского отдела и его дочерних отделов.'

    def add_arguments(self, parser):
        """
        Добавляет аргументы для команды.

        Аргументы:
        parent_id: int - ID родительского отдела, для которого необходимо обновить позиции сотрудников.
        """
        parser.add_argument(
            'parent_id',
            type=int,
            help='ID родительского отдела, в котором и в его дочерних отделах будут обновлены позиции всех сотрудников на "Сотрудник".',
        )

    @transaction.atomic
    def handle(self, *args, **kwargs):
        """
        Основной метод команды. Выполняет обновление позиций всех сотрудников на "Сотрудник" для указанного родительского отдела.

        Аргументы:
        parent_id: int - ID родительского отдела, для которого нужно обновить позиции сотрудников.
        """
        parent_id = kwargs['parent_id']

        try:
            parent_department = ChildDepartment.objects.get(id=parent_id)
        except ChildDepartment.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'Отдел с id {parent_id} не найден. Убедитесь, что указанный ID корректен.'
                )
            )
            return

        descendant_ids = self.get_all_descendants(parent_department)

        try:
            employee_position = Position.objects.get(id=1)
        except Position.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    'Не удалось найти позицию с id 1, которая должна быть "Сотрудник". Убедитесь в правильности данных.'
                )
            )
            return

        staff_to_update = Staff.objects.filter(department__in=descendant_ids)

        updated_count = 0
        for staff in staff_to_update:
            staff.positions.clear()  
            staff.positions.add(employee_position)  
            updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Обновлено позиции у {updated_count} сотрудников в отделе {parent_department.name} и его дочерних отделах.'
            )
        )

    def get_all_descendants(self, department):
        """
        Рекурсивно находит всех потомков отдела, включая сам отдел.

        Аргументы:
        department: ChildDepartment - отдел, для которого ищутся потомки.

        Возвращает:
        list: Список ID всех дочерних отделов и самого указанного отдела.
        """
        descendants = [department.id]
        children = ChildDepartment.objects.filter(parent=department)
        for child in children:
            descendants.extend(self.get_all_descendants(child))
        return descendants
