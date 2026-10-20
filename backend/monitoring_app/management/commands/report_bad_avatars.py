from django.core.management.base import BaseCommand

from monitoring_app import ml, models
from monitoring_app.face_bootstrap_quality import avatar_rejection


class Command(BaseCommand):
    help = "CSV (pin;ФИО;причины;сообщение) аватаров без одного лица, снятого прямо: их нужно перезалить."

    def add_arguments(self, parser):
        parser.add_argument("--pins", nargs="*", help="Проверить только эти PIN.")

    def handle(self, *args, **opts):
        qs = models.Staff.objects.exclude(avatar="").exclude(avatar__isnull=True).order_by("pin")
        if opts["pins"]:
            qs = qs.filter(pin__in=opts["pins"])
        bad = 0
        self.stdout.write("pin;fio;reason_codes;message")
        for staff in qs.iterator(chunk_size=200):
            image = ml.imread_bgr(staff.avatar.path)
            if image is None:
                rejection = {"reason_codes": ["unreadable"], "message": "Файл не читается."}
            else:
                rejection = avatar_rejection(ml.preprocess_image(image))
            if rejection:
                bad += 1
                codes = ",".join(rejection["reason_codes"])
                fio = f"{staff.surname} {staff.name}"
                self.stdout.write(f"{staff.pin};{fio};{codes};{rejection['message']}")
        self.stderr.write(f"плохих аватаров: {bad} из {qs.count()}")
