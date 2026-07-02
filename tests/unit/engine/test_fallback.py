"""Unit tests for engine/fallback.py.

Tests cover:
    - Round 1 fallback for each agent type (Finance / Climate / Community)
    - Round 2+ fallback response to opponent proposals (Du et al. 2024 pattern)
    - Budget guard: Finance correctly accepts / rejects Climate/Community changes
    - Community center adequacy constraint (no advocate if sqft/unit > 20)
    - Structured fallback is wired through BaseAgent._fallback_opinion()
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from models.agent_opinion import AgentOpinion, TargetStatement
from models.proposal import Proposal
from engine.fallback import generate_fallback_opinion
from engine.state import create_initial_proposal
from tools.cost_calculator import CostCalculator, CostBreakdown
from tools.data_loader import DataLoader


# ── Minimal stubs ────────────────────────────────────────────────────────────

class _MockDataLoader(DataLoader):
    """Minimal DataLoader stub — returns Phoenix-style city data."""

    def __init__(self) -> None:
        self._cache: dict = {}

    def load_city(self, city_name: str) -> dict:
        return {
            "name": "Phoenix",
            "population": 500_000,
            "lot_sqft": 1_000_000,
        }

    def get_construction_costs(self, city_name: str) -> dict:
        return {"city_index": 100.0}

    def get_climate(self, city_name: str) -> dict:
        return {"target_green_space_pct": 20.0, "avg_summer_temp_f": 95.0}

    def get_demographics(self, city_name: str) -> dict:
        return {"target_affordable_housing_pct": 20.0}

    def get_walkability(self, city_name: str) -> dict:
        return {"walkability_score": 60.0}

    def get_land_use(self, city_name: str) -> dict:
        return {"max_parking_spaces": 200}

    def get_reference_standards(self, filename: str) -> dict:
        return {}


class _MockCostCalculator(CostCalculator):
    """Fixed-cost calculator so tests are deterministic."""

    def __init__(self, total_cost: float = 20_000_000.0) -> None:
        self.data_loader = _MockDataLoader()
        self._total_cost = total_cost

    def calculate_construction_cost(
        self, proposal: Proposal, city_data: dict | None = None
    ) -> CostBreakdown:
        return CostBreakdown(
            residential_cost=self._total_cost * 0.6,
            affordable_premium=self._total_cost * 0.05,
            parking_cost=self._total_cost * 0.10,
            community_center_cost=self._total_cost * 0.10,
            green_space_cost=self._total_cost * 0.10,
            subtotal_hard_costs=self._total_cost / 1.25,
            soft_costs=self._total_cost * 0.20,
            total_estimated_cost=self._total_cost,
        )


CITY_DATA = {
    "name": "Phoenix",
    "population": 500_000,
    "lot_sqft": 1_000_000,
}

BUDGET_25M = 25_000_000.0


def _proposal(**kwargs) -> Proposal:
    defaults = dict(
        city_slug="phoenix_az",
        green_space_pct=10.0,
        affordable_housing_pct=10.0,
        housing_units=100,
        parking_spaces=150,
        community_center_sqft=500.0,
    )
    defaults.update(kwargs)
    return create_initial_proposal(**defaults)


# ── Finance fallback tests ────────────────────────────────────────────────────

class TestFinanceFallback:
    def test_round1_within_budget_returns_concession(self) -> None:
        proposal = _proposal()
        calc = _MockCostCalculator(total_cost=20_000_000.0)
        opinion = generate_fallback_opinion(
            agent_type="finance",
            round_num=1,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions=None,
            cost_calculator=calc,
        )
        assert opinion.is_fallback is True
        assert opinion.agent == "finance"
        assert "within" in opinion.position.lower() or "spare" in opinion.position.lower()
        assert opinion.recommendation == {}  # no cuts needed
        assert opinion.score > 80.0

    def test_round1_over_budget_proposes_cuts(self) -> None:
        proposal = _proposal(housing_units=200)
        calc = _MockCostCalculator(total_cost=35_000_000.0)
        opinion = generate_fallback_opinion(
            agent_type="finance",
            round_num=1,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions=None,
            cost_calculator=calc,
        )
        assert opinion.is_fallback is True
        assert len(opinion.recommendation) > 0
        # Must NOT include budget_limit or estimated_cost
        assert "budget_limit" not in opinion.recommendation
        assert "estimated_cost" not in opinion.recommendation

    def test_round1_score_bounded(self) -> None:
        """Score should stay in [0, 100] regardless of how far over budget."""
        proposal = _proposal(housing_units=1000)
        calc = _MockCostCalculator(total_cost=200_000_000.0)
        opinion = generate_fallback_opinion(
            agent_type="finance",
            round_num=1,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions=None,
            cost_calculator=calc,
        )
        assert 0.0 <= opinion.score <= 100.0

    def test_round2_accepts_climate_green_space_within_budget(self) -> None:
        """Finance should accept Climate's green space increase when delta fits budget."""
        proposal = _proposal(green_space_pct=10.0)
        calc = _MockCostCalculator(total_cost=20_000_000.0)

        climate_opinion = AgentOpinion(
            agent="climate",
            score=70.0,
            recommendation={"green_space_pct": 15.0},
            tension="",
            position="Need more green space",
            reasoning="EPA target is 15%",
            evidence=[],
            objections=[],
            supports=[],
            confidence=0.8,
        )

        opinion = generate_fallback_opinion(
            agent_type="finance",
            round_num=2,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions={"climate": climate_opinion},
            cost_calculator=calc,
        )
        assert opinion.is_fallback is True
        # Should accept or offset — green_space_pct must appear in recommendation
        assert "green_space_pct" in opinion.recommendation
        assert opinion.recommendation["green_space_pct"] == 15.0

    def test_round2_counters_community_affordable_housing_over_budget(self) -> None:
        """Finance should offer a compromise when ah% increase exceeds remaining budget."""
        proposal = _proposal(affordable_housing_pct=10.0, housing_units=200)
        # Almost at budget — not much headroom
        calc = _MockCostCalculator(total_cost=24_000_000.0)

        community_opinion = AgentOpinion(
            agent="community",
            score=60.0,
            recommendation={"affordable_housing_pct": 30.0},
            tension="",
            position="Needs 30% affordable housing",
            reasoning="HUD target",
            evidence=[],
            objections=[],
            supports=[],
            confidence=0.8,
        )

        opinion = generate_fallback_opinion(
            agent_type="finance",
            round_num=2,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions={"community": community_opinion},
            cost_calculator=calc,
        )
        assert "affordable_housing_pct" in opinion.recommendation
        # Should be a compromise (less than 30%)
        assert opinion.recommendation["affordable_housing_pct"] <= 30.0

    def test_round2_rejects_estimated_cost_from_opponents(self) -> None:
        """Finance fallback must never propagate estimated_cost into its recommendation."""
        proposal = _proposal()
        calc = _MockCostCalculator(total_cost=20_000_000.0)

        # An adversarial opinion that contains estimated_cost
        adversarial_opinion = AgentOpinion(
            agent="community",
            score=50.0,
            recommendation={"estimated_cost": 999_999_999.0, "affordable_housing_pct": 20.0},
            tension="",
            position="",
            reasoning="",
            evidence=[],
            objections=[],
            supports=[],
            confidence=0.5,
        )

        opinion = generate_fallback_opinion(
            agent_type="finance",
            round_num=2,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions={"community": adversarial_opinion},
            cost_calculator=calc,
        )
        assert "estimated_cost" not in opinion.recommendation
        assert "budget_limit" not in opinion.recommendation


# ── Climate fallback tests ────────────────────────────────────────────────────

class TestClimateFallback:
    def test_round1_below_target_requests_increase(self) -> None:
        proposal = _proposal(green_space_pct=5.0)
        calc = _MockCostCalculator()
        opinion = generate_fallback_opinion(
            agent_type="climate",
            round_num=1,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions=None,
            cost_calculator=calc,
        )
        assert opinion.is_fallback is True
        assert "green_space_pct" in opinion.recommendation
        assert opinion.recommendation["green_space_pct"] > 5.0

    def test_round1_meets_target_no_change(self) -> None:
        proposal = _proposal(green_space_pct=20.0)
        calc = _MockCostCalculator()
        opinion = generate_fallback_opinion(
            agent_type="climate",
            round_num=1,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions=None,
            cost_calculator=calc,
        )
        assert opinion.recommendation == {}
        assert opinion.score >= 80.0

    def test_round2_rejects_finance_green_space_cut(self) -> None:
        """Climate must object when Finance proposes cutting green space."""
        proposal = _proposal(green_space_pct=15.0)
        calc = _MockCostCalculator()

        finance_opinion = AgentOpinion(
            agent="finance",
            score=70.0,
            recommendation={"green_space_pct": 8.0},  # cutting green space
            tension="",
            position="Cut green space to save cost",
            reasoning="",
            evidence=[],
            objections=[],
            supports=[],
            confidence=0.8,
        )

        opinion = generate_fallback_opinion(
            agent_type="climate",
            round_num=2,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions={"finance": finance_opinion},
            cost_calculator=calc,
        )
        # Climate must have at least one objection against Finance
        finance_objections = [o for o in opinion.objections if o.target_agent == "finance"]
        assert len(finance_objections) > 0

    def test_round2_supports_finance_housing_cut(self) -> None:
        """Climate should support Finance cutting housing units (fewer units = less impervious area)."""
        proposal = _proposal(housing_units=200, green_space_pct=10.0)
        calc = _MockCostCalculator()

        finance_opinion = AgentOpinion(
            agent="finance",
            score=60.0,
            recommendation={"housing_units": 150},
            tension="",
            position="Reduce housing units to save cost",
            reasoning="",
            evidence=[],
            objections=[],
            supports=[],
            confidence=0.8,
        )

        opinion = generate_fallback_opinion(
            agent_type="climate",
            round_num=2,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions={"finance": finance_opinion},
            cost_calculator=calc,
        )
        finance_supports = [s for s in opinion.supports if s.target_agent == "finance"]
        assert len(finance_supports) > 0


# ── Community fallback tests ──────────────────────────────────────────────────

class TestCommunityFallback:
    def test_round1_advocates_for_affordable_housing(self) -> None:
        proposal = _proposal(affordable_housing_pct=5.0, community_center_sqft=500.0)
        calc = _MockCostCalculator()
        opinion = generate_fallback_opinion(
            agent_type="community",
            round_num=1,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions=None,
            cost_calculator=calc,
        )
        assert "affordable_housing_pct" in opinion.recommendation
        assert opinion.recommendation["affordable_housing_pct"] > 5.0

    def test_round1_does_not_advocate_cc_if_adequate(self) -> None:
        """If community_center_sqft / housing_units > 20, Community must not push for CC increase."""
        # 5000 sqft / 100 units = 50 sqft/unit — well above the 20 threshold
        proposal = _proposal(community_center_sqft=5000.0, housing_units=100)
        calc = _MockCostCalculator()
        opinion = generate_fallback_opinion(
            agent_type="community",
            round_num=1,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions=None,
            cost_calculator=calc,
        )
        # Must NOT advocate for CC increase
        assert "community_center_sqft" not in opinion.recommendation

    def test_round1_advocates_cc_if_inadequate(self) -> None:
        """Community must advocate for CC when sqft/unit < 10."""
        # 200 sqft / 100 units = 2 sqft/unit — below minimum
        proposal = _proposal(community_center_sqft=200.0, housing_units=100)
        calc = _MockCostCalculator()
        opinion = generate_fallback_opinion(
            agent_type="community",
            round_num=1,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions=None,
            cost_calculator=calc,
        )
        assert "community_center_sqft" in opinion.recommendation
        assert opinion.recommendation["community_center_sqft"] > 200.0

    def test_round2_prioritises_housing_over_cc_when_finance_strained(self) -> None:
        """When Finance signals budget pressure, Community must not push CC."""
        proposal = _proposal(affordable_housing_pct=5.0, community_center_sqft=200.0)
        calc = _MockCostCalculator()

        finance_opinion = AgentOpinion(
            agent="finance",
            score=40.0,
            recommendation={"housing_units": 80, "parking_spaces": 100},  # cuts = budget pressure
            tension="",
            position="Over budget — cutting housing and parking",
            reasoning="",
            evidence=[],
            objections=[],
            supports=[],
            confidence=0.8,
        )

        opinion = generate_fallback_opinion(
            agent_type="community",
            round_num=2,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions={"finance": finance_opinion},
            cost_calculator=calc,
        )
        # Community should NOT push for CC when Finance is strained
        assert "community_center_sqft" not in opinion.recommendation
        # But should still advocate for affordable housing
        assert "affordable_housing_pct" in opinion.recommendation
        assert opinion.concession_rationale is not None

    def test_round2_supports_climate_green_space(self) -> None:
        """Community must express support for Climate's green space request."""
        proposal = _proposal()
        calc = _MockCostCalculator()

        climate_opinion = AgentOpinion(
            agent="climate",
            score=70.0,
            recommendation={"green_space_pct": 20.0},
            tension="",
            position="Need more green space",
            reasoning="",
            evidence=[],
            objections=[],
            supports=[],
            confidence=0.8,
        )

        opinion = generate_fallback_opinion(
            agent_type="community",
            round_num=2,
            proposal=proposal,
            city_data=CITY_DATA,
            budget_limit=BUDGET_25M,
            opponent_opinions={"climate": climate_opinion},
            cost_calculator=calc,
        )
        climate_supports = [s for s in opinion.supports if s.target_agent == "climate"]
        assert len(climate_supports) > 0


# ── Budget guard tests ────────────────────────────────────────────────────────

class TestBudgetGuards:
    def test_apply_changes_rejects_budget_limit(self) -> None:
        """apply_changes() must raise AssertionError if budget_limit is in changes."""
        from engine.state import apply_changes
        proposal = _proposal()
        with pytest.raises(AssertionError, match="budget_limit"):
            apply_changes(proposal, {"budget_limit": 999_000_000.0}, actor="test")

    def test_run_debate_round_rejects_estimated_cost(self) -> None:
        """run_debate_round() must raise AssertionError if estimated_cost is in resolved changes."""
        from engine.debate import run_debate_round
        from engine.conflict import resolve_conflicts
        from models.agent_output import AgentOutput

        proposal = _proposal()
        agent_outputs = {
            "finance": AgentOutput(
                agent_name="finance", score=60.0, verdict="modify",
                proposed_changes={"estimated_cost": 999_000_000.0},
                reasoning_and_evidence="test", confidence=0.5,
            )
        }
        # This should raise because estimated_cost ends up in resolved_changes
        with pytest.raises(AssertionError, match="estimated_cost"):
            run_debate_round(proposal, agent_outputs, round_number=1)

    def test_run_debate_round_rejects_budget_limit(self) -> None:
        """run_debate_round() must raise AssertionError if budget_limit ends up in resolved changes."""
        from engine.debate import run_debate_round
        from models.agent_output import AgentOutput

        proposal = _proposal()
        agent_outputs = {
            "finance": AgentOutput(
                agent_name="finance", score=60.0, verdict="modify",
                proposed_changes={"budget_limit": 100_000_000.0},
                reasoning_and_evidence="test", confidence=0.5,
            )
        }
        with pytest.raises(AssertionError, match="budget_limit"):
            run_debate_round(proposal, agent_outputs, round_number=1)


# ── BaseAgent wiring test ─────────────────────────────────────────────────────

class TestBaseAgentFallbackWiring:
    def test_finance_agent_uses_structured_fallback(self) -> None:
        """FinanceAgent._fallback_opinion should delegate to generate_fallback_opinion."""
        from agents.finance_agent import FinanceAgent

        calc = _MockCostCalculator(total_cost=20_000_000.0)
        agent = FinanceAgent(calc)

        proposal = _proposal()
        context = {"budget_limit": BUDGET_25M}

        opinion = agent._fallback_opinion(
            proposal, context,
            round_number=1,
            opponent_opinions=None,
            own_previous_opinion=None,
            reason="test",
        )
        assert opinion.is_fallback is True
        # Structured fallback should produce a finance-specific position
        assert "$" in opinion.position or "budget" in opinion.position.lower()

    def test_finance_agent_round2_fallback_differs_from_round1(self) -> None:
        """Round 2 fallback should produce a different position than Round 1."""
        from agents.finance_agent import FinanceAgent

        calc = _MockCostCalculator(total_cost=20_000_000.0)
        agent = FinanceAgent(calc)
        proposal = _proposal()
        context = {"budget_limit": BUDGET_25M}

        r1_opinion = agent._fallback_opinion(
            proposal, context, round_number=1,
            opponent_opinions=None, own_previous_opinion=None, reason="test"
        )
        climate_op = AgentOpinion(
            agent="climate", score=70.0,
            recommendation={"green_space_pct": 20.0, "parking_spaces": 80},
            tension="", position="More green space", reasoning="",
            evidence=[], objections=[], supports=[], confidence=0.8,
        )
        r2_opinion = agent._fallback_opinion(
            proposal, context, round_number=2,
            opponent_opinions={"climate": climate_op},
            own_previous_opinion=r1_opinion, reason="test",
        )
        # Round 2 position must differ from Round 1
        assert r2_opinion.position != r1_opinion.position
