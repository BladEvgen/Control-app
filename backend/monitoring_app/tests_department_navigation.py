import unittest

from monitoring_app.services import department_navigation


class DepartmentNavigationTests(unittest.TestCase):
    def test_full_path_and_subtree_counts_include_empty_parents(self):
        rows = [
            {"id": "1", "parent_id": None, "name": "Университет"},
            {"id": "2", "parent_id": "1", "name": "Студенты"},
            {"id": "3", "parent_id": "2", "name": "ОМ"},
            {"id": "4", "parent_id": "1", "name": "Другой отдел"},
        ]
        result = department_navigation.build_navigation(rows, {"3": 12000, "4": 2})
        by_id = {item["id"]: item for item in result}
        self.assertEqual(by_id["3"]["path"], "Университет → Студенты → ОМ")
        self.assertEqual(by_id["2"]["total_staff_count"], 12000)
        self.assertEqual(by_id["1"]["total_staff_count"], 12002)
        self.assertTrue(by_id["2"]["has_children"])
        self.assertFalse(by_id["3"]["has_children"])
        self.assertEqual(by_id["3"]["ancestor_ids"], ["1", "2"])

    def test_empty_structure_and_departments_without_people_are_retained(self):
        self.assertEqual(department_navigation.build_navigation([], {}), [])
        result = department_navigation.build_navigation(
            [{"id": "5", "parent_id": None, "name": "Пустой отдел"}], {}
        )
        self.assertEqual(result[0]["total_staff_count"], 0)

    def test_cycle_and_missing_parent_terminate(self):
        result = department_navigation.build_navigation(
            [
                {"id": "1", "parent_id": "2", "name": "A"},
                {"id": "2", "parent_id": "1", "name": "B"},
                {"id": "3", "parent_id": "99", "name": "C"},
            ],
            {"1": 4},
        )
        self.assertEqual(len(result), 3)
        self.assertTrue(all(item["id"] not in item["ancestor_ids"] for item in result))
        self.assertEqual(next(item for item in result if item["id"] == "1")["total_staff_count"], 4)


if __name__ == "__main__":
    unittest.main()
