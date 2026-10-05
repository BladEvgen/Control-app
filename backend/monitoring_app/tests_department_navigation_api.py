from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from rest_framework.test import APIRequestFactory, force_authenticate

from monitoring_app.department_navigation_api import department_navigation


class DepartmentNavigationApiTests(TestCase):
    def test_anonymous_request_is_rejected_without_loading_structure(self):
        with patch("monitoring_app.department_navigation_api.ChildDepartment.objects.values") as rows:
            response = department_navigation(APIRequestFactory().get("/api/departments/navigation/"))
        self.assertIn(response.status_code, (401, 403))
        rows.assert_not_called()

    def test_authenticated_response_contains_metadata_only(self):
        request = APIRequestFactory().get("/api/departments/navigation/")
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        with (
            patch("monitoring_app.department_navigation_api.ChildDepartment.objects.values", return_value=[
                {"id": "001", "parent_id": None, "name": "Студенты"},
                {"id": "OM-01", "parent_id": "001", "name": "ОМ"},
            ]),
            patch("monitoring_app.department_navigation_api.Staff.objects.filter") as staff,
        ):
            staff.return_value.values.return_value.annotate.return_value = [{"department_id": "OM-01", "count": 12000}]
            response = department_navigation(request)
        self.assertEqual(response.status_code, 200)
        by_id = {item["id"]: item for item in response.data}
        self.assertEqual(by_id["OM-01"]["path"], "Студенты → ОМ")
        self.assertEqual(by_id["001"]["total_staff_count"], 12000)
        self.assertEqual(set(by_id["OM-01"]), {
            "id", "parent_id", "name", "path", "ancestor_ids", "has_children", "direct_staff_count", "total_staff_count",
        })
