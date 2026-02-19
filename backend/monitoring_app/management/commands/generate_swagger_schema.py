from django.core.management.base import BaseCommand
from django.test import RequestFactory


class Command(BaseCommand):
    help = "Генерирует схему OpenAPI (как для /swagger.json). При ошибке выводит traceback."

    def handle(self, *args, **options):
        from monitoring_app.swagger import _get_schema_view

        request_factory = RequestFactory()
        request = request_factory.get("/swagger.json/")
        request.user = None

        schema_view = _get_schema_view()
        without_ui = schema_view.without_ui()

        try:
            response = without_ui(request, format=".json")
            if hasattr(response, "render") and not getattr(response, "_is_rendered", True):
                response.render()
            self.stdout.write(
                self.style.SUCCESS(
                    f"OK: status={response.status_code}, "
                    f"content_type={getattr(response, 'content_type', 'N/A')}"
                )
            )
            if response.status_code == 200:
                content = getattr(response, "content", None)
                if content is not None:
                    self.stdout.write(f"Длина тела: {len(content)} байт")
        except Exception as e:
            import traceback

            self.stdout.write(self.style.ERROR(f"Ошибка генерации схемы: {e}"))
            self.stdout.write(traceback.format_exc())
            raise
