"""Verify spherical geometry without database access.

The module can run after calling ``django.setup()`` and then
``unittest.main(module=__name__)``.
"""

import math
import random
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from monitoring_app import geo, utils


class GeoTests(TestCase):
    def test_small_clusters_avoid_grid_setup(self):
        items = [dict(latitude=0, longitude=i * 0.001) for i in range(64)]
        with patch("monitoring_app.geo._clique_cells", wraps=geo._clique_cells) as grid:
            clusters = utils.cluster_geo_items(items, radius_m=2)
        self.assertEqual(len(clusters), len(items))
        grid.assert_not_called()

    def test_grid_preserves_exact_boundaries_near_poles_and_dateline(self):
        for lat, lon in ((0, 179.999999), (89.999, 40), (-89.999, -40), (43, 76)):
            points = [(lat, lon), (lat, lon + 0.000018)]
            points.extend((-40 + i * 0.1, -100) for i in range(70))
            items = [dict(id=i, latitude=a, longitude=b) for i, (a, b) in enumerate(points)]
            distance = geo.calculate_distance_haversine(*points[0], *points[1])
            for delta, joined in ((-1e-9, False), (0, True), (1e-9, True)):
                clusters = geo.cluster_geo_items(items, radius_m=distance + delta)
                self.assertEqual(len(clusters), len(items) - int(joined))
                self.assertEqual(len(clusters[0]["items"]), 2 if joined else 1)

    def test_override_only_radii_do_not_build_an_unused_index(self):
        locations = [
            SimpleNamespace(id=i, latitude=0, longitude=i * 0.001, acceptance_radius_m=95)
            for i in range(100)
        ]
        with patch("monitoring_app.geo.SphericalIndex", wraps=geo.SphericalIndex) as index:
            radii = utils.compute_class_location_acceptance_radii(locations)
        self.assertEqual(radii, {i: 95 for i in range(100)})
        self.assertEqual(index.call_count, 0)

    def test_grid_and_color_thresholds_match_exact_haversine_at_cell_boundaries(self):
        items = [dict(id=0, latitude=0, longitude=0), dict(id=1, latitude=0, longitude=0.000018)]
        distance = utils.calculate_distance_haversine(0, 0, 0, 0.000018)
        locations = [SimpleNamespace(**item) for item in items]
        for delta, cluster_sizes, colors in (
            (-1e-7, [1, 1], [0, 0]),
            (0, [2], [0, 0]),
            (1e-7, [2], [0, 1]),
        ):
            clusters = utils.cluster_geo_items(items, radius_m=distance + delta)
            self.assertEqual(sorted(len(group["items"]) for group in clusters), cluster_sizes)
            self.assertEqual(
                list(utils.compute_neighbor_color_index(locations, distance + delta).values()),
                colors,
            )
        self.assertEqual(
            utils.compute_class_location_acceptance_radii(
                locations,
                same_point_threshold=distance,
                cluster_threshold=distance + 1,
            ),
            {0: 80, 1: 80},
        )
        self.assertEqual(
            utils.compute_class_location_acceptance_radii(
                locations,
                same_point_threshold=distance + 1e-7,
                cluster_threshold=distance + 1,
            ),
            {0: 60, 1: 60},
        )

    def test_dense_colors_do_not_check_every_pair(self):
        locations = [SimpleNamespace(id=i, latitude=0, longitude=i * 1e-11) for i in range(512)]
        with patch(
            "monitoring_app.geo.calculate_distance_haversine",
            wraps=utils.calculate_distance_haversine,
        ) as distance:
            colors = utils.compute_neighbor_color_index(locations)
        self.assertEqual(list(colors.values()), [0, 1, 2, 3, 4] + [0] * 507)
        self.assertLessEqual(distance.call_count, len(locations) * 10)

    def test_dense_separate_components_do_not_enumerate_all_edges(self):
        items = [dict(id=i, latitude=0 if i < 256 else 1, longitude=i * 1e-11) for i in range(512)]
        returned_neighbors = 0
        original = geo.SphericalIndex.neighbors

        def counted_neighbors(index, point, radius):
            nonlocal returned_neighbors
            neighbors = original(index, point, radius)
            returned_neighbors += len(neighbors)
            return neighbors

        with patch.object(geo.SphericalIndex, "neighbors", counted_neighbors):
            clusters = utils.cluster_geo_items(items, radius_m=2)
        self.assertEqual(
            [[item["id"] for item in cluster["items"]] for cluster in clusters],
            [list(range(256)), list(range(256, 512))],
        )
        self.assertLessEqual(returned_neighbors, len(items) * 10)

    def test_bulk_nearest_does_not_query_radius_for_every_point(self):
        locations = [dict(name=str(i), latitude=0, longitude=i * 0.001) for i in range(100)]
        searcher = utils.LocationSearcher(locations)
        coordinates = [(0, float(loc["longitude"]) + 0.00001) for loc in locations]
        with patch.object(searcher.index, "tree", wraps=searcher.index.tree) as tree:
            nearest = searcher.find_nearest_locations_bulk(coordinates)
        self.assertEqual(nearest, locations)
        self.assertLessEqual(tree.query_ball_point.call_count, 4)

    def test_radii_do_not_compute_all_pairs(self):
        locations = [
            SimpleNamespace(id=i, latitude=43 + i * 0.001, longitude=76, acceptance_radius_m=None)
            for i in range(512)
        ]
        with patch(
            "monitoring_app.geo.calculate_distance_haversine",
            wraps=utils.calculate_distance_haversine,
        ) as distance:
            with patch("monitoring_app.utils.calculate_distance_haversine", distance):
                radii = utils.compute_class_location_acceptance_radii(locations, r_standalone=70)
        self.assertEqual(set(radii.values()), {70})
        self.assertLessEqual(distance.call_count, len(locations))

    def test_search_covers_longitude_poles_and_dateline(self):
        for origin, target, radius in [
            ((43.24, 76.9), (43.24, 76.9022), 200),
            ((89.99, 0), (89.99, 1), 30),
            ((0, 179.9999), (0, -179.9999), 30),
        ]:
            location = dict(latitude=target[0], longitude=target[1], name="near")
            searcher = utils.LocationSearcher([location])
            self.assertEqual(searcher.find_nearest(*origin, radius=radius), "near")
            self.assertEqual(
                searcher.find_nearest_locations_bulk([origin], radius=radius), [location]
            )

    def test_empty_search_keeps_bulk_alignment(self):
        searcher = utils.LocationSearcher([])
        self.assertEqual(searcher.find_nearest(0, 0), "Unknown Area")
        self.assertEqual(searcher.find_nearest_locations_bulk([(0, 0), (1, 1)]), [None, None])

    def test_search_exact_radius_and_duplicate_tie(self):
        locations = [dict(latitude=0.0, longitude=0.0, name=name) for name in ("first", "second")]
        searcher = utils.LocationSearcher(locations)
        self.assertEqual(searcher.find_nearest(0, 0, radius=0), "first")
        self.assertEqual(searcher.find_nearest(0, 0, radius=-1), "Unknown Area")
        distance = utils.calculate_distance_haversine(0, 0.001, 0, 0)
        self.assertEqual(searcher.find_nearest(0, 0.001, radius=distance), "first")
        self.assertEqual(searcher.find_nearest(0, 0.001, radius=distance - 0.0001), "Unknown Area")

    def test_radius_search_keeps_all_shared_pins_in_input_order(self):
        locations = [
            dict(name=name, latitude=0, longitude=lon)
            for name, lon in (("far", 1), ("first", 0), ("second", 0))
        ]
        matches = utils.LocationSearcher(locations).find_locations_within_radius(0, 0, 0)
        self.assertEqual([location["name"] for _, location in matches], ["first", "second"])

    def test_radii_and_colors_match_pairwise_reference(self):
        rng = random.Random(15)
        locations = [
            SimpleNamespace(
                id=i,
                latitude=43 + rng.random() * 0.002,
                longitude=76 + rng.random() * 0.002,
                acceptance_radius_m=123 if i % 7 == 0 else None,
            )
            for i in range(80)
        ]
        locations[1].latitude, locations[1].longitude = (
            locations[2].latitude,
            locations[2].longitude,
        )
        radii, colors = {}, {}
        for loc in locations:
            distances = {
                other.id: utils.calculate_distance_haversine(
                    loc.latitude, loc.longitude, other.latitude, other.longitude
                )
                for other in locations
                if other.id != loc.id
            }
            nearest = min(distances.values())
            radii[loc.id] = loc.acceptance_radius_m or (
                60 if nearest < 5 else 80 if nearest < 30 else 70
            )
            used = {
                colors[key]
                for key, distance in distances.items()
                if key in colors and distance < 30
            }
            color = 0
            while color in used:
                color += 1
            colors[loc.id] = color % 5
        self.assertEqual(
            utils.compute_class_location_acceptance_radii(locations, r_standalone=70), radii
        )
        self.assertEqual(utils.compute_neighbor_color_index(locations), colors)

    def test_clusters_are_transitive_keep_duplicates_and_isolates(self):
        items = [
            dict(latitude=0.0, longitude=lon, id=i)
            for i, lon in enumerate([0, 0.000015, 0.000030, 1] + [0] * 30)
        ]
        clusters = utils._cluster_geo_items_for_excel(items, radius_m=2)
        groups = {frozenset(item["id"] for item in cluster["items"]) for cluster in clusters}
        self.assertEqual(groups, {frozenset({0, 1, 2, *range(4, 34)}), frozenset({3})})
        clusters = utils._cluster_geo_items_for_excel(items, radius_m=0)
        self.assertEqual(sorted(len(cluster["items"]) for cluster in clusters), [1, 1, 1, 31])

    def test_haversine_antipodes_are_finite(self):
        self.assertAlmostEqual(
            utils.calculate_distance_haversine(0, 0, 0, 180), math.pi * utils.R_EARTH_M
        )

    def test_clusters_match_pairwise_components(self):
        rng = random.Random(19)
        for count in (3, 8, 9, 40, 120):
            items = [
                dict(
                    id=i,
                    latitude=43 + rng.random() * 0.00015,
                    longitude=76 + rng.random() * 0.00015,
                )
                for i in range(count)
            ]
            for radius in (0, 2, 6, 100):
                parents = list(range(count))

                def find(i):
                    while parents[i] != i:
                        i = parents[i]
                    return i

                for i in range(count):
                    for j in range(i):
                        if (
                            utils.calculate_distance_haversine(
                                items[i]["latitude"],
                                items[i]["longitude"],
                                items[j]["latitude"],
                                items[j]["longitude"],
                            )
                            <= radius
                        ):
                            parents[find(i)] = find(j)
                expected = {}
                for i in range(count):
                    expected.setdefault(find(i), set()).add(i)
                actual = utils._cluster_geo_items_for_excel(items, radius_m=radius)
                self.assertEqual(
                    {frozenset(item["id"] for item in cluster["items"]) for cluster in actual},
                    {frozenset(group) for group in expected.values()},
                )

    def test_radii_override_singleton_missing_coordinates_and_repeated_ids(self):
        locations = [
            SimpleNamespace(id=i, latitude=0.0, longitude=lon, acceptance_radius_m=override)
            for i, lon, override in ((1, 0, None), (1, 0, None), (2, 1, 95))
        ]
        locations.append(
            SimpleNamespace(id=3, latitude=None, longitude=0, acceptance_radius_m=None)
        )
        self.assertEqual(utils.compute_class_location_acceptance_radii(locations), {1: 70, 2: 95})
        self.assertEqual(utils.compute_class_location_acceptance_radii(locations[:1]), {1: 70})

    def test_nearest_bulk_matches_exhaustive_global_search(self):
        rng = random.Random(33)
        locations = [
            dict(latitude=rng.uniform(-89, 89), longitude=rng.uniform(-180, 180), name=str(i))
            for i in range(80)
        ]
        coordinates = [(rng.uniform(-89, 89), rng.uniform(-180, 180)) for _ in range(60)]
        searcher = utils.LocationSearcher(locations)
        for radius in (200, 500_000, math.inf):
            expected = []
            for lat, lon in coordinates:
                distances = [
                    utils.calculate_distance_haversine(lat, lon, loc["latitude"], loc["longitude"])
                    for loc in locations
                ]
                i = min(range(len(locations)), key=lambda i: distances[i])
                expected.append(locations[i] if distances[i] <= radius else None)
            self.assertEqual(
                searcher.find_nearest_locations_bulk(coordinates, radius=radius), expected
            )

    def test_view_helpers_share_spherical_search_and_stable_cluster_sorting(self):
        from monitoring_app.services.attendance_day import merge_day
        from monitoring_app.views import _cluster_geo_items

        items = [dict(lat=0, lon=lon, sort_id=i) for i, lon in ((2, 0), (1, 0), (3, 1))]
        clusters = _cluster_geo_items(items, 2)
        self.assertEqual(
            [[item["sort_id"] for item in group["items"]] for group in clusters], [[1, 2], [3]]
        )
        searcher = utils.LocationSearcher([dict(latitude=43.24, longitude=76.9022, name="east")])
        import datetime

        start = datetime.datetime(2026, 10, 3, 9, tzinfo=datetime.timezone.utc)
        merged = merge_day(
            [],
            [
                dict(
                    first_in=start,
                    last_out=start + datetime.timedelta(hours=1),
                    latitude=43.24,
                    longitude=76.9,
                )
            ],
            searcher,
        )
        self.assertEqual((merged["area_name_in"], merged["area_name_out"]), ("east", "east"))
        self.assertEqual(merged["effective_work_seconds"], 3600)
