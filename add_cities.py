import json
from pathlib import Path

data_dir = Path("data")

def load_json(name):
    with open(data_dir / name, "r") as f:
        return json.load(f)

def save_json(name, data):
    with open(data_dir / name, "w") as f:
        json.dump(data, f, indent=2)

cities = load_json("cities.json")
climate = load_json("climate.json")
construction_costs = load_json("construction_costs.json")
demographics = load_json("demographics.json")
land_use = load_json("land_use.json")
walkability = load_json("walkability.json")

new_cities_data = {
    "san_francisco_ca": {
        "cities": {"name": "San Francisco", "state": "CA", "region": "West", "city_tier": 1, "population": 808437, "lat": 37.7749, "lon": -122.4194},
        "climate": {"climate_zone": "3C", "climate_description": "Warm Marine", "annual_hdd": 2900, "annual_cdd": 100, "heat_island_risk": 2, "flood_risk_score": 3, "recommended_min_green_cover_pct": 20.0, "solar_irradiance_kwh_per_sqm": 5.0, "avg_summer_temp_f": 68.0, "target_green_space_pct": 20.0, "data_sources": "NOAA/ASHRAE"},
        "construction": {"city_index": 128.0, "residential_cost_per_sqft": 350.0, "commercial_cost_per_sqft": 450.0, "green_space_cost_per_sqft": 25.0, "parking_cost_per_space": 40000.0},
        "demographics": {"median_household_income": 136689.0, "poverty_rate": 10.3, "population_density_per_sqmi": 18635.0, "pct_age_65_plus": 15.6, "pct_with_disability": 9.4, "pct_renter_occupied": 62.0, "unemployment_rate": 3.8, "median_home_value": 1300000.0, "pct_no_vehicle": 30.5, "pct_non_white": 59.8, "target_community_center_sqft": 25000.0, "target_affordable_housing_pct": 40.0, "data_year": 2022, "source": "ACS 2022 5-Year Estimates"},
        "land_use": {"max_parking_spaces": 50, "typical_zoning": "RH-2", "max_building_height_stories": 60},
        "walkability": {"walk_score": 89.0, "transit_score": 77.0, "bike_score": 72.0, "walkability_score": 79.0}
    },
    "miami_fl": {
        "cities": {"name": "Miami", "state": "FL", "region": "Southeast", "city_tier": 1, "population": 449514, "lat": 25.7617, "lon": -80.1918},
        "climate": {"climate_zone": "1A", "climate_description": "Very Hot, Humid", "annual_hdd": 150, "annual_cdd": 4400, "heat_island_risk": 4, "flood_risk_score": 5, "recommended_min_green_cover_pct": 25.0, "solar_irradiance_kwh_per_sqm": 5.5, "avg_summer_temp_f": 89.0, "target_green_space_pct": 25.0, "data_sources": "NOAA/ASHRAE"},
        "construction": {"city_index": 98.0, "residential_cost_per_sqft": 210.0, "commercial_cost_per_sqft": 290.0, "green_space_cost_per_sqft": 15.0, "parking_cost_per_space": 25000.0},
        "demographics": {"median_household_income": 54050.0, "poverty_rate": 19.5, "population_density_per_sqmi": 12500.0, "pct_age_65_plus": 16.5, "pct_with_disability": 11.2, "pct_renter_occupied": 70.0, "unemployment_rate": 4.2, "median_home_value": 450000.0, "pct_no_vehicle": 16.0, "pct_non_white": 88.0, "target_community_center_sqft": 15000.0, "target_affordable_housing_pct": 30.0, "data_year": 2022, "source": "ACS 2022 5-Year Estimates"},
        "land_use": {"max_parking_spaces": 150, "typical_zoning": "T4", "max_building_height_stories": 45},
        "walkability": {"walk_score": 77.0, "transit_score": 57.0, "bike_score": 64.0, "walkability_score": 66.0}
    },
    "chicago_il": {
        "cities": {"name": "Chicago", "state": "IL", "region": "Midwest", "city_tier": 1, "population": 2665039, "lat": 41.8781, "lon": -87.6298},
        "climate": {"climate_zone": "5A", "climate_description": "Cool, Humid", "annual_hdd": 6500, "annual_cdd": 800, "heat_island_risk": 4, "flood_risk_score": 3, "recommended_min_green_cover_pct": 25.0, "solar_irradiance_kwh_per_sqm": 4.5, "avg_summer_temp_f": 75.0, "target_green_space_pct": 25.0, "data_sources": "NOAA/ASHRAE"},
        "construction": {"city_index": 115.0, "residential_cost_per_sqft": 240.0, "commercial_cost_per_sqft": 320.0, "green_space_cost_per_sqft": 18.0, "parking_cost_per_space": 30000.0},
        "demographics": {"median_household_income": 71673.0, "poverty_rate": 17.0, "population_density_per_sqmi": 12100.0, "pct_age_65_plus": 12.8, "pct_with_disability": 10.5, "pct_renter_occupied": 55.0, "unemployment_rate": 5.5, "median_home_value": 300000.0, "pct_no_vehicle": 27.5, "pct_non_white": 66.0, "target_community_center_sqft": 20000.0, "target_affordable_housing_pct": 25.0, "data_year": 2022, "source": "ACS 2022 5-Year Estimates"},
        "land_use": {"max_parking_spaces": 100, "typical_zoning": "RS-3", "max_building_height_stories": 100},
        "walkability": {"walk_score": 77.0, "transit_score": 65.0, "bike_score": 72.0, "walkability_score": 71.0}
    },
    "columbus_oh": {
        "cities": {"name": "Columbus", "state": "OH", "region": "Midwest", "city_tier": 2, "population": 907971, "lat": 39.9612, "lon": -82.9988},
        "climate": {"climate_zone": "4A", "climate_description": "Mixed, Humid", "annual_hdd": 5200, "annual_cdd": 1000, "heat_island_risk": 3, "flood_risk_score": 2, "recommended_min_green_cover_pct": 20.0, "solar_irradiance_kwh_per_sqm": 4.2, "avg_summer_temp_f": 75.0, "target_green_space_pct": 20.0, "data_sources": "NOAA/ASHRAE"},
        "construction": {"city_index": 96.0, "residential_cost_per_sqft": 170.0, "commercial_cost_per_sqft": 230.0, "green_space_cost_per_sqft": 12.0, "parking_cost_per_space": 18000.0},
        "demographics": {"median_household_income": 62000.0, "poverty_rate": 19.5, "population_density_per_sqmi": 4100.0, "pct_age_65_plus": 10.5, "pct_with_disability": 11.5, "pct_renter_occupied": 55.0, "unemployment_rate": 4.0, "median_home_value": 240000.0, "pct_no_vehicle": 8.5, "pct_non_white": 46.0, "target_community_center_sqft": 15000.0, "target_affordable_housing_pct": 20.0, "data_year": 2022, "source": "ACS 2022 5-Year Estimates"},
        "land_use": {"max_parking_spaces": 200, "typical_zoning": "R-3", "max_building_height_stories": 30},
        "walkability": {"walk_score": 41.0, "transit_score": 30.0, "bike_score": 48.0, "walkability_score": 39.0}
    },
    "new_york_ny": {
        "cities": {"name": "New York", "state": "NY", "region": "Northeast", "city_tier": 1, "population": 8335897, "lat": 40.7128, "lon": -74.0060},
        "climate": {"climate_zone": "4A", "climate_description": "Mixed, Humid", "annual_hdd": 4700, "annual_cdd": 1200, "heat_island_risk": 5, "flood_risk_score": 4, "recommended_min_green_cover_pct": 20.0, "solar_irradiance_kwh_per_sqm": 4.5, "avg_summer_temp_f": 77.0, "target_green_space_pct": 20.0, "data_sources": "NOAA/ASHRAE"},
        "construction": {"city_index": 132.0, "residential_cost_per_sqft": 400.0, "commercial_cost_per_sqft": 500.0, "green_space_cost_per_sqft": 30.0, "parking_cost_per_space": 45000.0},
        "demographics": {"median_household_income": 76607.0, "poverty_rate": 17.2, "population_density_per_sqmi": 29302.0, "pct_age_65_plus": 15.2, "pct_with_disability": 10.9, "pct_renter_occupied": 67.0, "unemployment_rate": 5.2, "median_home_value": 730000.0, "pct_no_vehicle": 54.5, "pct_non_white": 69.0, "target_community_center_sqft": 25000.0, "target_affordable_housing_pct": 40.0, "data_year": 2022, "source": "ACS 2022 5-Year Estimates"},
        "land_use": {"max_parking_spaces": 25, "typical_zoning": "R6", "max_building_height_stories": 100},
        "walkability": {"walk_score": 98.0, "transit_score": 89.0, "bike_score": 70.0, "walkability_score": 85.0}
    },
    "atlanta_ga": {
        "cities": {"name": "Atlanta", "state": "GA", "region": "Southeast", "city_tier": 1, "population": 499127, "lat": 33.7490, "lon": -84.3880},
        "climate": {"climate_zone": "3A", "climate_description": "Warm, Humid", "annual_hdd": 2800, "annual_cdd": 2100, "heat_island_risk": 4, "flood_risk_score": 2, "recommended_min_green_cover_pct": 35.0, "solar_irradiance_kwh_per_sqm": 5.0, "avg_summer_temp_f": 82.0, "target_green_space_pct": 40.0, "data_sources": "NOAA/ASHRAE"},
        "construction": {"city_index": 98.0, "residential_cost_per_sqft": 180.0, "commercial_cost_per_sqft": 250.0, "green_space_cost_per_sqft": 12.0, "parking_cost_per_space": 20000.0},
        "demographics": {"median_household_income": 77655.0, "poverty_rate": 17.5, "population_density_per_sqmi": 3600.0, "pct_age_65_plus": 11.5, "pct_with_disability": 10.5, "pct_renter_occupied": 55.0, "unemployment_rate": 4.5, "median_home_value": 410000.0, "pct_no_vehicle": 13.5, "pct_non_white": 61.0, "target_community_center_sqft": 15000.0, "target_affordable_housing_pct": 25.0, "data_year": 2022, "source": "ACS 2022 5-Year Estimates"},
        "land_use": {"max_parking_spaces": 200, "typical_zoning": "R4", "max_building_height_stories": 50},
        "walkability": {"walk_score": 49.0, "transit_score": 44.0, "bike_score": 42.0, "walkability_score": 45.0}
    },
    "denver_co": {
        "cities": {"name": "Denver", "state": "CO", "region": "Mountain", "city_tier": 1, "population": 713252, "lat": 39.7392, "lon": -104.9903},
        "climate": {"climate_zone": "5B", "climate_description": "Cool, Dry", "annual_hdd": 6000, "annual_cdd": 800, "heat_island_risk": 3, "flood_risk_score": 2, "recommended_min_green_cover_pct": 20.0, "solar_irradiance_kwh_per_sqm": 5.8, "avg_summer_temp_f": 74.0, "target_green_space_pct": 20.0, "data_sources": "NOAA/ASHRAE"},
        "construction": {"city_index": 105.0, "residential_cost_per_sqft": 220.0, "commercial_cost_per_sqft": 300.0, "green_space_cost_per_sqft": 15.0, "parking_cost_per_space": 25000.0},
        "demographics": {"median_household_income": 85853.0, "poverty_rate": 11.0, "population_density_per_sqmi": 4700.0, "pct_age_65_plus": 11.0, "pct_with_disability": 9.5, "pct_renter_occupied": 50.0, "unemployment_rate": 3.8, "median_home_value": 560000.0, "pct_no_vehicle": 8.0, "pct_non_white": 46.0, "target_community_center_sqft": 18000.0, "target_affordable_housing_pct": 25.0, "data_year": 2022, "source": "ACS 2022 5-Year Estimates"},
        "land_use": {"max_parking_spaces": 150, "typical_zoning": "U-SU-C", "max_building_height_stories": 40},
        "walkability": {"walk_score": 61.0, "transit_score": 45.0, "bike_score": 73.0, "walkability_score": 59.0}
    },
    "boston_ma": {
        "cities": {"name": "Boston", "state": "MA", "region": "Northeast", "city_tier": 1, "population": 650706, "lat": 42.3601, "lon": -71.0589},
        "climate": {"climate_zone": "5A", "climate_description": "Cool, Humid", "annual_hdd": 5600, "annual_cdd": 800, "heat_island_risk": 3, "flood_risk_score": 4, "recommended_min_green_cover_pct": 25.0, "solar_irradiance_kwh_per_sqm": 4.5, "avg_summer_temp_f": 74.0, "target_green_space_pct": 25.0, "data_sources": "NOAA/ASHRAE"},
        "construction": {"city_index": 125.0, "residential_cost_per_sqft": 320.0, "commercial_cost_per_sqft": 420.0, "green_space_cost_per_sqft": 20.0, "parking_cost_per_space": 35000.0},
        "demographics": {"median_household_income": 89212.0, "poverty_rate": 17.5, "population_density_per_sqmi": 14200.0, "pct_age_65_plus": 12.0, "pct_with_disability": 10.5, "pct_renter_occupied": 65.0, "unemployment_rate": 4.2, "median_home_value": 720000.0, "pct_no_vehicle": 33.5, "pct_non_white": 55.0, "target_community_center_sqft": 20000.0, "target_affordable_housing_pct": 35.0, "data_year": 2022, "source": "ACS 2022 5-Year Estimates"},
        "land_use": {"max_parking_spaces": 80, "typical_zoning": "R-1", "max_building_height_stories": 50},
        "walkability": {"walk_score": 83.0, "transit_score": 72.0, "bike_score": 70.0, "walkability_score": 75.0}
    }
}

for city_slug, data in new_cities_data.items():
    cities[city_slug] = data["cities"]
    climate[city_slug] = data["climate"]
    construction_costs[city_slug] = data["construction"]
    demographics[city_slug] = data["demographics"]
    land_use[city_slug] = data["land_use"]
    walkability[city_slug] = data["walkability"]

save_json("cities.json", cities)
save_json("climate.json", climate)
save_json("construction_costs.json", construction_costs)
save_json("demographics.json", demographics)
save_json("land_use.json", land_use)
save_json("walkability.json", walkability)

print("Added 8 new cities!")
