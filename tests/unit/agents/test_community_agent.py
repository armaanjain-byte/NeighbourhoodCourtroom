"""Tests for agents/community_agent.py.

Covers:
    - Poor community proposal (proposes boosting amenities, affordable housing)
    - Strong community proposal (accepts)
    - Low / High walkability impacts on score
    - Missing / Malformed dataset handling (rejects, scores 0)
    - Output validation
"""

import pytest
from typing import Any

from models.proposal import Proposal
from engine.state import create_initial_proposal
from tools.data_loader import DataLoader
from agents.community_agent import CommunityAgent


# ── Mocks ───────────────────────────────────────────────────────────────────

class MockDataLoader(DataLoader):
    def __init__(self, should_fail: bool = False, base_walkability: float = 50.0):
        self.should_fail = should_fail
        self.base_walkability = base_walkability
        self._cache = {}

    def get_demographics(self, city_name: str) -> dict[str, Any]:
        if self.should_fail:
            raise RuntimeError("Demographics data corrupted.")
        return {
            "target_community_center_sqft": 10000.0,
            "target_affordable_housing_pct": 20.0
        }

    def get_walkability(self, city_name: str) -> dict[str, float]:
        if self.should_fail:
            raise RuntimeError("Walkability data corrupted.")
        return {"walkability_score": self.base_walkability}

    def get_land_use(self, city_name: str) -> dict[str, float]:
        if self.should_fail:
            raise RuntimeError("Land use data corrupted.")
        return {"max_parking_spaces": 150}

    def load_city(self, city_name: str) -> dict:
        return {"name": "Phoenix", "population": 500_000}

    def get_reference_standards(self, filename: str) -> dict:
        """Return a minimal community standards dict for testing."""
        return {
            "community_facility_standards": {
                "sqft_per_capita": {
                    "minimum_sqft_per_1000_residents": 1000.0,
                    "recommended_sqft_per_1000_residents": 1500.0,
                    "source": "APA Planning Advisory Service Report #596 (2018)"
                },
                "program_area_minimums": {
                    "min_multipurpose_hall_sqft": 2000,
                    "source": "APA Community Facilities Design Standards (2018)"
                }
            },
            "ada_accessibility_requirements": {
                "parking_accessible_spaces": {
                    "pct_required_accessible_over_100_spaces": 4.0,
                    "source": "ADA Standards for Accessible Design (2010), Section 208"
                }
            },
            "affordable_housing_benchmarks": {
                "inclusionary_zoning_typical_ranges": {
                    "minimum_affordable_pct_typical": 10.0,
                    "moderate_affordable_pct_typical": 20.0,
                    "high_affordable_pct_typical": 30.0,
                    "source": "Furman Center, Inclusionary Zoning (2023)"
                }
            },
            "walkability_standards": {
                "walk_score_categories": {
                    "very_walkable_min": 70,
                    "somewhat_walkable_min": 50,
                    "source": "Walk Score methodology; EPA Smart Growth Program"
                }
            }
        }


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def proposal_poor_community() -> Proposal:
    # 0 sqft community center, 0% affordable housing, excessive housing
    return create_initial_proposal(
        "phoenix_az",
        community_center_sqft=0.0,
        affordable_housing_pct=10.0,
        housing_units=300, # Triggers density penalty
        parking_spaces=200, # Decreases walkability
        green_space_pct=10.0,
    )


@pytest.fixture
def proposal_strong_community() -> Proposal:
    # Meets all targets: 10000 sqft, 20% affordable, balanced housing/parking
    return create_initial_proposal(
        "phoenix_az",
        community_center_sqft=10000.0,
        affordable_housing_pct=20.0,
        housing_units=100,
        parking_spaces=100,
        green_space_pct=30.0,
    )


# ── Tests ───────────────────────────────────────────────────────────────────

class TestCommunityAgent:
    def test_agent_name(self) -> None:
        agent = CommunityAgent(MockDataLoader())
        assert agent.agent_name == "community"

    def test_poor_community_proposal(self, proposal_poor_community: Proposal) -> None:
        agent = CommunityAgent(MockDataLoader())
        output = agent.evaluate(proposal_poor_community, {})
        
        # community_ratio = 0
        # affordable_ratio = 0
        # base_walkability = 50. green = +5. parking = -20. effective = 35.0
        # raw_score = 0 + 0 + (35 * 0.3) - 15 (density penalty) = 10.5 - 15 = 0.0
        assert output.score < 50.0
        assert output.verdict == "modify"
        
        # Expected changes:
        # community_center_sqft min(0+2000, 10000) = 2000.0
        # affordable_housing_pct min(10+5, 20) = 15.0
        # parking_spaces max(0, 200 - 20) = 180
        # green_space_pct = 10.0 + 5.0 = 15.0
        changes = output.proposed_changes
        assert changes["community_center_sqft"] == 2000.0
        assert changes["affordable_housing_pct"] == 15.0
        assert changes["parking_spaces"] == 180
        assert changes["green_space_pct"] == 15.0
        
        assert "lacks adequate community amenities" in output.reasoning_and_evidence

        # Check standards_flags
        assert len(output.standards_flags) == 1
        flag = output.standards_flags[0]
        assert flag["standard_name"] == "HUD Affordable Housing"
        assert flag["passed"]

    def test_strong_community_proposal(self, proposal_strong_community: Proposal) -> None:
        agent = CommunityAgent(MockDataLoader())
        output = agent.evaluate(proposal_strong_community, {})
        
        # community_ratio = 1.0 -> 40
        # affordable_ratio = 1.0 -> 30
        # base_walkability = 50. green = +15. parking = -10. effective = 55.0
        # raw_score = 40 + 30 + 16.5 = 86.5
        assert output.score >= 85.0
        assert output.verdict == "accept"
        assert output.proposed_changes == {}
        assert "supports a high quality of life" in output.reasoning_and_evidence

        # Check standards_flags
        assert len(output.standards_flags) == 1
        flag = output.standards_flags[0]
        assert flag["standard_name"] == "HUD Affordable Housing"
        assert flag["passed"]

    def test_no_community_center(self, proposal_strong_community: Proposal) -> None:
        # Without a community center, walkability ratio is low (0.3) and cc_ratio is 0.
        proposal_strong_community.community_center_sqft = 0.0
        agent = CommunityAgent(MockDataLoader())
        output = agent.evaluate(proposal_strong_community, {})
        
        # cc_ratio = 0.0
        # housing_ratio = 1.0
        # walkability = 0.3
        # raw_score = (0 + 0.3 + 0.3*0.3) * 100 = 39.0
        assert output.verdict == "modify"
        
        # Since verdict is modify, it should propose small walkability bumps
        changes = output.proposed_changes
        assert "community_center_sqft" in changes

    def test_high_community_score(self, proposal_strong_community: Proposal) -> None:
        agent = CommunityAgent(MockDataLoader())
        output = agent.evaluate(proposal_strong_community, {})
        assert output.verdict == "accept"
        assert output.score > 90.0

    def test_missing_or_malformed_data(self, proposal_strong_community: Proposal) -> None:
        agent = CommunityAgent(MockDataLoader(should_fail=True))
        output = agent.evaluate(proposal_strong_community, {})
        
        assert output.score == 0.0
        assert output.verdict == "reject"
        assert output.proposed_changes == {}
        assert "Failed to load community-related data" in output.reasoning_and_evidence

    def test_personality_and_risk_tolerance_in_system_instruction(self, proposal_strong_community: Proposal) -> None:
        """Verify personality_brief and risk_tolerance are defined, non-empty,
        and included in the system_instruction passed to the LLM provider."""
        from unittest.mock import MagicMock
        agent = CommunityAgent(MockDataLoader())
        assert agent.personality_brief
        assert agent.risk_tolerance
        
        mock_provider = MagicMock()
        mock_provider.generate_structured.return_value = {
            "score": 95.0, "verdict": "accept", "proposed_changes": {},
            "tension": "Mock tension statement.",
            "position": "Pos", "reasoning": "Res", "evidence": [],
            "confidence": 0.9, "objections": [], "supports": []
        }
        agent.llm_provider = mock_provider
        
        agent.generate_opinion(proposal_strong_community, {})
        
        mock_provider.generate_structured.assert_called_once()
        _, kwargs = mock_provider.generate_structured.call_args
        sys_inst = kwargs["system_instruction"]
        assert agent.personality_brief in sys_inst
        assert agent.risk_tolerance in sys_inst

    def test_missing_tension_field_triggers_fallback(self, proposal_strong_community: Proposal) -> None:
        """Test that a mocked LLM response missing the required tension field triggers deterministic fallback."""
        from unittest.mock import MagicMock
        agent = CommunityAgent(MockDataLoader())
        mock_provider = MagicMock()
        # Omit 'tension'
        mock_provider.generate_structured.return_value = {
            "score": 95.0, "verdict": "accept", "proposed_changes": {},
            "position": "Pos", "reasoning": "Res", "evidence": [],
            "confidence": 0.9, "objections": [], "supports": []
        }
        agent.llm_provider = mock_provider
        
        opinion = agent.generate_opinion(proposal_strong_community, {})
        # The new structured fallback produces domain-specific content, not the old generic string.
        assert opinion.is_fallback is True
        # The position should contain real community data (housing %, sqft/unit, or target reference)
        assert (
            "%" in opinion.position
            or "housing" in opinion.position.lower()
            or "community" in opinion.position.lower()
            or "sqft" in opinion.position.lower()
        )

    def test_incremental_fallback_step(self) -> None:
        agent = CommunityAgent(MockDataLoader())
        proposal = create_initial_proposal("phoenix_az", community_center_sqft=5000.0, affordable_housing_pct=10.0)
        output = agent.evaluate(proposal, {})
        assert output.proposed_changes["community_center_sqft"] == 7000.0

    def test_incremental_fallback_close_to_target(self) -> None:
        agent = CommunityAgent(MockDataLoader())
        proposal = create_initial_proposal("phoenix_az", community_center_sqft=9000.0, affordable_housing_pct=10.0)
        output = agent.evaluate(proposal, {})
        assert output.proposed_changes["community_center_sqft"] == 10000.0

    def test_incremental_fallback_above_target(self) -> None:
        agent = CommunityAgent(MockDataLoader())
        proposal = create_initial_proposal("phoenix_az", community_center_sqft=15000.0, affordable_housing_pct=10.0)
        output = agent.evaluate(proposal, {})
        assert output.proposed_changes["community_center_sqft"] == 15000.0



    def test_community_agent_catches_adversarial_affordable_housing(self) -> None:
        agent = CommunityAgent(MockDataLoader())
        proposal = create_initial_proposal("phoenix_az", affordable_housing_pct=2.0)
        output = agent.evaluate(proposal, {})
        
        assert output.score <= 10.0
        assert output.verdict == "modify"
        assert output.proposed_changes["affordable_housing_pct"] == 20.0
        assert "egregiously violates the HUD/Furman Center standard" in output.reasoning_and_evidence




# ── Tests for get_planning_standards tool ─────────────────────────────

def test_get_planning_standards_all_categories():
    """get_planning_standards('all') returns all top-level categories (excluding _ prefixed)."""
    agent = CommunityAgent(MockDataLoader())
    result = agent.execute_tool_call("get_planning_standards", {"category": "all"})
    assert "community_facility_standards" in result
    assert "ada_accessibility_requirements" in result
    assert "affordable_housing_benchmarks" in result
    assert "walkability_standards" in result


def test_get_planning_standards_community_facility():
    """get_planning_standards returns APA sqft per capita minimums."""
    agent = CommunityAgent(MockDataLoader())
    result = agent.execute_tool_call("get_planning_standards", {"category": "community_facility_standards"})
    assert "community_facility_standards" in result
    assert "ada_accessibility_requirements" not in result
    sqft = result["community_facility_standards"]["sqft_per_capita"]
    assert sqft["minimum_sqft_per_1000_residents"] == 1000.0
    assert sqft["recommended_sqft_per_1000_residents"] == 1500.0


def test_get_planning_standards_affordable_housing():
    """get_planning_standards returns HUD/Furman Center inclusionary zoning benchmarks."""
    agent = CommunityAgent(MockDataLoader())
    result = agent.execute_tool_call("get_planning_standards", {"category": "affordable_housing_benchmarks"})
    assert "affordable_housing_benchmarks" in result
    ranges = result["affordable_housing_benchmarks"]["inclusionary_zoning_typical_ranges"]
    assert ranges["minimum_affordable_pct_typical"] == 10.0
    assert ranges["moderate_affordable_pct_typical"] == 20.0
    assert ranges["high_affordable_pct_typical"] == 30.0


def test_get_planning_standards_ada():
    """get_planning_standards returns ADA parking accessibility requirements."""
    agent = CommunityAgent(MockDataLoader())
    result = agent.execute_tool_call("get_planning_standards", {"category": "ada_accessibility_requirements"})
    assert "ada_accessibility_requirements" in result
    ada = result["ada_accessibility_requirements"]["parking_accessible_spaces"]
    assert ada["pct_required_accessible_over_100_spaces"] == 4.0
