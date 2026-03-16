import React, { useMemo } from "react";
import { Circle, Marker } from "react-leaflet";
import L from "leaflet";

interface AnimatedMarkerProps {
  position: [number, number];
  name: string;
  address: string;
  employees: number;
  isVisible: boolean;
  onClick: () => void;
  isActive: boolean;
  radius: number;
  color: string;
  mapZoom: number;
  mapExtentMeters: number;
  isDarkTheme: boolean;
}

const HEX_COLOR_RE = /^#([\da-f]{3}|[\da-f]{6})$/i;

const getSafeColor = (value: string): string =>
  HEX_COLOR_RE.test(value) ? value : "#ef4444";

const clamp01 = (value: number): number => Math.min(1, Math.max(0, value));

const hexToRgb = (hex: string): { r: number; g: number; b: number } => {
  const value = hex.replace("#", "");
  const normalized =
    value.length === 3
      ? value
          .split("")
          .map((char) => `${char}${char}`)
          .join("")
      : value;

  if (normalized.length !== 6) {
    return { r: 239, g: 68, b: 68 };
  }

  return {
    r: parseInt(normalized.slice(0, 2), 16),
    g: parseInt(normalized.slice(2, 4), 16),
    b: parseInt(normalized.slice(4, 6), 16),
  };
};

const rgbToHex = (r: number, g: number, b: number): string =>
  `#${[r, g, b]
    .map((channel) => Math.round(channel).toString(16).padStart(2, "0"))
    .join("")}`;

const rgbToHsl = (r: number, g: number, b: number) => {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const delta = max - min;

  let h = 0;
  const l = (max + min) / 2;
  const s = delta === 0 ? 0 : delta / (1 - Math.abs(2 * l - 1));

  if (delta !== 0) {
    if (max === rn) {
      h = ((gn - bn) / delta) % 6;
    } else if (max === gn) {
      h = (bn - rn) / delta + 2;
    } else {
      h = (rn - gn) / delta + 4;
    }
    h *= 60;
    if (h < 0) h += 360;
  }

  return { h, s, l };
};

const hslToRgb = (h: number, s: number, l: number) => {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;

  let rp = 0;
  let gp = 0;
  let bp = 0;

  if (h < 60) {
    rp = c;
    gp = x;
  } else if (h < 120) {
    rp = x;
    gp = c;
  } else if (h < 180) {
    gp = c;
    bp = x;
  } else if (h < 240) {
    gp = x;
    bp = c;
  } else if (h < 300) {
    rp = x;
    bp = c;
  } else {
    rp = c;
    bp = x;
  }

  return {
    r: (rp + m) * 255,
    g: (gp + m) * 255,
    b: (bp + m) * 255,
  };
};

const enhanceColorForDarkTheme = (hex: string): string => {
  const { r, g, b } = hexToRgb(hex);
  const { h, s, l } = rgbToHsl(r, g, b);
  const boostedSaturation = clamp01(s + (s < 0.68 ? 0.14 : 0.1));
  const loweredLightness = clamp01(l - (l > 0.55 ? 0.1 : 0.08));
  const nextRgb = hslToRgb(h, boostedSaturation, loweredLightness);
  return rgbToHex(nextRgb.r, nextRgb.g, nextRgb.b);
};

const softenColorForLightTheme = (hex: string): string => {
  const { r, g, b } = hexToRgb(hex);
  const { h, s, l } = rgbToHsl(r, g, b);
  const lift = l < 0.32 ? 0.18 : l < 0.45 ? 0.13 : 0.08;
  const liftedLightness = clamp01(Math.min(0.78, l + lift));
  const balancedSaturation = clamp01(s + (s < 0.45 ? 0.08 : 0.04));
  const nextRgb = hslToRgb(h, balancedSaturation, liftedLightness);
  return rgbToHex(nextRgb.r, nextRgb.g, nextRgb.b);
};

const getEmployeesBadge = (value: number): string => {
  if (value > 999) return "999+";
  if (value > 99) return "99+";
  return String(Math.max(0, Math.floor(value)));
};

const hexToRgba = (hex: string, alpha: number): string => {
  const value = hex.replace("#", "");
  const normalized =
    value.length === 3
      ? value
          .split("")
          .map((char) => `${char}${char}`)
          .join("")
      : value;

  if (normalized.length !== 6) {
    return `rgba(239,68,68,${alpha})`;
  }

  const r = parseInt(normalized.slice(0, 2), 16);
  const g = parseInt(normalized.slice(2, 4), 16);
  const b = parseInt(normalized.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
};

const AnimatedMarker: React.FC<AnimatedMarkerProps> = ({
  position,
  name,
  address,
  employees,
  isVisible,
  onClick,
  isActive,
  radius,
  color,
  mapZoom,
  mapExtentMeters,
  isDarkTheme,
}) => {
  const safeColor = useMemo(() => getSafeColor(color), [color]);
  const renderColor = useMemo(
    () =>
      isDarkTheme
        ? enhanceColorForDarkTheme(safeColor)
        : softenColorForLightTheme(safeColor),
    [isDarkTheme, safeColor],
  );

  const markerScale = useMemo(
    () => Math.min(1.2, Math.max(0.95, 0.95 + employees * 0.01)),
    [employees],
  );

  const markerIcon = useMemo(() => {
    const employeesBadge = getEmployeesBadge(employees);

    return L.divIcon({
      className: "map-pin-icon-wrapper",
      iconSize: [48, 58],
      iconAnchor: [24, 46],
      popupAnchor: [0, -38],
      html: `
        <div class="map-pin-icon ${isActive ? "is-active" : ""}" style="--pin-color:${renderColor};--pin-scale:${markerScale};" title="${name.replace(/"/g, "&quot;")}\n${address.replace(/"/g, "&quot;")}">
          <span class="map-pin-wave"></span>
          <span class="map-pin-core"><span class="map-pin-core-dot"></span></span>
          <span class="map-pin-badge">${employeesBadge}</span>
        </div>
      `,
    });
  }, [address, employees, isActive, markerScale, name, renderColor]);

  if (!isVisible) {
    return null;
  }

  const normalizedEmployees = Math.max(1, Math.floor(employees));
  const densityFactor = Math.min(1, Math.log10(normalizedEmployees + 12) / 2.9);

  const latRad = (position[0] * Math.PI) / 180;
  const metersPerPixel =
    (156543.03392 * Math.max(0.12, Math.cos(latRad))) / Math.pow(2, mapZoom);

  const zoomOutFactor = Math.max(0, Math.min(1, (13.6 - mapZoom) / 4.4));
  const extentFactor = Math.max(0, Math.min(1, mapExtentMeters / 40000));
  const minVisualRadiusPixels = isActive
    ? 10 + zoomOutFactor * 9 + extentFactor * 2
    : 8 + zoomOutFactor * 7 + extentFactor * 1.6;
  const minVisualRadiusMeters = Math.max(48, minVisualRadiusPixels * metersPerPixel);
  const zoomAdaptiveRadius =
    radius * (1 + zoomOutFactor * (1.9 + extentFactor * 1.25));
  const baseRadius = Math.max(zoomAdaptiveRadius, minVisualRadiusMeters);

  const auraRadius = Math.max(
    76,
    Math.min(360, Math.round(baseRadius * (0.86 + densityFactor * 1.08))),
  );
  const perimeterRadius = Math.max(
    54,
    Math.min(250, Math.round(auraRadius * (isActive ? 0.72 : 0.66))),
  );
  const waveRadius = Math.max(
    92,
    Math.min(460, Math.round(auraRadius * (isActive ? 1.2 : 1.1))),
  );

  const baseOutline = isDarkTheme
    ? "rgba(248,250,252,0.72)"
    : "rgba(15,23,42,0.42)";

  return (
    <>
      <Circle
        center={position}
        radius={perimeterRadius + (isActive ? 5 : 4)}
        interactive={false}
        pathOptions={{
          color: baseOutline,
          fillOpacity: 0,
          opacity: isActive ? 0.82 : 0.64,
          weight: isActive ? 2.2 : 1.8,
        }}
        className="map-marker-outline"
      />
      <Circle
        center={position}
        radius={auraRadius}
        interactive={false}
        pathOptions={{
          color: renderColor,
          fillColor: renderColor,
          fillOpacity: isDarkTheme
            ? isActive
              ? 0.41
              : 0.33
            : isActive
              ? 0.33
              : 0.24,
          weight: isActive ? 2.7 : 2.1,
          opacity: isActive ? 0.9 : 0.8,
        }}
        className={`map-marker-aura ${
          isActive ? "map-marker-aura-active" : "map-marker-aura-muted"
        }`}
      />
      <Circle
        center={position}
        radius={perimeterRadius}
        interactive={false}
        pathOptions={{
          color: renderColor,
          fillOpacity: 0,
          weight: isActive ? 2.9 : 2.3,
          opacity: isActive ? 0.94 : 0.82,
        }}
        className={`map-marker-perimeter ${
          isActive
            ? "map-marker-perimeter-active"
            : "map-marker-perimeter-muted"
        }`}
      />
      <Circle
        center={position}
        radius={waveRadius}
        interactive={false}
        pathOptions={{
          color: hexToRgba(renderColor, isActive ? 0.96 : 0.88),
          fillOpacity: 0,
          weight: isActive ? 2.1 : 1.8,
          opacity: isActive ? 0.78 : 0.58,
          dashArray: "9 7",
        }}
        className={`map-marker-wave ${
          isActive ? "map-marker-wave-active" : "map-marker-wave-muted"
        }`}
      />

      <Marker
        position={position}
        icon={markerIcon}
        eventHandlers={{
          click: onClick,
        }}
      />
    </>
  );
};

export default AnimatedMarker;
