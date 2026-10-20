import test from "node:test";
import assert from "node:assert/strict";
import {
  MAP_NUMBER,
  mergeMapEntries,
  createMapEntries,
  defaultMapDate,
  groupMapPoints,
  parseMapLocations,
  matchesMapQuery,
} from "../../src/components/map/mapModel.ts";

const location = {
  name: "Корпус",
  address: "Улица 1",
  lat: 43.24,
  lng: 76.93,
  employees: 12,
};

test("default report date uses Almaty yesterday at month and year boundaries", () => {
  assert.equal(defaultMapDate(new Date("2025-12-31T20:00:00Z")), "2025-12-31");
  assert.equal(defaultMapDate(new Date("2026-03-01T18:00:00Z")), "2026-02-28");
});
test("reject invalid response and discard unusable map coordinates and zero attendance", () => {
  assert.throws(() => parseMapLocations({ results: [] }));
  assert.deepEqual(
    parseMapLocations([
      location,
      { ...location, lat: 91 },
      { ...location, lng: NaN },
      { ...location, employees: 0 },
      { ...location, employees: "12" },
    ]),
    [location],
  );
});
test("location identity and color survive refresh reorder and attendance changes", () => {
  const other = { ...location, name: "Клиника", lng: 76.95 };
  const before = createMapEntries([location, other]);
  const after = createMapEntries([other, { ...location, employees: 50 }]);
  assert.equal(before[0].key, after[1].key);
  assert.equal(before[0].color, after[1].color);
  assert.equal(
    new Set(createMapEntries([location, location]).map((e) => e.key)).size,
    2,
  );
});
test("screen groups partition all locations and preserve attendance totals", () => {
  const entries = createMapEntries([
    location,
    { ...location, name: "Рядом" },
    { ...location, name: "Далеко" },
  ]);
  const points = entries.map((entry, i) => ({
    entry,
    x: i === 2 ? 200 : i * 12,
    y: 10,
  }));
  const groups = groupMapPoints(points);
  assert.deepEqual(
    groups.map((g) => g.entries.length),
    [2, 1],
  );
  assert.equal(groups.flatMap((g) => g.entries).length, 3);
  assert.equal(
    groups.reduce((n, g) => n + g.visits, 0),
    36,
  );
  assert.deepEqual(groupMapPoints([]), []);
});
test("search matches name and address without case or surrounding spaces", () => {
  assert.equal(matchesMapQuery(location, "  кОрПус "), true);
  assert.equal(matchesMapQuery(location, "улица 1"), true);
  assert.equal(matchesMapQuery(location, "нет"), false);
});

test("groups account for label width, not only distance between geographic points", () => {
  const entries = createMapEntries([location, { ...location, name: "Вторая" }]);
  assert.equal(
    groupMapPoints(entries.map((entry, i) => ({ entry, x: i * 70, y: 0 })))
      .length,
    1,
  );
  const combined = groupMapPoints(
    Array.from({ length: 64 }, (_, i) => ({
      entry: { ...entries[0], key: String(i) },
      x: (i % 8) * 20,
      y: Math.floor(i / 8) * 20,
    })),
  );
  assert.equal(combined.flatMap((g) => g.entries).length, 64);
  for (let i = 0; i < combined.length; i++)
    for (let j = i + 1; j < combined.length; j++) {
      const width = (g: (typeof combined)[number]) =>
        Math.max(
          64,
          MAP_NUMBER.format(g.visits).length * 12 +
            (g.entries.length > 1 ? 62 : 38),
        );
      assert.ok(
        Math.abs(combined[i].x - combined[j].x) >=
          (width(combined[i]) + width(combined[j])) / 2 + 8 ||
          Math.abs(combined[i].y - combined[j].y) >= 58,
      );
    }
});

test("merge keeps unchanged objects, applies updates and additions, and removes missing locations", () => {
  const old = createMapEntries([location, { ...location, name: "Удалённая" }]);
  assert.equal(
    mergeMapEntries(
      old,
      createMapEntries([location, { ...location, name: "Удалённая" }]),
    ),
    old,
  );
  const next = mergeMapEntries(
    old,
    createMapEntries([
      { ...location, employees: 20 },
      { ...location, name: "Новая" },
    ]),
  );
  assert.equal(next[0].key, old[0].key);
  assert.equal(next[0].employees, 20);
  assert.notEqual(next[0], old[0]);
  assert.equal(next[1].name, "Новая");
  const added = mergeMapEntries(
    old,
    createMapEntries([
      location,
      { ...location, name: "Удалённая" },
      { ...location, name: "Новая" },
    ]),
  );
  assert.equal(added[0], old[0]);
  assert.equal(added[1], old[1]);
});

test("focused nearby locations keep individual counts and real coordinates", () => {
  const entries = createMapEntries([
    { ...location, address: "Проспект Абылай хана, 51/53", employees: 3 },
    {
      ...location,
      address: "город Алматы, Алмалинский район ул. Желтоксан, 62",
      employees: 7,
    },
  ]);
  const points = entries.map((entry, i) => ({
    entry,
    x: 300 + i * 20,
    y: 250,
  }));
  assert.equal(groupMapPoints(points).length, 1);
  const focused = groupMapPoints(points, 1, { selectedKey: entries[0].key });
  assert.deepEqual(
    focused.map((group) => group.visits),
    [3, 7],
  );
  assert.deepEqual(focused[0].offset, [0, 0]);
  assert.equal(focused[1].x, points[1].x);
  assert.equal(focused[1].y, points[1].y);
  assert.ok(Math.hypot(...focused[1].offset!) > 0);
  assert.ok(Math.hypot(...focused[1].offset!) < 80);
  assert.equal(groupMapPoints(points, 1, { spread: true }).length, 2);
});

test("nearby labels spread without overlap while large groups stay bounded", () => {
  const entries = createMapEntries(
    Array.from({ length: 20 }, (_, i) => ({ ...location, name: String(i) })),
  );
  const points = entries.map((entry, i) => ({
    entry,
    x: 300.123 + i * 0.1,
    y: 250.321,
  }));
  const small = groupMapPoints(points.slice(0, 6), 1.4, {
    spread: true,
    selectedKey: entries[0].key,
  });
  assert.equal(small.length, 6);
  for (let i = 0; i < small.length; i++)
    for (let j = i + 1; j < small.length; j++) {
      const a = small[i],
        b = small[j];
      assert.ok(
        Math.abs(a.x + a.offset![0] - b.x - b.offset![0]) >= 64 * 1.4 + 8 ||
          Math.abs(a.y + a.offset![1] - b.y - b.offset![1]) >= 58 * 1.4,
      );
    }
  assert.equal(groupMapPoints(points, 1, { spread: true }).length, 1);
  const selected = groupMapPoints(points, 1, {
    selectedKey: entries[0].key,
    spread: true,
  });
  assert.equal(selected.length, 2);
  assert.equal(selected[0].entries[0].key, entries[0].key);
  assert.equal(selected[1].entries.length, 19);
  assert.equal(
    selected.reduce((sum, group) => sum + group.visits, 0),
    240,
  );
});
