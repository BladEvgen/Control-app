import test from "node:test";
import assert from "node:assert/strict";
import type { Map as LibreMap, LayerSpecification } from "maplibre-gl";
import { applyMapTheme } from "../../src/components/map/mapTheme.ts";

test("map themes preserve distinct terrain and road classes and reuse building shadows", () => {
  const layers: LayerSpecification[] = [
    { id: "background", type: "background" },
    {
      id: "road_area_pattern",
      type: "fill",
      source: "tiles",
      "source-layer": "transportation",
      paint: { "fill-pattern": "pedestrian_polygon" },
    },
    {
      id: "road_path_pedestrian",
      type: "line",
      source: "tiles",
      "source-layer": "transportation",
    },
    ...["water", "park", "building"].map((source) => ({
      id: source,
      type: "fill" as const,
      source: "tiles",
      "source-layer": source,
    })),
    ...["wood", "ice", "sand"].map((kind) => ({
      id: `landcover_${kind}`,
      type: "fill" as const,
      source: "tiles",
      "source-layer": "landcover",
    })),
    ...["minor", "secondary_tertiary", "motorway"].map((kind) => ({
      id: `road_${kind}`,
      type: "line" as const,
      source: "tiles",
      "source-layer": "transportation",
    })),
  ];
  const paint = new Map<string, unknown>();
  const zoomRanges = new Map<string, number[]>();
  const map = {
    getStyle: () => ({ layers: [...layers] }),
    setLayerZoomRange: (id: string, min: number, max: number) =>
      zoomRanges.set(id, [min, max]),
    getLayer: (id: string) => layers.find((layer) => layer.id === id),
    addLayer: (layer: LayerSpecification) => layers.push(layer),
    setPaintProperty: (id: string, property: string, value: unknown) =>
      paint.set(`${id}/${property}`, value),
  } as unknown as LibreMap;
  applyMapTheme(map, false);
  assert.deepEqual(zoomRanges.get("building"), [13, 24]);
  assert.equal(
    layers.find((layer) => layer.id === "building-shadow")?.maxzoom,
    24,
  );
  assert.equal(paint.get("road_area_pattern/fill-pattern"), undefined);
  assert.notEqual(
    paint.get("road_path_pedestrian/line-color"),
    paint.get("road_minor/line-color"),
  );
  assert.ok(Number(paint.get("road_path_pedestrian/line-opacity")) < 1);
  const light = new Map(paint);
  for (const dark of [true, false, true]) {
    applyMapTheme(map, dark);
    assert.equal(
      layers.filter((layer) => layer.id === "building-shadow").length,
      1,
    );
    assert.equal(
      new Set(
        [
          "water",
          "park",
          "building",
          "landcover_wood",
          "landcover_ice",
          "landcover_sand",
        ].map((id) => paint.get(`${id}/fill-color`)),
      ).size,
      6,
    );
    assert.equal(
      new Set(
        ["minor", "secondary_tertiary", "motorway"].map((id) =>
          paint.get(`road_${id}/line-color`),
        ),
      ).size,
      3,
    );
    assert.notEqual(
      paint.get("building-shadow/fill-color"),
      paint.get("building/fill-color"),
    );
    if (!dark) assert.deepEqual(paint, light);
    else
      assert.notEqual(
        paint.get("water/fill-color"),
        light.get("water/fill-color"),
      );
  }
});
