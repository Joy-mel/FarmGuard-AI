"""
FarmGuard AI - Kenya County Reference Data
=============================================
All 47 Kenyan counties with approximate centroid coordinates, grouped into
7 broad agro-ecological zones for soil profiling.

IMPORTANT HONESTY NOTE: coordinates here are county-level centroids (or
main town), not precise farm locations - fine for a regional climate/price
forecast, not a substitute for a GPS reading of an actual field. Soil
profiles are assigned per zone (7 categories), not surveyed per county -
they're a reasonable approximation grounded in Kenya's known agro-ecological
geography, not lab data. Before real farmer decisions lean on soil
guidance specifically, swap `ZONE_SOIL_PROFILES` lookups for a query to
Kenya Soil Survey / FAO's Harmonized World Soil Database for the exact
coordinates.
"""

# name -> (lat, lon, zone)
KENYA_COUNTIES = {
    "mombasa":          (-4.0435, 39.6682, "coast"),
    "kwale":            (-4.1740, 39.4520, "coast"),
    "kilifi":           (-3.5107, 39.9093, "coast"),
    "tana_river":       (-1.0167, 40.1167, "coast"),
    "lamu":             (-2.2717, 40.9020, "coast"),
    "taita_taveta":     (-3.3167, 38.3500, "coast"),
    "garissa":          (-0.4569, 39.6583, "arid_north"),
    "wajir":            (1.7471, 40.0629, "arid_north"),
    "mandera":          (3.9366, 41.8670, "arid_north"),
    "marsabit":         (2.3284, 37.9899, "arid_north"),
    "isiolo":           (0.3546, 37.5822, "arid_north"),
    "turkana":          (3.1167, 35.6000, "arid_north"),
    "samburu":          (1.1167, 36.9500, "arid_north"),
    "west_pokot":       (1.6167, 35.1167, "rift_valley"),
    "meru":             (0.0470, 37.6500, "central_highlands"),
    "tharaka_nithi":    (-0.3000, 37.9000, "central_highlands"),
    "embu":             (-0.5310, 37.4500, "central_highlands"),
    "kitui":            (-1.3667, 38.0167, "eastern_semi_arid"),
    "machakos":         (-1.5177, 37.2634, "eastern_semi_arid"),
    "makueni":          (-1.8043, 37.6236, "eastern_semi_arid"),
    "nyandarua":        (-0.1833, 36.5167, "central_highlands"),
    "nyeri":            (-0.4167, 36.9500, "central_highlands"),
    "kirinyaga":        (-0.6667, 37.3833, "central_highlands"),
    "muranga":          (-0.7167, 37.1500, "central_highlands"),
    "kiambu":           (-1.1714, 36.8356, "central_highlands"),
    "nairobi":          (-1.2921, 36.8219, "central_highlands"),
    "trans_nzoia":      (1.0167, 34.9500, "rift_valley"),
    "uasin_gishu":      (0.5143, 35.2698, "rift_valley"),
    "elgeyo_marakwet":  (0.8000, 35.5000, "rift_valley"),
    "nandi":            (0.1833, 35.1167, "rift_valley"),
    "baringo":          (0.4667, 35.9667, "rift_valley"),
    "laikipia":         (0.2000, 36.7833, "rift_valley"),
    "nakuru":           (-0.3031, 36.0800, "rift_valley"),
    "narok":            (-1.0833, 35.8667, "southern_rangelands"),
    "kajiado":          (-1.8500, 36.7833, "southern_rangelands"),
    "kericho":          (-0.3667, 35.2833, "rift_valley"),
    "bomet":            (-0.7833, 35.3333, "rift_valley"),
    "kakamega":         (0.2827, 34.7519, "lake_basin"),
    "vihiga":           (0.0500, 34.7167, "lake_basin"),
    "bungoma":          (0.5667, 34.5667, "lake_basin"),
    "busia":            (0.4608, 34.1116, "lake_basin"),
    "siaya":            (0.0667, 34.2833, "lake_basin"),
    "kisumu":           (-0.0917, 34.7680, "lake_basin"),
    "homa_bay":         (-0.5167, 34.4500, "lake_basin"),
    "migori":           (-1.0634, 34.4731, "lake_basin"),
    "kisii":            (-0.6817, 34.7667, "lake_basin"),
    "nyamira":          (-0.5633, 34.9358, "lake_basin"),
}

assert len(KENYA_COUNTIES) == 47, "Kenya has 47 counties - check the list above"

ZONE_SOIL_PROFILES = {
    "central_highlands": {
        "type": "Nitisols", "ph": 5.8, "organic_matter": 3.8,
        "nitrogen": "Medium", "phosphorus": "Low", "potassium": "Medium",
        "water_retention": "High", "suitability": ["Maize", "Beans", "Coffee", "Tea"],
    },
    "lake_basin": {
        "type": "Vertisols", "ph": 6.5, "organic_matter": 2.4,
        "nitrogen": "Medium", "phosphorus": "Medium", "potassium": "High",
        "water_retention": "Very High", "suitability": ["Rice", "Maize", "Sugarcane", "Sorghum"],
    },
    "rift_valley": {
        "type": "Andosols", "ph": 6.1, "organic_matter": 3.6,
        "nitrogen": "Medium", "phosphorus": "Medium", "potassium": "High",
        "water_retention": "Medium", "suitability": ["Maize", "Wheat", "Vegetables", "Pyrethrum"],
    },
    "eastern_semi_arid": {
        "type": "Luvisols", "ph": 6.4, "organic_matter": 1.8,
        "nitrogen": "Low", "phosphorus": "Low", "potassium": "Medium",
        "water_retention": "Low", "suitability": ["Sorghum", "Millet", "Cowpeas", "Drought-resistant maize"],
    },
    "coast": {
        "type": "Arenosols", "ph": 6.8, "organic_matter": 1.5,
        "nitrogen": "Low", "phosphorus": "Low", "potassium": "Medium",
        "water_retention": "Low", "suitability": ["Coconut", "Cashew nuts", "Cassava", "Mango"],
    },
    "arid_north": {
        "type": "Xerosols", "ph": 7.5, "organic_matter": 0.8,
        "nitrogen": "Low", "phosphorus": "Low", "potassium": "Low",
        "water_retention": "Very Low", "suitability": ["Sorghum", "Livestock pasture", "Drought-resistant millet"],
    },
    "southern_rangelands": {
        "type": "Vertisols", "ph": 6.9, "organic_matter": 1.6,
        "nitrogen": "Low", "phosphorus": "Low", "potassium": "Medium",
        "water_retention": "Medium", "suitability": ["Livestock pasture", "Sorghum", "Sunflower"],
    },
}


def get_zone_soil(location_name: str) -> dict:
    entry = KENYA_COUNTIES.get(location_name)
    zone = entry[2] if entry else "central_highlands"
    return ZONE_SOIL_PROFILES[zone]


def get_coords(location_name: str):
    entry = KENYA_COUNTIES.get(location_name, KENYA_COUNTIES["nairobi"])
    return entry[0], entry[1]
