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
    return DataLoader(data_root=mock_data_dir)

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
