from django.db.models import Count
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from monitoring_app.models import ChildDepartment, Staff
from monitoring_app.services.department_navigation import build_navigation


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def department_navigation(request):
    """All department paths and counts; no staff records or personal data."""
    rows = list(ChildDepartment.objects.values("id", "parent_id", "name"))
    counts = {
        row["department_id"]: row["count"]
        for row in Staff.objects.filter(department_id__isnull=False)
        .values("department_id")
        .annotate(count=Count("id"))
    }
    return Response(build_navigation(rows, counts))
