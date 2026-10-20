import type { Map as LibreMap } from "maplibre-gl";

export const BASEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";

export function applyMapTheme(map: LibreMap, dark: boolean): void {
  const p = dark
    ? {
        land: "#222d38",
        residential: "#2c3946",
        water: "#21658a",
        park: "#2f705b",
        wood: "#285a48",
        grass: "#396c54",
        building: "#46596a",
        edge: "#62758a",
        shadow: "#101923",
        pedestrian: "#30404c",
        path: "#526575",
        road: "#63778a",
        roadEdge: "#24313e",
        major: "#c0a063",
        highway: "#d4a56c",
        hospital: "#533e51",
        school: "#53513c",
        sand: "#6c6041",
        ice: "#6d929c",
        text: "#e1e8ec",
        secondary: "#b4c6d3",
        waterText: "#b6e4f7",
        boundary: "#8c879f",
      }
    : {
        land: "#f2ede3",
        residential: "#e5e3df",
        water: "#59a7d6",
        park: "#83b986",
        wood: "#68a077",
        grass: "#abd093",
        building: "#cfbdac",
        edge: "#b49f8e",
        shadow: "#9a8e81",
        pedestrian: "#e5dfd4",
        path: "#b1a894",
        road: "#fffdf5",
        roadEdge: "#cabaa5",
        major: "#f5c86b",
        highway: "#eda65c",
        hospital: "#efd1d6",
        school: "#e8dcac",
        sand: "#e8d39a",
        ice: "#d8edf0",
        text: "#314352",
        secondary: "#53636b",
        waterText: "#154e72",
        boundary: "#9a88a6",
      };
  for (const layer of map.getStyle().layers) {
    if (layer.id === "building-shadow") continue;
    const source = "source-layer" in layer ? layer["source-layer"] : "";
    if (layer.type === "background")
      map.setPaintProperty(layer.id, "background-color", p.land);
    if (layer.type === "raster" || layer.type === "fill-extrusion")
      map.setLayoutProperty(layer.id, "visibility", "none");
    if (layer.type === "fill") {
      if (layer.paint?.["fill-pattern"])
        map.setPaintProperty(layer.id, "fill-pattern", undefined);
      const color =
        source === "transportation"
          ? p.pedestrian
          : source === "water"
            ? p.water
            : source === "park"
              ? p.park
              : source === "building"
                ? p.building
                : /wood/.test(layer.id)
                  ? p.wood
                  : /grass|pitch|track|cemetery|wetland/.test(layer.id)
                    ? p.grass
                    : /hospital/.test(layer.id)
                      ? p.hospital
                      : /school/.test(layer.id)
                        ? p.school
                        : /sand/.test(layer.id)
                          ? p.sand
                          : /ice/.test(layer.id)
                            ? p.ice
                            : source === "landuse"
                              ? p.residential
                              : p.land;
      map.setPaintProperty(layer.id, "fill-color", color);
      if (source === "park" || source === "landcover" || source === "landuse")
        map.setPaintProperty(layer.id, "fill-opacity", 1);
      if (source === "park" || source === "building")
        map.setPaintProperty(
          layer.id,
          "fill-outline-color",
          source === "park" ? p.wood : p.edge,
        );
      if (layer.id === "landuse_residential")
        map.setLayerZoomRange(layer.id, 0, 24);
      if (source === "building" && layer.id === "building") {
        map.setLayerZoomRange(layer.id, 13, 24);
        if (!map.getLayer("building-shadow"))
          map.addLayer(
            { ...layer, id: "building-shadow", maxzoom: 24, paint: {} },
            layer.id,
          );
        map.setPaintProperty("building-shadow", "fill-color", p.shadow);
        map.setPaintProperty("building-shadow", "fill-translate", [2, 3]);
        map.setPaintProperty("building-shadow", "fill-opacity", 0.35);
      }
    }
    if (layer.type === "line") {
      const color =
        source === "waterway"
          ? p.water
          : source === "park"
            ? p.wood
            : /path|pedestrian/.test(layer.id)
              ? p.path
              : source === "boundary"
                ? p.boundary
                : /rail/.test(layer.id)
                  ? p.edge
                  : /casing/.test(layer.id)
                    ? p.roadEdge
                    : /motorway/.test(layer.id)
                      ? p.highway
                      : /trunk|primary|secondary|tertiary|link/.test(layer.id)
                        ? p.major
                        : p.road;
      map.setPaintProperty(layer.id, "line-color", color);
      if (/path|pedestrian/.test(layer.id) || source === "park")
        map.setPaintProperty(layer.id, "line-opacity", 0.55);
    }
    if (layer.type === "symbol") {
      if (/shield|one_way/.test(layer.id))
        map.setLayoutProperty(layer.id, "visibility", "none");
      if (layer.layout?.["text-field"]) {
        const water = source === "water_name" || source === "waterway";
        map.setPaintProperty(
          layer.id,
          "text-color",
          water ? p.waterText : source === "poi" ? p.secondary : p.text,
        );
        map.setPaintProperty(
          layer.id,
          "text-halo-color",
          water ? p.water : p.land,
        );
        map.setPaintProperty(layer.id, "text-halo-width", dark ? 1.4 : 1.8);
        map.setLayoutProperty(layer.id, "text-field", [
          "coalesce",
          ["get", "name:ru"],
          ["get", "name"],
          ["get", "name:latin"],
        ]);
      }
    }
  }
  if (map.getLayer("building-shadow"))
    map.setPaintProperty("building-shadow", "fill-color", p.shadow);
}
