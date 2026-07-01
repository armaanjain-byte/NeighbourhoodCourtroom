import sys
sys.path.append('.')
from tools.cost_calculator import CostCalculator
from tests.test_climate_agent import *
class MockLoader(MockDataLoader):
    def get_construction_costs(self, city_name: str) -> dict:
        return {'city_index': 1.0, 'base_costs': {'housing_unit': 250000.0}, 'soft_cost_multiplier': 1.0, 'contingency_multiplier': 1.0}
agent=ClimateAgent(MockLoader())
p=create_initial_proposal('phoenix_az', green_space_pct=0.0, parking_spaces=0, housing_units=100, community_center_sqft=0.0)
calc=CostCalculator(agent.data_loader)
c=calc.calculate_estimated_cost(p)
print('current_cost:', c)
changes={'green_space_pct': 10.0, 'parking_spaces': 0}
p2=p.model_copy(update=changes)
n=calc.calculate_estimated_cost(p2)
print('new_cost:', n)
print('delta:', n - c)
out = agent.evaluate(p, {})
print('agent output:', out.proposed_changes, out.reasoning_and_evidence)
