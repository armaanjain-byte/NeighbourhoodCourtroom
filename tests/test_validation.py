import pytest
import json
from pathlib import Path
from tools.data_loader import DataLoader, DatasetLoadError

@pytest.fixture
def valid_mock_data_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    cities = {"test_city": {"name": "Test", "state": "TS", "region": "Test", "city_tier": 1, "population": 1000, "lat": 1.0, "lon": 1.0}}
    climate = {"test_city": {"climate_zone": "1A", "climate_description": "Test", "annual_hdd": 1, "annual_cdd": 1, "heat_island_risk": 1, "flood_risk_score": 1, "recommended_min_green_cover_pct": 10.0, "solar_irradiance_kwh_per_sqm": 1.0, "avg_summer_temp_f": 80.0, "target_green_space_pct": 15.0, "data_sources": "Test"}}
    construction_costs = {"test_city": {"city_index": 100.0, "residential_cost_per_sqft": 100.0, "commercial_cost_per_sqft": 100.0, "green_space_cost_per_sqft": 10.0, "parking_cost_per_space": 1000.0}}
    demographics = {"test_city": {"median_household_income": 50000.0, "poverty_rate": 10.0, "population_density_per_sqmi": 1000.0, "pct_age_65_plus": 10.0, "pct_with_disability": 10.0, "pct_renter_occupied": 50.0, "unemployment_rate": 5.0, "median_home_value": 200000.0, "pct_no_vehicle": 10.0, "pct_non_white": 50.0, "target_community_center_sqft": 10000.0, "target_affordable_housing_pct": 20.0, "data_year": 2022, "source": "Test"}}
    land_use = {"test_city": {"max_parking_spaces": 100, "typical_zoning": "R1", "max_building_height_stories": 10}}
    walkability = {"test_city": {"walk_score": 50.0, "transit_score": 50.0, "bike_score": 50.0, "walkability_score": 50.0}}
    
    def write_json(name, data):
        with open(data_dir / name, "w") as f:
            json.dump(data, f)
            
    write_json("cities.json", cities)
    write_json("climate.json", climate)
    write_json("construction_costs.json", construction_costs)
    write_json("demographics.json", demographics)
    write_json("land_use.json", land_use)
    write_json("walkability.json", walkability)
    
    return data_dir

def test_validation_success(valid_mock_data_dir):
    # Should initialize without errors
    loader = DataLoader(data_root=valid_mock_data_dir, skip_validation=False)
    assert "test_city" in loader.list_available_cities()

def test_validation_missing_key(valid_mock_data_dir):
    # Remove a required key
    with open(valid_mock_data_dir / "walkability.json", "r") as f:
        data = json.load(f)
    del data["test_city"]["walkability_score"]
    with open(valid_mock_data_dir / "walkability.json", "w") as f:
        json.dump(data, f)
        
    with pytest.raises(DatasetLoadError, match="missing required key 'walkability_score'"):
        DataLoader(data_root=valid_mock_data_dir, skip_validation=False)

def test_validation_wrong_type(valid_mock_data_dir):
    # Change a key to the wrong type
    with open(valid_mock_data_dir / "climate.json", "r") as f:
        data = json.load(f)
    data["test_city"]["annual_hdd"] = "high" # Should be int/float
    with open(valid_mock_data_dir / "climate.json", "w") as f:
        json.dump(data, f)
        
    with pytest.raises(DatasetLoadError, match="has invalid type for key 'annual_hdd'"):
        DataLoader(data_root=valid_mock_data_dir, skip_validation=False)

def test_validation_missing_file(valid_mock_data_dir):
    # Delete a whole file
    (valid_mock_data_dir / "land_use.json").unlink()
    
    with pytest.raises(DatasetLoadError, match="missing or malformed required file 'land_use.json'"):
        DataLoader(data_root=valid_mock_data_dir, skip_validation=False)

def test_validation_missing_city_in_one_file(valid_mock_data_dir):
    # Add a new city to cities.json but not the others
    with open(valid_mock_data_dir / "cities.json", "r") as f:
        data = json.load(f)
    data["broken_city"] = data["test_city"].copy()
    with open(valid_mock_data_dir / "cities.json", "w") as f:
        json.dump(data, f)
        
    with pytest.raises(DatasetLoadError, match="Validation failed: City 'broken_city' is missing from climate.json"):
        DataLoader(data_root=valid_mock_data_dir, skip_validation=False)
