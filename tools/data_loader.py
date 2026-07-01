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
    def __init__(self, data_root: Path | None = None, skip_validation: bool = False):
        if data_root is None:
            self.data_root = Path(__file__).resolve().parent.parent / "data"
        else:
            self.data_root = Path(data_root)
        
        self._cache: Dict[str, Dict[str, Any]] = {}
        
        # Validation schema defining expected keys and types for each file
        self._schema = {
            "cities.json": {
                "name": str, "state": str, "region": str,
                "city_tier": (int, float), "population": (int, float),
                "lat": (int, float), "lon": (int, float)
            },
            "climate.json": {
                "climate_zone": str, "climate_description": str,
                "annual_hdd": (int, float), "annual_cdd": (int, float),
                "heat_island_risk": (int, float), "flood_risk_score": (int, float),
                "recommended_min_green_cover_pct": (int, float),
                "solar_irradiance_kwh_per_sqm": (int, float),
                "avg_summer_temp_f": (int, float),
                "target_green_space_pct": (int, float),
                "data_sources": str
            },
            "construction_costs.json": {
                "city_index": (int, float),
                "residential_cost_per_sqft": (int, float),
                "commercial_cost_per_sqft": (int, float),
                "green_space_cost_per_sqft": (int, float),
                "parking_cost_per_space": (int, float)
            },
            "demographics.json": {
                "median_household_income": (int, float),
                "poverty_rate": (int, float),
                "population_density_per_sqmi": (int, float),
                "pct_age_65_plus": (int, float),
                "pct_with_disability": (int, float),
                "pct_renter_occupied": (int, float),
                "unemployment_rate": (int, float),
                "median_home_value": (int, float),
                "pct_no_vehicle": (int, float),
                "pct_non_white": (int, float),
                "target_community_center_sqft": (int, float),
                "target_affordable_housing_pct": (int, float),
                "data_year": (int, float),
                "source": str
            },
            "land_use.json": {
                "max_parking_spaces": (int, float),
                "typical_zoning": str,
                "max_building_height_stories": (int, float)
            },
            "walkability.json": {
                "walk_score": (int, float),
                "transit_score": (int, float),
                "bike_score": (int, float),
                "walkability_score": (int, float)
            }
        }
        
        # Only run validation if the data directory exists and skip_validation is False
        if not skip_validation and self.data_root.exists() and (self.data_root / "cities.json").exists():
            self.validate_city_data_completeness()

    def validate_city_data_completeness(self) -> None:
        """Validate that all cities in cities.json have complete and correctly typed data across all datasets."""
        try:
            cities_data = self._load_json("cities.json")
        except DatasetLoadError:
            return  # Can't validate if cities.json fails to load (caught elsewhere)

        city_slugs = list(cities_data.keys())
        
        for file_name, expected_schema in self._schema.items():
            try:
                file_data = self._load_json(file_name)
            except DatasetLoadError as e:
                raise DatasetLoadError(f"Validation failed: missing or malformed required file '{file_name}': {e}")
            
            for slug in city_slugs:
                if slug not in file_data:
                    # special case: construction_costs legacy nested format
                    if file_name == "construction_costs.json" and "cost_index_by_city" in file_data:
                        if slug not in file_data["cost_index_by_city"]:
                            raise DatasetLoadError(f"Validation failed: City '{slug}' is missing from {file_name}")
                        city_entry = file_data["cost_index_by_city"][slug]
                        # We won't strictly type check the legacy format here to keep validation simple
                        # The new flat format should be type checked.
                        continue
                    raise DatasetLoadError(f"Validation failed: City '{slug}' is missing from {file_name}")
                
                # Check types for normal flat records
                if file_name == "construction_costs.json" and "cost_index_by_city" in file_data:
                    continue # Skip legacy structure checking

                city_record = file_data[slug]
                if not isinstance(city_record, dict):
                    raise DatasetLoadError(f"Validation failed: City '{slug}' in {file_name} should be a dictionary")
                
                for key, expected_type in expected_schema.items():
                    if key not in city_record:
                        raise DatasetLoadError(f"Validation failed: City '{slug}' in {file_name} is missing required key '{key}'")
                    val = city_record[key]
                    if not isinstance(val, expected_type):
                        expected_name = expected_type.__name__ if isinstance(expected_type, type) else " or ".join(t.__name__ for t in expected_type)
                        actual_name = type(val).__name__
                        raise DatasetLoadError(f"Validation failed: City '{slug}' in {file_name} has invalid type for key '{key}'. Expected {expected_name}, got {actual_name}.")

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
                        "green_space_pct": 500000.0 * (float(raw_city.get("green_space_cost_per_sqft", 15)) / 15.0),
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

    def get_reference_standards(self, filename: str) -> dict:
        """Load a non-city-specific reference/standards JSON file using the same caching pattern.
        
        Parameters
        ----------
        filename : str
            The filename (e.g. 'finance_standards.json') relative to data_root.
            
        Returns
        -------
        dict
            The parsed standards data.
        """
        return self._load_json(filename)

