"""Посещение зданий за прошедший день по точным PIN из расписания."""

from datetime import date, timedelta
from math import cos, radians, sin

from monitoring_app import models, utils


def address_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _sphere_point(latitude: float, longitude: float) -> tuple[float, float, float]:
    lat, lon = radians(latitude), radians(longitude)
    return cos(lat) * cos(lon), cos(lat) * sin(lon), sin(lat)


def _location_index(locations):
    """O(L log L): точный индекс на сфере и прежние правила радиусов."""
    from scipy.spatial import cKDTree

    if not locations:
        return None, {}
    coords = [_sphere_point(loc.latitude, loc.longitude) for loc in locations]
    tree = cKDTree(coords)
    _distances, neighbors = tree.query(coords, k=2)
    radii = {}
    for i, loc in enumerate(locations):
        other_i = int(neighbors[i][1])
        if other_i >= len(locations):
            distance = float("inf")
        else:
            other = locations[other_i]
            distance = utils.calculate_distance_haversine(
                loc.latitude, loc.longitude, other.latitude, other.longitude
            )
        default = 60 if distance < 5 else 80 if distance < 30 else 70
        radii[loc.id] = loc.acceptance_radius_m or default
    return tree, radii


def schedule_presence(on: date, requests: list[dict]) -> list[dict]:
    locations = list(models.ClassLocation.objects.all())
    by_address: dict[str, list] = {}
    for loc in locations:
        by_address.setdefault(address_key(loc.address), []).append(loc)
    all_pins = {pin for item in requests for pin in item["pins"]}
    staff: dict[int, str] = {
        staff_id: pin
        for staff_id, pin in models.Staff.all_objects.filter(pin__in=all_pins).values_list(
            "id", "pin"
        )
    }
    visited: dict[str, set[str]] = {pin: set() for pin in staff.values()}
    for row in (
        models.StaffAttendance.objects.filter(staff_id__in=staff, date_at=on + timedelta(days=1))
        .values(
            "staff_id",
            "first_in",
            "area_name_in",
            "area_name_out",
            "area_sequence",
            "report_variants",
        )
        .iterator(chunk_size=2000)
    ):
        variants = row["report_variants"]
        all_report = variants.get("all") if isinstance(variants, dict) else None
        entrance = all_report if isinstance(all_report, dict) else row
        if not entrance.get("first_in"):
            continue
        areas = [entrance.get("area_name_in"), entrance.get("area_name_out")]
        sequence = row["area_sequence"]
        if isinstance(sequence, list):
            areas.extend(item.get("area") for item in sequence if isinstance(item, dict))
        for area in areas:
            resolved = utils.resolve_area_address(area) if isinstance(area, str) else None
            if resolved:
                visited[staff[row["staff_id"]]].add(address_key(resolved))

    tree, radii = _location_index(locations)
    radius_chord = 2 * sin(max(radii.values(), default=70) / (2 * utils.R_EARTH_M))
    by_coords: dict[tuple[float, float], str | None] = {}
    lessons = (
        models.LessonAttendance.exclude_report_invalid_days()
        .filter(staff_id__in=staff, date_at=on)
        .values("staff_id", "latitude", "longitude", "first_in")
    )
    for row in lessons.iterator(chunk_size=2000):
        if row["first_in"] is None:
            continue
        coords = (row["latitude"], row["longitude"])
        if coords not in by_coords:
            matches = []
            candidates = (
                tree.query_ball_point(
                    _sphere_point(*coords), r=radius_chord + 1e-12, return_sorted=False
                )
                if tree is not None
                else []
            )
            for i in candidates:
                loc = locations[i]
                distance = utils.calculate_distance_haversine(*coords, loc.latitude, loc.longitude)
                if distance <= radii[loc.id]:
                    matches.append((distance, i, loc))
            nearest = min(matches, key=lambda pair: (pair[0], pair[1]))[2] if matches else None
            by_coords[coords] = address_key(nearest.address) if nearest else None
        address = by_coords[coords]
        if address:
            visited[staff[row["staff_id"]]].add(address)

    known = set(staff.values())
    has_data = (
        models.StaffAttendance.objects.filter(date_at=on + timedelta(days=1)).exists()
        or models.LessonAttendance.objects.filter(date_at=on).exists()
    )
    results = []
    for item in requests:
        key = address_key(item["address"])
        candidates = by_address.get(key, [])
        pins = set(item["pins"])
        results.append(
            {
                "id": item["id"],
                "address": item["address"],
                "status": (
                    ("ok" if has_data else "no_data")
                    if len(candidates) == 1
                    else "location_unresolved"
                ),
                "present_pins": (
                    sorted(pin for pin in pins if key in visited.get(pin, set()))
                    if len(candidates) == 1
                    else []
                ),
                "unknown_pins": sorted(pins - known),
            }
        )
    return results
