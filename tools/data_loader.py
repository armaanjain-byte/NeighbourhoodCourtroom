import json
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
        
        # construction_costs.json may use either:
        #   (a) flat format: { "phoenix_az": { "city_index": 92.0, ... }, ... }
        #   (b) legacy format: { "cost_index_by_city": { "phoenix_az": 0.89 }, ... }
        if filename == "construction_costs.json":
            # Prefer flat format if the top-level keys look like city slugs
            if city_name in data:
                raw_city = data[city_name]
                return {
                    "city_index": float(raw_city.get("city_index", 100.0)),
                    "base_costs": {
                        "housing_unit": float(raw_city.get("residential_cost_per_sqft", 150)) * 1000.0,
                        "parking_space": float(raw_city.get("parking_cost_per_space", 25000)),
                        "green_space_pct": float(raw_city.get("green_space_cost_per_sqft", 15)) * 43560.0,
                        "community_center_sqft": float(raw_city.get("commercial_cost_per_sqft", 350.0)),
                    },
                    "soft_cost_multiplier": 1.1,
                    "contingency_multiplier": 1.1,
                }
            # Fall back to legacy nested format
            if "cost_index_by_city" in data:
                if city_name not in data["cost_index_by_city"]:
                    raise CityNotFoundError(f"City '{city_name}' not found in {filename}")
                return {
                    "city_index": data["cost_index_by_city"][city_name],
                    "base_costs": data.get("base_costs_per_sqft", {}),
                    "soft_cost_multiplier": data.get("soft_cost_multiplier", 1.0),
                    "contingency_multiplier": data.get("contingency_multiplier", 1.0),
                }
            raise DatasetLoadError(f"Malformed structure in {filename}")
        
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
