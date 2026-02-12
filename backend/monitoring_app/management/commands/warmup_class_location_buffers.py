from django.core.cache import caches
from django.core.management.base import BaseCommand

from monitoring_app import models, utils
from monitoring_app.lesson_locations_conf import (
    ACCEPTANCE_R_CLUSTER,
    ACCEPTANCE_R_SAME_POINT,
    ACCEPTANCE_R_STANDALONE,
    CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY,
    CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_TTL,
    CLUSTER_THRESHOLD_M,
    SAME_POINT_THRESHOLD_M,
)


class Command(BaseCommand):
    help = (
        "Прогревает кэш приёмных радиусов R_loc по ClassLocation (Redis). "
        "Запускать при деплое или после смены локаций; Celery Beat — раз в 30 мин."
    )

    def handle(self, *args, **options):
        locations = list(
            models.ClassLocation.objects.filter(
                latitude__isnull=False, longitude__isnull=False
            ).only("id", "latitude", "longitude", "acceptance_radius_m")
        )
        radii = utils.compute_class_location_acceptance_radii(
            locations,
            r_same_point=ACCEPTANCE_R_SAME_POINT,
            r_cluster=ACCEPTANCE_R_CLUSTER,
            r_standalone=ACCEPTANCE_R_STANDALONE,
            same_point_threshold=SAME_POINT_THRESHOLD_M,
            cluster_threshold=CLUSTER_THRESHOLD_M,
        )
        caches["default"].set(
            CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY,
            radii,
            CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_TTL,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Кэш приёмных радиусов обновлён: {len(radii)} локаций, TTL {CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_TTL} с"
            )
        )
