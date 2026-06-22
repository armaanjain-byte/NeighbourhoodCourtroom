import os

TOOLS_DIR = "tools"
TESTS_DIR = "tests"

DATA_LOADER_CODE = '''import json
import os
from pathlib import Path
from typing import Any, Dict, List

class CityNotFoundError(RuntimeError):
    """Raised when a requested city is not found in the datasets."""
    pass

class DatasetLoadError(RuntimeError):
    """Raised when a dataset file cannot be loaded or parsed."""
    pass

class EmptyDatasetError(RuntimeError):
    """Raised when a dataset file exists but is empty."""
    pass


class DataLoader:
    """Local dataset query interface.
    
    Parameters
    ----------
    data_root : Path, optional
        Directory containing the JSON data files. Defaults to the project's 'data/' folder.
    """
    def __init__(self, data_root: Path | None = None):
        if data_root is None:
            self.data_root = Path(__file__).resolve().parent.parent / "data"
        else:
            self.data_root = Path(data_root)
        
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _load_json(self, filename: str) -> Dict[str, Any]:
        """Lazy load and cache a JSON file."""
        if filename in self._cache:
            return self._cache[filename]
            
        file_path = self.data_root / filename
        if not file_path.exists():
            raise DatasetLoadError(f"Dataset file not found: {file_path}")
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    raise EmptyDatasetError(f"Dataset is empty: {file_path}")
                data = json.loads(content)
        except json.JSONDecodeError as e:
            raise DatasetLoadError(f"Malformed JSON in {filename}: {e}")
        except EmptyDatasetError:
            raise
        except Exception as e:
            raise DatasetLoadError(f"Error loading {filename}: {e}")
            
        if not data:
            raise EmptyDatasetError(f"Dataset contains no data: {filename}")

        self._cache[filename] = data
        return data

    def _get_city_data(self, filename: str, city_name: str) -> Dict[str, Any]:
        """Helper to get specific city data from a dataset."""
        data = self._load_json(filename)
        
        # construction_costs is keyed differently in architecture:
        # { "cost_index_by_city": { "phoenix_az": 0.89 }, "base_costs_per_sqft": {...} }
        if filename == "construction_costs.json":
            if "cost_index_by_city" not in data:
                raise DatasetLoadError(f"Unexpected format in {filename}")
            if city_name not in data["cost_index_by_city"]:
                raise CityNotFoundError(f"City '{city_name}' not found in {filename}")
            
            return {
                "city_index": data["cost_index_by_city"][city_name],
                "base_costs": data.get("base_costs_per_sqft", {}),
                "soft_cost_multiplier": data.get("soft_cost_multiplier", 1.0),
                "contingency_multiplier": data.get("contingency_multiplier", 1.0)
            }
        
        if city_name not in data:
            raise CityNotFoundError(f"City '{city_name}' not found in {filename}")
            
        return data[city_name]

    def load_city(self, city_name: str) -> Dict[str, Any]:
        """Return the master city record."""
        return self._get_city_data("cities.json", city_name)

    def get_demographics(self, city_name: str) -> Dict[str, Any]:
        """Return the demographic profile."""
        return self._get_city_data("demographics.json", city_name)

    def get_climate(self, city_name: str) -> Dict[str, Any]:
        """Return the climate profile."""
        return self._get_city_data("climate.json", city_name)

    def get_walkability(self, city_name: str) -> Dict[str, Any]:
        """Return the walkability and accessibility profile."""
        return self._get_city_data("walkability.json", city_name)

    def get_land_use(self, city_name: str) -> Dict[str, Any]:
        """Return the zoning and land-use constraints."""
        return self._get_city_data("land_use.json", city_name)

    def get_construction_costs(self, city_name: str) -> Dict[str, Any]:
        """Return the cost indices and base costs."""
        return self._get_city_data("construction_costs.json", city_name)

    def list_available_cities(self) -> List[str]:
        """List all city slugs present in cities.json."""
        data = self._load_json("cities.json")
        return list(data.keys())
'''

TEST_DATA_LOADER_CODE = '''import pytest
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
'''

with open(f"{TOOLS_DIR}/data_loader.py", "w", encoding="utf-8") as f:
    f.write(DATA_LOADER_CODE)

with open(f"{TESTS_DIR}/test_data_loader.py", "w", encoding="utf-8") as f:
    f.write(TEST_DATA_LOADER_CODE)

print("Scaffolded data_loader and tests.")
