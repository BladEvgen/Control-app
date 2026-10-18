from typing import cast

from django.db.models import Count
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from monitoring_app.models import ChildDepartment, Staff
from monitoring_app.services.department_navigation import DepartmentRow, build_navigation


_ITEM = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        "id": openapi.Schema(type=openapi.TYPE_STRING),
        "parent_id": openapi.Schema(type=openapi.TYPE_STRING, x_nullable=True),
        "name": openapi.Schema(type=openapi.TYPE_STRING),
        "path": openapi.Schema(type=openapi.TYPE_STRING, description="Корень → … → отдел"),
        "ancestor_ids": openapi.Schema(
            type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING)
        ),
        "has_children": openapi.Schema(type=openapi.TYPE_BOOLEAN),
        "direct_staff_count": openapi.Schema(type=openapi.TYPE_INTEGER),
        "total_staff_count": openapi.Schema(
            type=openapi.TYPE_INTEGER, description="С учётом всех дочерних отделов"
        ),
    },
)


@swagger_auto_schema(
    method="get",
    operation_summary="Дерево отделов для навигации",
    operation_description="Все отделы с путём от корня и числом сотрудников, отсортировано по пути. "
    "Персональных данных нет.",
    tags=["Departments"],
    responses={200: openapi.Schema(type=openapi.TYPE_ARRAY, items=_ITEM)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def department_navigation(request):
    """All department paths and counts; no staff records or personal data."""
    rows = cast(
        list[DepartmentRow], list(ChildDepartment.objects.values("id", "parent_id", "name"))
    )
    counts = {
        row["department_id"]: row["count"]
        for row in Staff.objects.filter(department_id__isnull=False)
        .values("department_id")
        .annotate(count=Count("id"))
    }
    return Response(build_navigation(rows, counts))
