# Configuration for lesson_locations: receiving radii R_loc by location, cached in Redis.
#
# --- Model (geomathematics) ---
# • The Earth is a sphere with R ≈ 6371 km. Haversine gives the length of the great circle arc between
# two points along (lat, lon). For distances <1 km, the error of the sphere relative to the
# WGS84 ellipsoid < 0.01% is acceptable.
# • One point in the database (pin) is the conventional "center" of the object. A real building/yard has a
# size of 30–100+ m. A person "in the location" ⟺ Haversine(user, pin) ≤ R_loc.
# • GPS accuracy: 5–15 m (smartphone). R_loc must be at least 15–20 m, otherwise
# legitimate users at the entrance will receive a 404. Typical R_loc range: 50–100 m.
#
# --- Rules for R_loc (if ClassLocation.acceptance_radius_m is not set) ---
# Classification by min_d — minimum distance to another location (Haversine, m):
#
# min_d < 5 m — single point, multiple organizations (shared pin) → R = 60
# 5 ≤ min_d < 30 m — single building/campus, courtyard, multiple pins → R = 80
# min_d ≥ 30 m — stand-alone location (one point per building) → R = 70
#
# Rationale: in a cluster (5–30 m), pins are spaced apart — zone Uncertainty and yard
# are greater, so R=80. For "single point" and "separate"—60 and 70, with a reserve for
# yard/wing. For specific objects (hospital, large building), set
# acceptance_radius_m in the database (50–100 m).
#
# --- Cache ---
CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY = "class_location_acceptance_radii"
CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_TTL = 3600

# Radii (m) by neighborhood class
ACCEPTANCE_R_SAME_POINT = 60 # min_d < SAME_POINT_THRESHOLD_M
ACCEPTANCE_R_CLUSTER = 80 # SAME_POINT_THRESHOLD_M ≤ min_d < CLUSTER_THRESHOLD_M
ACCEPTANCE_R_STANDALONE = 70 # min_d ≥ CLUSTER_THRESHOLD_M

# Thresholds (m) to the nearest other location
SAME_POINT_THRESHOLD_M = 5
CLUSTER_THRESHOLD_M = 30

# Fallback if there is no cache entry for the location
DEFAULT_ACCEPTANCE_RADIUS_M = 70
