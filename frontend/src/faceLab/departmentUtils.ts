export type DeptForDepth = {
  id: number;
  parent_id: number | null;
};

export function departmentDepth(
  deptId: number,
  byId: Map<number, DeptForDepth>,
): number {
  let n = 0;
  let cur: DeptForDepth | undefined = byId.get(deptId);
  const seen = new Set<number>();
  while (cur?.parent_id != null && byId.has(cur.parent_id) && !seen.has(cur.id)) {
    seen.add(cur.id);
    n += 1;
    cur = byId.get(cur.parent_id);
  }
  return n;
}

export function sortDepartmentsDeepestFirst<T extends DeptForDepth>(depts: T[]): T[] {
  const byId = new Map(depts.map((d) => [d.id, d]));
  return [...depts].sort(
    (a, b) => departmentDepth(b.id, byId) - departmentDepth(a.id, byId),
  );
}
