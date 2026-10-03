"""Provide exact spherical searches and clustering for geographic coordinates.

The module uses Euclidean chord distances for spatial-index bounds and
Haversine distances for final inclusion checks.
"""

import math
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.spatial import cKDTree

from monitoring_app.lesson_locations_conf import (
    ACCEPTANCE_R_CLUSTER,
    ACCEPTANCE_R_SAME_POINT,
    ACCEPTANCE_R_STANDALONE,
    CLUSTER_THRESHOLD_M,
    DEFAULT_ACCEPTANCE_RADIUS_M,
    SAME_POINT_THRESHOLD_M,
)

R_EARTH_M = 6_371_000
_CHORD_EPSILON = 1e-12


def calculate_distance_haversine(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin(math.radians(lat2 - lat1) / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    a = min(1.0, max(0.0, a))
    return R_EARTH_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _sphere_points(coordinates):
    radians = np.radians(np.asarray(coordinates, dtype=float).reshape(-1, 2))
    lat, lon = radians[:, 0], radians[:, 1]
    cos_lat = np.cos(lat)
    return np.column_stack((cos_lat * np.cos(lon), cos_lat * np.sin(lon), np.sin(lat)))


def _chord_radius(radius_m: float) -> float:
    return 2 * math.sin(min(math.pi, radius_m / R_EARTH_M) / 2) + _CHORD_EPSILON


def _clique_cells(points, radius_m):
    """Group unit-sphere points into cells narrower than a search radius.

    Args:
        points: NumPy array of three-dimensional unit-sphere points.
        radius_m: Maximum geographic distance in meters.

    Returns:
        A tuple containing unique cells, inverse cell indices, and cell side
        length, or ``None`` when the radius is too small for safe contraction.
    """
    side = (_chord_radius(radius_m) - 5 * _CHORD_EPSILON) / math.sqrt(3)
    if side <= 32 * _CHORD_EPSILON:
        return None
    cells, inverse = np.unique(
        np.floor(points / side).astype(np.int64), axis=0, return_inverse=True
    )
    return cells, inverse, side


def _cell_component_labels(coordinates, points, radius_m, grid):
    """Return connected-component labels after contracting clique cells.

    Args:
        coordinates: Geographic ``(latitude, longitude)`` pairs in degrees.
        points: NumPy array of corresponding unit-sphere points.
        radius_m: Maximum edge distance in meters.
        grid: Cell data returned by :func:`_clique_cells`.

    Returns:
        A component label for every input coordinate.
    """
    cells, inverse, side = grid
    parents = list(range(len(cells)))
    sizes = [1] * len(cells)

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    limit = _chord_radius(radius_m) - _CHORD_EPSILON
    pairs = cKDTree(cells).query_pairs(limit / side + math.sqrt(3) + 1e-9, output_type="ndarray")
    if len(pairs):
        gaps = np.maximum(np.abs(cells[pairs[:, 0]] - cells[pairs[:, 1]]) - 1, 0) * side
        pairs = pairs[np.einsum("ij,ij->i", gaps, gaps) <= (limit + _CHORD_EPSILON) ** 2]
    members = [[] for _ in cells]
    for i, cell in enumerate(inverse):
        members[int(cell)].append(i)
    trees = {}
    for a, b in pairs:
        root_a, root_b = find(int(a)), find(int(b))
        if root_a == root_b:
            continue
        small, large = (a, b) if len(members[a]) <= len(members[b]) else (b, a)
        if large not in trees:
            trees[large] = cKDTree(points[members[large]])
        tree = trees[large]
        chords, _neighbors = tree.query(points[members[small]], k=1)
        connected = bool(np.any(chords < limit - 2 * _CHORD_EPSILON))
        if not connected:
            for row in np.flatnonzero(chords <= limit + 2 * _CHORD_EPSILON):
                i = members[small][int(row)]
                for other in tree.query_ball_point(points[i], limit + 2 * _CHORD_EPSILON):
                    j = members[large][other]
                    if calculate_distance_haversine(*coordinates[i], *coordinates[j]) <= radius_m:
                        connected = True
                        break
                if connected:
                    break
        if connected:
            if sizes[root_a] < sizes[root_b]:
                root_a, root_b = root_b, root_a
            parents[root_b] = root_a
            sizes[root_a] += sizes[root_b]
    return [find(int(cell)) for cell in inverse]


class SphericalIndex:
    """Index coordinates with exact spherical candidate bounds.

    Args:
        coordinates: Geographic ``(latitude, longitude)`` pairs in degrees.

    Note:
        The index uses linear space and typically builds in ``O(n log n)``.
    """

    def __init__(self, coordinates):
        self.coordinates = np.asarray(coordinates, dtype=float).reshape(-1, 2)
        self.points = _sphere_points(self.coordinates)
        self.tree = cKDTree(self.points) if len(self.points) else None

    def neighbors(self, index: int, radius_m: float):
        if self.tree is None or radius_m < 0:
            return []
        return self.tree.query_ball_point(self.points[index], _chord_radius(radius_m))

    def nearest_bulk(self, coordinates, radius: float = math.inf) -> list[int | None]:
        """Find the nearest indexed coordinate for each query coordinate.

        Args:
            coordinates: Query ``(latitude, longitude)`` pairs in degrees.
            radius: Maximum accepted distance in meters.

        Returns:
            Indexed coordinate positions, with ``None`` for unmatched queries.
        """
        if not len(coordinates):
            return []
        if self.tree is None or radius < 0 or math.isnan(radius):
            return [None] * len(coordinates)
        points = _sphere_points(coordinates)
        limit = _chord_radius(radius)
        chords, indices = self.tree.query(points, k=2, distance_upper_bound=limit)
        valid = np.isfinite(chords[:, 0])
        result = np.where(valid, indices[:, 0], -1)
        ambiguous = valid & (chords[:, 1] <= chords[:, 0] + 2 * _CHORD_EPSILON)
        if math.isfinite(radius):
            ambiguous |= valid & (
                np.abs(chords[:, 0] - (limit - _CHORD_EPSILON)) <= 2 * _CHORD_EPSILON
            )
        for row in np.flatnonzero(ambiguous):
            candidates = self.tree.query_ball_point(
                points[row], float(chords[row, 0]) + 2 * _CHORD_EPSILON
            )
            best = min(
                (calculate_distance_haversine(*coordinates[row], *self.coordinates[i]), int(i))
                for i in candidates
            )
            result[row] = best[1] if best[0] <= radius else -1
        return [int(i) if i >= 0 else None for i in result]


class LocationSearcher:
    """Search retained location payloads through a spherical index.

    Args:
        locations: Iterable of mappings containing ``latitude``, ``longitude``,
            and ``name`` values.
    """

    def __init__(self, locations):
        self.locations = list(locations)
        first_by_coord = {}
        for i, loc in enumerate(self.locations):
            first_by_coord.setdefault((float(loc["latitude"]), float(loc["longitude"])), i)
        self._indices = list(first_by_coord.values())
        member_by_coord = {coordinate: [] for coordinate in first_by_coord}
        for i, loc in enumerate(self.locations):
            member_by_coord[(float(loc["latitude"]), float(loc["longitude"]))].append(i)
        self._members = list(member_by_coord.values())
        self.index = SphericalIndex(list(first_by_coord))
        self.names = [loc["name"] for loc in self.locations]

    def find_nearest_location(self, lat, lon, radius: float = 200):
        if lat is None or lon is None:
            return None
        return self.find_nearest_locations_bulk([(float(lat), float(lon))], radius=radius)[0]

    def find_nearest(self, lat, lon, radius: float = 200):
        location = self.find_nearest_location(lat, lon, radius=radius)
        return str(location.get("name") or "Unknown Area") if location else "Unknown Area"

    def find_locations_within_radius(self, lat, lon, radius: float):
        """Find every retained location within a radius.

        Args:
            lat: Query latitude in degrees.
            lon: Query longitude in degrees.
            radius: Maximum accepted distance in meters.

        Returns:
            ``(distance, payload)`` pairs ordered by distance and input order.
            Payloads sharing coordinates are retained separately.
        """
        if self.index.tree is None or lat is None or lon is None or radius < 0:
            return []
        point = _sphere_points([(lat, lon)])[0]
        candidates = self.index.tree.query_ball_point(point, _chord_radius(radius))
        matches = []
        for i in candidates:
            distance = calculate_distance_haversine(lat, lon, *self.index.coordinates[i])
            if distance <= radius:
                for original_index in self._members[i]:
                    matches.append((distance, original_index))
        matches.sort()
        return [(distance, self.locations[i]) for distance, i in matches]

    def find_nearest_locations_bulk(
        self,
        coordinates: Sequence[tuple[float, float]],
        *,
        radius: float = 200,
    ) -> list[dict[str, Any] | None]:
        """Find nearest location payloads for multiple coordinates.

        Args:
            coordinates: Query ``(latitude, longitude)`` pairs in degrees.
            radius: Maximum accepted distance in meters.

        Returns:
            Payloads aligned with the queries, with ``None`` for unmatched
            coordinates.
        """
        unique = dict.fromkeys((float(lat), float(lon)) for lat, lon in coordinates)
        nearest = self.index.nearest_bulk(list(unique), radius)
        resolved = {
            coordinate: self.locations[self._indices[i]] if i is not None else None
            for coordinate, i in zip(unique, nearest)
        }
        return [resolved[(float(lat), float(lon))] for lat, lon in coordinates]


def compute_class_location_acceptance_radii(
    locations,
    r_same_point=ACCEPTANCE_R_SAME_POINT,
    r_cluster=ACCEPTANCE_R_CLUSTER,
    r_standalone=ACCEPTANCE_R_STANDALONE,
    same_point_threshold: float = SAME_POINT_THRESHOLD_M,
    cluster_threshold: float = CLUSTER_THRESHOLD_M,
):
    """Compute acceptance radii from overrides and nearest neighbors.

    Args:
        locations: Objects with ``id``, coordinates, and an optional
            ``acceptance_radius_m`` value.
        r_same_point: Radius for locations closer than
            ``same_point_threshold``.
        r_cluster: Radius for locations closer than ``cluster_threshold``.
        r_standalone: Radius for locations without a nearby neighbor.
        same_point_threshold: Shared-pin threshold in meters.
        cluster_threshold: Neighbor-cluster threshold in meters.

    Returns:
        A mapping from location ID to acceptance radius in meters.
    """
    locs = [
        loc
        for loc in locations
        if getattr(loc, "latitude", None) is not None
        and getattr(loc, "longitude", None) is not None
    ]
    overrides = [getattr(loc, "acceptance_radius_m", None) or 0 for loc in locs]
    pending = [i for i, override in enumerate(overrides) if override <= 0]
    unique_ids = len({loc.id for loc in locs})
    if not pending or unique_ids <= 1:
        return {
            loc.id: int(overrides[i]) if overrides[i] > 0 else r_standalone
            for i, loc in enumerate(locs)
        }
    index = SphericalIndex([(loc.latitude, loc.longitude) for loc in locs])
    assert index.tree is not None
    nearest_chords = np.full(len(locs), math.inf)
    if unique_ids == len(locs):
        chords, neighbors = index.tree.query(index.points[pending], k=2)
        columns = np.where(neighbors[:, 0] == np.asarray(pending), 1, 0)
        nearest_chords[pending] = chords[np.arange(len(pending)), columns]
    else:
        k = min(2, len(locs))
        while pending:
            chords, candidates = index.tree.query(index.points[pending], k=k)
            unresolved = []
            for row, (i, neighbors) in enumerate(zip(pending, candidates)):
                other = next(
                    (col for col, j in enumerate(neighbors) if locs[int(j)].id != locs[i].id), None
                )
                if other is None:
                    unresolved.append(i)
                else:
                    nearest_chords[i] = chords[row, other]
            pending = unresolved
            k = min(k * 2, len(locs))
    below_thresholds = []
    for threshold in (same_point_threshold, cluster_threshold):
        if threshold <= 0 or math.isnan(threshold):
            below = np.zeros(len(locs), dtype=bool)
        elif threshold > math.pi * R_EARTH_M:
            below = np.isfinite(nearest_chords)
        else:
            limit = _chord_radius(threshold) - _CHORD_EPSILON
            below = nearest_chords < limit
            for i in np.flatnonzero(np.abs(nearest_chords - limit) <= 2 * _CHORD_EPSILON):
                below[i] = any(
                    locs[j].id != locs[i].id
                    and calculate_distance_haversine(
                        *index.coordinates[i],
                        *index.coordinates[j],
                    )
                    < threshold
                    for j in index.neighbors(int(i), threshold)
                )
        below_thresholds.append(below)
    return {
        loc.id: (
            int(overrides[i])
            if overrides[i] > 0
            else (
                r_same_point
                if below_thresholds[0][i]
                else r_cluster if below_thresholds[1][i] else r_standalone
            )
        )
        for i, loc in enumerate(locs)
    }


def get_location_radius(loc, radii_dict=None):
    override = getattr(loc, "acceptance_radius_m", None)
    if override is not None and override > 0:
        return int(override)
    if radii_dict and getattr(loc, "id", None) in radii_dict:
        return int(radii_dict[loc.id])
    return DEFAULT_ACCEPTANCE_RADIUS_M


def compute_neighbor_color_index(locations, neighbor_threshold_m: float = CLUSTER_THRESHOLD_M):
    """Assign contrasting palette indices to neighboring locations.

    Args:
        locations: Objects with ``id``, ``latitude``, and ``longitude`` values.
        neighbor_threshold_m: Distance below which locations are neighbors.

    Returns:
        A mapping from location ID to a palette index from zero through four.
    """
    locs = [loc for loc in locations if loc.latitude is not None and loc.longitude is not None]
    if not locs or neighbor_threshold_m <= 0 or math.isnan(neighbor_threshold_m):
        return {loc.id: 0 for loc in locs}
    index = SphericalIndex([(loc.latitude, loc.longitude) for loc in locs])
    grid = (
        _clique_cells(index.points, neighbor_threshold_m)
        if len({loc.id for loc in locs}) == len(locs)
        else None
    )
    cell_ids = grid[1] if grid is not None else None
    masks = [0] * len(grid[0]) if grid is not None else []
    out = {}
    for i, loc in enumerate(locs):
        used = masks[int(cell_ids[i])] if cell_ids is not None else 0
        if used != 31:
            for j in index.neighbors(i, neighbor_threshold_m):
                other = locs[j]
                if other.id not in out:
                    continue
                bit = 1 << out[other.id]
                if (
                    not used & bit
                    and calculate_distance_haversine(
                        *index.coordinates[i],
                        *index.coordinates[j],
                    )
                    < neighbor_threshold_m
                ):
                    used |= bit
                    if used == 31:
                        break
        color = next((color for color in range(5) if not used & (1 << color)), 0)
        out[loc.id] = color
        if cell_ids is not None:
            masks[int(cell_ids[i])] |= 1 << color
    return out


def is_within_radius(lat1, lon1, lat2, lon2, radius=200):
    return calculate_distance_haversine(lat1, lon1, lat2, lon2) <= radius


def cluster_geo_items(
    items: Sequence[Mapping[str, Any]],
    *,
    radius_m: float,
    lat_key: str = "latitude",
    lon_key: str = "longitude",
) -> list[dict[str, Any]]:
    """Cluster geographic records into radius-connected components.

    Args:
        items: Records containing latitude and longitude values.
        radius_m: Maximum distance for an edge between two records.
        lat_key: Record key containing latitude.
        lon_key: Record key containing longitude.

    Returns:
        Components containing their records and arithmetic center coordinates.

    Raises:
        ValueError: If a large input contains non-finite coordinates.
    """
    if not items:
        return []
    if radius_m < 0:
        return [
            dict(items=[item], center_lat=float(item[lat_key]), center_lon=float(item[lon_key]))
            for item in items
        ]
    coordinate_indices: dict[tuple[float, float], int] = {}
    item_indices = []
    for item in items:
        coordinate = (float(item[lat_key]), float(item[lon_key]))
        coordinate_indices.setdefault(coordinate, len(coordinate_indices))
        item_indices.append(coordinate_indices[coordinate])
    coordinates = list(coordinate_indices)
    grid = None
    if len(coordinates) > 64:
        points = _sphere_points(coordinates)
        if not np.isfinite(points).all():
            raise ValueError("Geo coordinates must be finite")
        grid = _clique_cells(points, radius_m)
    if grid is not None:
        labels = _cell_component_labels(coordinates, points, radius_m, grid)
    else:
        index = SphericalIndex(coordinates)
        labels = [-1] * len(coordinates)
        discovered = 0
        group_count = 0
        for start in range(len(coordinates)):
            if labels[start] >= 0:
                continue
            label = group_count
            group_count += 1
            labels[start] = label
            discovered += 1
            stack = [start]
            while stack and discovered < len(coordinates):
                i = stack.pop()
                for j in index.neighbors(i, radius_m):
                    if (
                        labels[j] < 0
                        and calculate_distance_haversine(
                            *coordinates[i],
                            *coordinates[j],
                        )
                        <= radius_m
                    ):
                        labels[j] = label
                        discovered += 1
                        stack.append(j)
    groups: list[list[Mapping[str, Any]]] = []
    groups_by_label = {}
    for label in labels:
        if label not in groups_by_label:
            groups_by_label[label] = len(groups)
            groups.append([])
    for item, i in zip(items, item_indices):
        groups[groups_by_label[labels[i]]].append(item)
    return [
        dict(
            items=group,
            center_lat=sum(float(item[lat_key]) for item in group) / len(group),
            center_lon=sum(float(item[lon_key]) for item in group) / len(group),
        )
        for group in groups
    ]
