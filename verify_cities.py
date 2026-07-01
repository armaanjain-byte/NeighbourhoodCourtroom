from engine.state import create_initial_proposal
from tools.data_loader import DataLoader
from tools.cost_calculator import CostCalculator

def test_city(city):
    print(f"\n--- Testing {city} ---")
    data_loader = DataLoader()
    cost_calculator = CostCalculator(data_loader)
    proposal = create_initial_proposal(city, green_space_pct=20.0, parking_spaces=100)
    
    costs = cost_calculator.calculate_cost_breakdown(proposal)
    print(costs)

test_city("san_francisco_ca")
test_city("columbus_oh")
