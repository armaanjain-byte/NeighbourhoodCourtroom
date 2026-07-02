import pytest
import json
from pathlib import Path
from tools.data_loader import DataLoader, CityNotFoundError, DatasetLoadError, EmptyDatasetError

@pytest.fixture
def mock_data_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    # Create valid dummy files
    cities = {"phoenix_az": {"name": "Phoenix, AZ"}}
    demographics = {"phoenix_az": {"poverty_rate": 0.17}}
    climate = {"phoenix_az": {"climate_zone": "2B"}}
    walkability = {"phoenix_az": {"walk_score": 41}}
    land_use = {"phoenix_az": {"typical_far": 2.0}}
    construction_costs = {
        "cost_index_by_city": {"phoenix_az": 0.89},
        "base_costs_per_sqft": {"park": 10},
        "soft_cost_multiplier": 1.2
    }
    
    with open(data_dir / "cities.json", "w") as f:
        json.dump(cities, f)
    with open(data_dir / "demographics.json", "w") as f:
        json.dump(demographics, f)
    with open(data_dir / "climate.json", "w") as f:
        json.dump(climate, f)
    with open(data_dir / "walkability.json", "w") as f:
        json.dump(walkability, f)
    with open(data_dir / "land_use.json", "w") as f:
        json.dump(land_use, f)
    with open(data_dir / "construction_costs.json", "w") as f:
        json.dump(construction_costs, f)
        
    # Malformed file
    with open(data_dir / "malformed.json", "w") as f:
        f.write("{bad json")
        
    # Empty file
    with open(data_dir / "empty.json", "w") as f:
        f.write("")
        
    # Empty JSON object
    with open(data_dir / "empty_obj.json", "w") as f:
        f.write("{}")
        
    return data_dir

@pytest.fixture
def loader(mock_data_dir):
    return DataLoader(data_root=mock_data_dir, skip_validation=True)

def test_successful_loads(loader):
    assert loader.load_city("phoenix_az")["name"] == "Phoenix, AZ"
    assert loader.get_demographics("phoenix_az")["poverty_rate"] == 0.17
    assert loader.get_climate("phoenix_az")["climate_zone"] == "2B"
    assert loader.get_walkability("phoenix_az")["walk_score"] == 41
    assert loader.get_land_use("phoenix_az")["typical_far"] == 2.0
    
    costs = loader.get_construction_costs("phoenix_az")
    assert costs["city_index"] == 0.89
    assert costs["base_costs"]["park"] == 10
    
    assert "phoenix_az" in loader.list_available_cities()

def test_missing_city(loader):
    with pytest.raises(CityNotFoundError):
        loader.load_city("missing_city")

def test_construction_costs_missing_city(loader):
    with pytest.raises(CityNotFoundError):
        loader.get_construction_costs("missing_city")

def test_malformed_dataset(loader):
    with pytest.raises(DatasetLoadError):
        loader._load_json("malformed.json")

def test_empty_dataset(loader):
    with pytest.raises(EmptyDatasetError):
        loader._load_json("empty.json")
        
def test_empty_json_object(loader):
    with pytest.raises(EmptyDatasetError):
        loader._load_json("empty_obj.json")

def test_missing_dataset_file(loader):
    with pytest.raises(DatasetLoadError):
        loader._load_json("nonexistent.json")

def test_cache_behavior(loader, mock_data_dir):
    # First load
    data = loader.load_city("phoenix_az")
    assert "cities.json" in loader._cache
    
    # Delete file to prove we use cache
    (mock_data_dir / "cities.json").unlink()
    
    # Second load should succeed from cache
    data2 = loader.load_city("phoenix_az")
    assert data == data2
    
def test_construction_costs_malformed(mock_data_dir, loader):
    with open(mock_data_dir / "construction_costs.json", "w") as f:
        json.dump({"wrong_key": {}}, f)
        
    loader._cache.pop("construction_costs.json", None) # clear cache
    with pytest.raises(DatasetLoadError):
        loader.get_construction_costs("phoenix_az")

def test_construction_costs_flat_format(mock_data_dir, loader):
    # Test flat format parsing and mapping (e.g., residential_cost_per_sqft to housing_unit * 1000.0)
    flat_format_data = {
        "austin_tx": {
            "city_index": 94.0,
            "residential_cost_per_sqft": 140.0,
            "parking_cost_per_space": 23000.0,
            "green_space_cost_per_sqft": 10.0,
            "commercial_cost_per_sqft": 300.0
        }
    }
    with open(mock_data_dir / "construction_costs.json", "w") as f:
        json.dump(flat_format_data, f)
        
    loader._cache.pop("construction_costs.json", None)
    costs = loader.get_construction_costs("austin_tx")
    
    assert costs["city_index"] == 94.0
    assert costs["base_costs"]["housing_unit"] == 140000.0  # 140.0 * 1000.0
    assert costs["base_costs"]["parking_space"] == 23000.0
    assert costs["base_costs"]["green_space_pct"] == pytest.approx(333333.33333)
    assert costs["base_costs"]["community_center_sqft"] == 300.0

def test_construction_costs_legacy_format(mock_data_dir, loader):
    # Test legacy format parsing explicitly
    legacy_format_data = {
        "cost_index_by_city": {"seattle_wa": 1.18},
        "base_costs_per_sqft": {"legacy_park": 15},
        "soft_cost_multiplier": 1.3
    }
    with open(mock_data_dir / "construction_costs.json", "w") as f:
        json.dump(legacy_format_data, f)
        
    loader._cache.pop("construction_costs.json", None)
    costs = loader.get_construction_costs("seattle_wa")
    
    assert costs["city_index"] == 1.18
    assert costs["base_costs"]["legacy_park"] == 15
    assert costs["soft_cost_multiplier"] == 1.3
