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


def _root_chain(
    node: str, by_id: Mapping[str, DepartmentRow], memo: dict[str, list[str]]
) -> list[str]:
    """Root→node ids; reuses each ancestor's cached chain, so every node is walked once.

    Broken ancestry (cycle) is cut at the first repeat and not cached.
    """
    stack: list[str] = []
    seen: set[str] = set()
    current: str | None = node
    while current is not None and current in by_id and current not in memo and current not in seen:
        seen.add(current)
        stack.append(current)
        current = by_id[current]["parent_id"]
    cyclic = current is not None and current in seen
    base = memo[current] if current is not None and not cyclic and current in memo else []
    for item in reversed(stack):
        base = base + [item]
        if not cyclic:
            memo[item] = base
    return base


def build_navigation(
    rows: Sequence[DepartmentRow], staff_counts: Mapping[str, int]
) -> list[NavigationItem]:
    """Full metadata-only tree, including empty parents; tolerate broken ancestry."""
    by_id = {row["id"]: row for row in rows}
    parents = {row["parent_id"] for row in rows}
    memo: dict[str, list[str]] = {}
    chains: dict[str, list[str]] = {}
    totals = {row["id"]: 0 for row in rows}
    for row in rows:
        chain = chains[row["id"]] = _root_chain(row["id"], by_id, memo)
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
