import { z } from "zod";
import type { LocationData } from "../../schemas/IData";
import { localDate, shiftDate } from "../../utils/reportDates.ts";

const MAP_COLORS = [
  "#7254b8",
  "#277e86",
  "#b46635",
  "#3974ae",
  "#a54d75",
  "#64813d",
] as const;
export const MAP_NUMBER = new Intl.NumberFormat("ru-RU");

export type MapEntry = LocationData & { key: string; color: string };
export type MapPoint = { entry: MapEntry; x: number; y: number };
export type MapGroup = {
  entries: MapEntry[];
  x: number;
  y: number;
  visits: number;
  offset?: [number, number];
};

const locationSchema = z.object({
  name: z.string(),
  address: z.string(),
  lat: z.number().finite().min(-85).max(85),
  lng: z.number().finite().min(-180).max(180),
  employees: z.number().finite().positive(),
});

export function parseMapLocations(data: unknown): LocationData[] {
  if (!Array.isArray(data))
    throw new Error("Некорректный ответ списка локаций");
  return data.flatMap((item: unknown) => {
    const parsed = locationSchema.safeParse(item);
    return parsed.success ? [parsed.data] : [];
  });
}

export function defaultMapDate(now = new Date()): string {
  return shiftDate(localDate(now), -1);
}

export function createMapEntries(locations: LocationData[]): MapEntry[] {
  const seen = new Map<string, number>();
  return locations.map((location) => {
    const base = [
      location.name.trim().toLowerCase(),
      location.address.trim().toLowerCase(),
      location.lat.toFixed(6),
      location.lng.toFixed(6),
    ].join("|");
    const occurrence = (seen.get(base) ?? 0) + 1;
    seen.set(base, occurrence);
    let hash = 0;
    for (const char of base)
      hash = (Math.imul(hash, 31) + char.charCodeAt(0)) >>> 0;
    return {
      ...location,
      key: `${base}|${occurrence}`,
      color: MAP_COLORS[hash % MAP_COLORS.length],
    };
  });
}

export function matchesMapQuery(
  location: LocationData,
  query: string,
): boolean {
  return `${location.name} ${location.address}`
    .toLocaleLowerCase("ru")
    .includes(query.trim().toLocaleLowerCase("ru"));
}

export function groupMapPoints(
  points: MapPoint[],
  labelScale = 1,
  {
    selectedKey = null,
    spread = false,
  }: { selectedKey?: string | null; spread?: boolean } = {},
): MapGroup[] {
  const groups: MapGroup[] = points.map(({ entry, x, y }) => ({
    entries: [entry],
    x,
    y,
    visits: entry.employees,
  }));
  const labelWidth = (group: MapGroup): number =>
    Math.max(
      64,
      MAP_NUMBER.format(group.visits).length * 12 +
        (group.entries.length > 1 ? 62 : 38),
    );
  let merged = true;
  while (merged) {
    merged = false;
    for (let i = 0; i < groups.length && !merged; i++) {
      for (let j = i + 1; j < groups.length; j++) {
        const a = groups[i];
        const b = groups[j];
        if (
          Math.abs(a.x - b.x) >=
            ((labelWidth(a) + labelWidth(b)) / 2) * labelScale + 8 ||
          Math.abs(a.y - b.y) >= 58 * labelScale
        )
          continue;
        const count = a.entries.length + b.entries.length;
        a.x = (a.x * a.entries.length + b.x * b.entries.length) / count;
        a.y = (a.y * a.entries.length + b.y * b.entries.length) / count;
        a.entries.push(...b.entries);
        a.visits += b.visits;
        groups.splice(j, 1);
        merged = true;
        break;
      }
    }
  }
  if (!spread && !selectedKey) return groups;

  const positions = new Map(points.map((point) => [point.entry.key, point]));
  const atCoordinates = (entries: MapEntry[]): MapGroup => ({
    entries,
    x:
      entries.reduce((sum, entry) => sum + positions.get(entry.key)!.x, 0) /
      entries.length,
    y:
      entries.reduce((sum, entry) => sum + positions.get(entry.key)!.y, 0) /
      entries.length,
    visits: entries.reduce((sum, entry) => sum + entry.employees, 0),
  });
  const expanded = groups.flatMap((group) => {
    const selected = group.entries.find((entry) => entry.key === selectedKey);
    if (
      group.entries.length === 1 ||
      (!selected && (!spread || group.entries.length > 6))
    )
      return [group];
    if (group.entries.length > 6 && selected)
      return [
        atCoordinates([selected]),
        atCoordinates(group.entries.filter((entry) => entry !== selected)),
      ];
    return group.entries.map((entry) => atCoordinates([entry]));
  });
  expanded.sort(
    (a, b) =>
      Number(b.entries.some((e) => e.key === selectedKey)) -
      Number(a.entries.some((e) => e.key === selectedKey)),
  );
  const placed: MapGroup[] = [];
  for (const group of expanded) {
    const width = labelWidth(group) * labelScale;
    const height = 58 * labelScale;
    const overlaps = (x: number, y: number): boolean =>
      placed.some(
        (other) =>
          Math.abs(x - other.x) <
            (width + labelWidth(other) * labelScale) / 2 + 8 &&
          Math.abs(y - other.y) < height,
      );
    let x = group.x,
      y = group.y;
    if (overlaps(x, y)) {
      const candidates = placed.flatMap((other) => {
        const gap = (width + labelWidth(other) * labelScale) / 2 + 9;
        return [
          { x: other.x - gap, y },
          { x: other.x + gap, y },
          { x, y: other.y - height - 1 },
          { x, y: other.y + height + 1 },
        ];
      });
      candidates.sort(
        (a, b) =>
          (a.x - x) ** 2 + (a.y - y) ** 2 - (b.x - x) ** 2 - (b.y - y) ** 2,
      );
      const free = candidates.find((point) => !overlaps(point.x, point.y))!;
      x = free.x;
      y = free.y;
    }
    group.offset = [x - group.x, y - group.y];
    placed.push({ ...group, x, y });
  }
  return expanded;
}

export function mergeMapEntries(
  previous: MapEntry[],
  incoming: MapEntry[],
): MapEntry[] {
  const remaining = new Map(incoming.map((entry) => [entry.key, entry]));
  const merged: MapEntry[] = [];
  for (const old of previous) {
    const next = remaining.get(old.key);
    if (!next) continue;
    remaining.delete(old.key);
    merged.push(
      old.name === next.name &&
        old.address === next.address &&
        old.lat === next.lat &&
        old.lng === next.lng &&
        old.employees === next.employees
        ? old
        : next,
    );
  }
  merged.push(...remaining.values());
  return merged.length === previous.length &&
    merged.every((entry, index) => entry === previous[index])
    ? previous
    : merged;
}
