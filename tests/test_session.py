"""Tests for engine/session.py — Session Engine.

Covers:
    - Session creation and initial state
    - Running multiple debate rounds
    - Handling high conflicts (WAITING_FOR_JUDGE transition)
    - Applying human overrides and state progression
    - Verdict generation and unresolved conflict detection
    - Output history retrieval
"""

import pytest

from unittest.mock import patch

from models.proposal import Proposal
from models.agent_output import AgentOutput
from models.agent_opinion import AgentOpinion
from agents.base_agent import BaseAgent
from engine.state import create_initial_proposal
from engine.session import create_session, CourtroomSession
from tools.cost_calculator import CostCalculator


# ── Mocks ───────────────────────────────────────────────────────────────────

class MockDataLoader:
    def get_construction_costs(self, city_name: str) -> dict:
        return {"city_index": 1.0}


class MockCostCalculator(CostCalculator):
    def __init__(self):
        super().__init__(MockDataLoader())  # type: ignore
    
    def calculate_estimated_cost(self, proposal: Proposal) -> float:
        return 20_000_000.0


class MockAgent(BaseAgent):
    def __init__(self, name: str, changes: dict):
        self._name = name
        self.changes = changes

    @property
    def agent_name(self) -> str:
        return self._name

    def evaluate(self, proposal: Proposal, context: dict) -> AgentOutput:
        return self.build_output(
            score=50.0,
            verdict="modify",
            changes=self.changes,
            reasoning="Test."
        )


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def initial_proposal() -> Proposal:
    return create_initial_proposal("phoenix_az", green_space_pct=20.0, parking_spaces=100)


@pytest.fixture
def cost_calculator() -> CostCalculator:
    return MockCostCalculator()


# ── Tests ───────────────────────────────────────────────────────────────────

class TestCourtroomSession:
    def test_create_session(self, initial_proposal: Proposal) -> None:
        session = create_session(initial_proposal)
        assert session.status == "CREATED"
        assert len(session.debate_rounds) == 0
        assert len(session.override_history) == 0
        assert session.get_current_state().version == 1

    def test_run_single_round(self, initial_proposal: Proposal, cost_calculator: CostCalculator) -> None:
        session = create_session(initial_proposal)
        
        # Low conflict so it auto-resolves
        agent1 = MockAgent("agent1", {"green_space_pct": 21.0})
        agent2 = MockAgent("agent2", {"green_space_pct": 22.0})
        
        round_record = session.run_round([agent1, agent2], {}, cost_calculator)
        
        assert session.status == "IN_PROGRESS"
        assert len(session.get_debate_history()) == 1
        assert session.get_current_state().version == 2
        assert round_record.round_number == 1

    def test_run_multiple_rounds(self, initial_proposal: Proposal, cost_calculator: CostCalculator) -> None:
        session = create_session(initial_proposal)
        
        agent1 = MockAgent("agent1", {"parking_spaces": 95.0})
        session.run_round([agent1], {}, cost_calculator)
        assert session.get_current_state().version == 2
        
        agent2 = MockAgent("agent2", {"housing_units": 105.0})
        session.run_round([agent2], {}, cost_calculator)
        assert session.get_current_state().version == 3
        
        assert len(session.get_debate_history()) == 2

    def test_high_conflict_waits_for_judge(self, initial_proposal: Proposal, cost_calculator: CostCalculator) -> None:
        session = create_session(initial_proposal)
        
        # 10.0 vs 80.0 is a high conflict on green space
        agent1 = MockAgent("agent1", {"green_space_pct": 10.0})
        agent2 = MockAgent("agent2", {"green_space_pct": 80.0})
        
        session.run_round([agent1, agent2], {}, cost_calculator)
        
        assert session.status == "WAITING_FOR_JUDGE"
        
        # Cannot run round while waiting
        with pytest.raises(ValueError, match="Cannot run debate round"):
            session.run_round([agent1], {}, cost_calculator)

    def test_apply_override_resumes_session(self, initial_proposal: Proposal, cost_calculator: CostCalculator) -> None:
        session = create_session(initial_proposal)
        
        # Trigger high conflict
        agent1 = MockAgent("agent1", {"green_space_pct": 10.0})
        agent2 = MockAgent("agent2", {"green_space_pct": 80.0})
        session.run_round([agent1, agent2], {}, cost_calculator)
        
        assert session.status == "WAITING_FOR_JUDGE"
        
        # Judge overrides and locks it
        session.apply_override("green_space_pct", 45.0)
        
        assert session.status == "IN_PROGRESS"
        assert session.get_current_state().green_space_pct == 45.0
        assert "green_space_pct" in session.get_current_state().human_locks
        assert len(session.override_history) == 1
        
        # Can now run another round
        agent3 = MockAgent("agent1", {"parking_spaces": 50.0}) # Attempt different param
        session.run_round([agent3], {}, cost_calculator)
        assert len(session.debate_rounds) == 2

    def test_locked_parameters_enforced_in_future_rounds(self, initial_proposal: Proposal, cost_calculator: CostCalculator) -> None:
        session = create_session(initial_proposal)
        
        session.apply_override("green_space_pct", 40.0)
        assert "green_space_pct" in session.get_current_state().human_locks
        
        agent = MockAgent("rogue", {"green_space_pct": 10.0})
        session.run_round([agent], {}, cost_calculator)
        
        # Agent's attempt should be silently skipped due to lock
        assert session.get_current_state().green_space_pct == 40.0

    def test_generate_verdict(self, initial_proposal: Proposal, cost_calculator: CostCalculator) -> None:
        session = create_session(initial_proposal)
        
        agent1 = MockAgent("agent1", {"parking_spaces": 80.0})
        session.run_round([agent1], {}, cost_calculator)
        
        session.apply_override("housing_units", 200.0)
        
        verdict = session.generate_verdict()
        
        assert session.status == "COMPLETED"
        assert verdict["total_rounds"] == 1
        assert "final_proposal" in verdict
        assert verdict["final_proposal"].housing_units == 200
        assert verdict["final_proposal"].parking_spaces == 80
        assert "override" in verdict["audit_summary"] or "overrides" in verdict["audit_summary"]
        assert verdict["unresolved_conflicts"] == []
        
        # Cannot apply override when completed
        with pytest.raises(ValueError, match="Cannot apply overrides"):
            session.apply_override("green_space_pct", 50.0)

    def test_generate_verdict_with_unresolved_conflicts(self, initial_proposal: Proposal, cost_calculator: CostCalculator) -> None:
        session = create_session(initial_proposal)
        
        # Generate high conflict
        agent1 = MockAgent("agent1", {"green_space_pct": 10.0})
        agent2 = MockAgent("agent2", {"green_space_pct": 90.0})
        session.run_round([agent1, agent2], {}, cost_calculator)
        
        assert session.status == "WAITING_FOR_JUDGE"
        
        # Admin decides to just complete the session anyway without overriding
        verdict = session.generate_verdict()
        
        assert session.status == "COMPLETED"
        assert "green_space_pct" in verdict["unresolved_conflicts"]

    @patch.object(MockAgent, 'generate_opinion')
    def test_llm_opinions_feed_conflict_engine(self, mock_generate_opinion, initial_proposal: Proposal, cost_calculator: CostCalculator) -> None:
        """Verify that LLM generated opinions correctly override the deterministic evaluate() fallback
        and are consumed by the conflict resolution engine."""
        session = create_session(initial_proposal)
        
        # The mock agent's deterministic evaluate() would return green_space_pct: 21.0
        agent = MockAgent("agent1", {"green_space_pct": 21.0})
        
        # We mock generate_opinion to return an LLM opinion with green_space_pct: 45.0 in Round 2
        def side_effect(proposal, context, round_number=1, opponent_opinions=None):
            if round_number == 1:
                return AgentOpinion(
                    agent="agent1", score=50.0, recommendation={"green_space_pct": 30.0},
                    position="R1", reasoning="R1", confidence=1.0
                )
            else:
                return AgentOpinion(
                    agent="agent1", score=50.0, recommendation={"green_space_pct": 45.0},
                    position="R2", reasoning="R2", confidence=1.0
                )
        mock_generate_opinion.side_effect = side_effect
        
        session.run_round([agent], {}, cost_calculator)
        
        # Since the LLM proposed 45.0 in Round 2, and there are no opponents, 
        # it should auto-resolve to 45.0, NOT the deterministic 21.0.
        assert session.get_current_state().green_space_pct == 45.0
