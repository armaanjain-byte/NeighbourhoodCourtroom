"""Script to verify all cities in the dataset can be successfully loaded and costed.

Usage:
    python scripts/verify_cities.py
"""
import sys
import os
sys.path.insert(0, os.path.abspath("."))

from engine.state import create_initial_proposal
from tools.data_loader import DataLoader
from tools.cost_calculator import CostCalculator

def test_all_cities():
    data_loader = DataLoader()
    cost_calculator = CostCalculator(data_loader)
    
    cities = data_loader.list_available_cities()
    success_count = 0
    
    for city_slug in cities:
        print(f"\n--- Testing {city_slug} ---")
        try:
            proposal = create_initial_proposal(city_slug, green_space_pct=20.0, parking_spaces=100)
            costs = cost_calculator.calculate_cost_breakdown(proposal)
            print(f"Total Estimated Cost: ${sum(costs.values()):,.2f}")
            success_count += 1
        except Exception as e:
            print(f"ERROR testing {city_slug}: {e}")
            
    print(f"\nVerification complete. {success_count}/{len(cities)} cities passed.")

if __name__ == "__main__":
    test_all_cities()

    