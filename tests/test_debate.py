"""Tests for engine/debate.py — Debate Engine.

Covers:
    - Debate orchestration flow
    - No conflicts handling
    - Low conflicts handling
    - Medium conflicts handling
    - High conflicts handling
    - Locked parameters handling
    - Multiple agents & multiple parameters
    - End-to-End integration test
"""

import pytest

from models.proposal import Proposal
from models.agent_output import AgentOutput
from engine.state import create_initial_proposal, apply_human_override
from engine.debate import run_debate_round
from tools.cost_calculator import CostCalculator

class MockDataLoader:
    def get_construction_costs(self, city_slug: str) -> dict:
        return {"city_index": 1.0}

class MockCostCalculator(CostCalculator):
    def __init__(self):
        super().__init__(MockDataLoader())
    
    def calculate_estimated_cost(self, proposal: Proposal) -> float:
        # Simple linear formula for testing
        return (proposal.housing_units * 1000) + (proposal.parking_spaces * 500) + (proposal.green_space_pct * 100)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_output(agent: str, changes: dict[str, float]) -> AgentOutput:
    """Shorthand to create an AgentOutput for testing."""
    return AgentOutput(
        agent_name=agent,
        score=50.0,
        verdict="modify",
        proposed_changes=changes,
        reasoning_and_evidence="test reasoning",
    )


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def base_proposal() -> Proposal:
    return create_initial_proposal("phoenix_az", green_space_pct=20.0, parking_spaces=100)


# ── Tests ───────────────────────────────────────────────────────────────────

class TestRunDebateRound:
    def test_no_conflicts(self, base_proposal: Proposal) -> None:
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 25.0}),
            "climate": _make_output("climate", {"parking_spaces": 90.0}),
        }
        
        round_record, updated = run_debate_round(base_proposal, outputs, round_number=1)
        
        # Verify round record
        assert round_record.round_number == 1
        assert len(round_record.detected_conflicts) == 0
        assert "2 parameter(s) auto-resolved" in round_record.engine_summary
        
        # Verify updated state
        assert updated.version == base_proposal.version + 1
        assert updated.green_space_pct == 25.0
        assert updated.parking_spaces == 90
        
        # Verify audit log
        assert len(updated.change_log) == 2
        assert updated.change_log[0]["actor"] == "engine"

    def test_low_conflict(self, base_proposal: Proposal) -> None:
        # 25.0 vs 26.0 on 26.0 max -> delta is 1.0 / 26.0 = 3.8% (LOW)
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 25.0}),
            "climate": _make_output("climate", {"green_space_pct": 26.0}),
        }
        
        round_record, updated = run_debate_round(base_proposal, outputs)
        
        assert len(round_record.detected_conflicts) == 1
        assert round_record.detected_conflicts[0].disagreement_severity == "low"
        
        # Arithmetic mean of 25 and 26 = 25.5
        assert updated.green_space_pct == 25.5

    def test_medium_conflict(self, base_proposal: Proposal) -> None:
        # 100 vs 80 -> delta is 20% (MEDIUM)
        outputs = {
            "finance": _make_output("finance", {"parking_spaces": 100.0}),
            "climate": _make_output("climate", {"parking_spaces": 80.0}),
        }
        
        round_record, updated = run_debate_round(base_proposal, outputs)
        
        assert len(round_record.detected_conflicts) == 1
        assert round_record.detected_conflicts[0].disagreement_severity == "medium"
        
        # Weighted mean: finance(0.4)*100 + climate(0.3)*80 = 40 + 24 = 64
        # Total weight = 0.7 -> 64 / 0.7 = 91.428... -> coerced to int -> 91
        assert updated.parking_spaces == int(64.0 / 0.7)

    def test_high_conflict(self, base_proposal: Proposal) -> None:
        # 20.0 vs 50.0 -> delta is 60% (HIGH)
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 20.0}),
            "climate": _make_output("climate", {"green_space_pct": 50.0}),
        }
        
        round_record, updated = run_debate_round(base_proposal, outputs)
        
        assert len(round_record.detected_conflicts) == 1
        assert round_record.detected_conflicts[0].disagreement_severity == "high"
        
        # High conflict is NOT auto-resolved
        assert updated.green_space_pct == 20.0 # unchanged
        assert updated.version == base_proposal.version # unchanged version
        assert "require human review" in round_record.engine_summary

    def test_locked_parameter(self, base_proposal: Proposal) -> None:
        locked_proposal = apply_human_override(base_proposal, "green_space_pct", 30.0)
        
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 10.0, "parking_spaces": 90.0}),
        }
        
        round_record, updated = run_debate_round(locked_proposal, outputs)
        
        # Green space is locked at 30.0
        assert updated.green_space_pct == 30.0
        # Parking spaces goes through
        assert updated.parking_spaces == 90
        
        # Audit log tracks the lock and the change
        # (The skipped attempt is logged in the debate round summary, not the state change log,
        # because the resolution engine filters it out before apply_changes)
        assert len(updated.change_log) == 2 # 1 human override + 1 from debate round
        
        assert "skipped (human-locked)" in round_record.engine_summary

    def test_multiple_agents_and_parameters(self, base_proposal: Proposal) -> None:
        outputs = {
            "finance": _make_output("finance", {
                "green_space_pct": 30.0,
                "parking_spaces": 50.0, # high conflict with 100
                "housing_units": 200.0, # unopposed
            }),
            "climate": _make_output("climate", {
                "green_space_pct": 29.0, # low conflict with 30
                "parking_spaces": 100.0,
            }),
            "community": _make_output("community", {
                "affordable_housing_pct": 25.0, # unopposed
            })
        }
        
        round_record, updated = run_debate_round(base_proposal, outputs)
        
        # Detected conflicts: green_space_pct (low), parking_spaces (high)
        assert len(round_record.detected_conflicts) == 2
        
        # Housing units -> unopposed -> 200
        assert updated.housing_units == 200
        # Affordable housing pct -> unopposed -> 25.0
        assert updated.affordable_housing_pct == 25.0
        # Green space pct -> low -> mean of 30 and 29 -> 29.5
        assert updated.green_space_pct == 29.5
        # Parking spaces -> high -> ignored -> original 100
        assert updated.parking_spaces == 100

    def test_estimated_cost_proposals_ignored(self, base_proposal: Proposal) -> None:
        outputs = {
            "rogue_agent": _make_output("rogue_agent", {"estimated_cost": 99_000_000.0, "housing_units": 200.0})
        }
        
        calc = MockCostCalculator()
        round_record, updated = run_debate_round(base_proposal, outputs, cost_calculator=calc)
        
        # Housing units changed
        assert updated.housing_units == 200
        
        # Cost should be derived from housing units (200*1000 + 100*500 + 20.0*100 = 252000), not the rogue agent's proposal
        assert updated.estimated_cost == 252000.0
        
        # Summary should indicate housing units auto-resolved
        assert "housing_units" in round_record.engine_summary

    def test_end_to_end_integration(self) -> None:
        """Full end to end test of State + Conflict + Debate engines."""
        # 1. create_initial_proposal
        proposal = create_initial_proposal(
            city_slug="detroit_mi",
            green_space_pct=20.0,
            housing_units=100
        )
        assert proposal.version == 1
        
        # 2. agent outputs
        outputs = {
            "finance": _make_output("finance", {
                "housing_units": 150.0, # vs 120 -> 20% delta -> medium
                "green_space_pct": 20.0, # unopposed
            }),
            "climate": _make_output("climate", {
                "housing_units": 120.0,
            }),
            "community": _make_output("community", {
                "community_center_sqft": 6000.0, # unopposed
            })
        }
        
        # 3-7. run_debate_round covers detect, resolve, apply, and build
        calc = MockCostCalculator()
        debate_round, updated = run_debate_round(proposal, outputs, round_number=1, cost_calculator=calc)
        
        # 8. Verify
        # Housing units: finance(0.4)*150 + climate(0.3)*120 = 60 + 36 = 96
        # Total weight: 0.7. 96 / 0.7 = 137.14 -> 137
        assert updated.housing_units == 137
        assert updated.green_space_pct == 20.0
        assert updated.community_center_sqft == 6000.0
        
        # 9. Verify Cost Recalculation
        # Expected: (137*1000) + (150*500) + (20.0*100) = 137000 + 75000 + 2000 = 214000
        assert updated.estimated_cost == 214000.0
        
        # Version incremented
        assert updated.version == 2
        
        # Conflict summary
        assert "housing_units → 137.14" in debate_round.engine_summary or "housing_units → 137" in debate_round.engine_summary
        assert "community_center_sqft → 6000.0" in debate_round.engine_summary
        
        # Audit log tracks the changes
        assert len(updated.change_log) == 3 # community center, housing units, and estimated_cost
        log_params = {entry["parameter"] for entry in updated.change_log}
        assert log_params == {"housing_units", "community_center_sqft", "estimated_cost"}
        # green_space_pct was 20.0 and proposed 20.0, so it's a no-op and skipped
