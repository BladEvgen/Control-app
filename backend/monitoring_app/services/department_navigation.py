from collections.abc import Mapping, Sequence
from typing import TypedDict


class DepartmentRow(TypedDict):
    id: str
    parent_id: str | None
    name: str


class NavigationItem(DepartmentRow):
    path: str
    ancestor_ids: list[str]
    has_children: bool
    direct_staff_count: int
    total_staff_count: int


def build_navigation(
    rows: Sequence[DepartmentRow], staff_counts: Mapping[str, int]
) -> list[NavigationItem]:
    """Full metadata-only tree, including empty parents; tolerate broken ancestry."""
    by_id = {row["id"]: row for row in rows}
    parents = {row["parent_id"] for row in rows}
    chains: dict[str, list[str]] = {}
    totals = {row["id"]: 0 for row in rows}
    # ponytail: O(nodes * depth); cache ancestor paths if the hierarchy grows very deep.
    for row in rows:
        chain: list[str] = []
        seen: set[str] = set()
        current = row["id"]
        while current in by_id and current not in seen:
            seen.add(current)
            chain.append(current)
            parent_id = by_id[current]["parent_id"]
            if parent_id is None:
                break
            current = parent_id
        chains[row["id"]] = list(reversed(chain))
        count = staff_counts.get(row["id"], 0)
        for ancestor in chain:
            totals[ancestor] += count

    result: list[NavigationItem] = []
    for row in rows:
        chain = chains[row["id"]]
        result.append(
            {
                **row,
                "path": " → ".join(by_id[item]["name"] for item in chain),
                "ancestor_ids": chain[:-1],
                "has_children": row["id"] in parents,
                "direct_staff_count": staff_counts.get(row["id"], 0),
                "total_staff_count": totals[row["id"]],
            }
        )
    return sorted(result, key=lambda item: (item["path"].casefold(), item["id"]))
