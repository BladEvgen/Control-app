export type DepartmentNode = {
  id: string;
  parent_id: string | null;
  name: string;
  path: string;
  ancestor_ids: string[];
  has_children: boolean;
  total_staff_count: number;
};

export function activeDepartmentId(pathname: string): string {
  return decodeURIComponent(
    pathname.match(/\/(?:department|childDepartment)\/([^/]+)/i)?.[1] ?? "",
  );
}

export function navigationPath(node: DepartmentNode): string {
  return `/${node.has_children ? "department" : "childDepartment"}/${encodeURIComponent(node.id)}`;
}

const searchWords = (value: string): string[] =>
  value
    .normalize("NFKC")
    .toLocaleLowerCase("ru")
    .replace(/ё/g, "е")
    .replace(/\p{Cf}/gu, "")
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean);
export function matchesDepartmentSearch(value: string, query: string): boolean {
  const words = searchWords(value);
  return searchWords(query).every((token) =>
    words.some((word) => word.startsWith(token)),
  );
}

export function filterNavigation(
  nodes: DepartmentNode[],
  query: string,
  expanded: Set<string>,
): DepartmentNode[] {
  const tokens = searchWords(query);
  return nodes.filter((node) => {
    if (!tokens.length)
      return node.ancestor_ids.every((id) => expanded.has(id));
    const pathWords = searchWords(node.path);
    return tokens.every((token) =>
      pathWords.some((word) => word.startsWith(token)),
    );
  });
}
