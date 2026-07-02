"""Tests for objection rendering in the debate transcript."""

from models.agent_opinion import AgentOpinion
from ui.components.transcript_view import build_card_html


def test_objection_renders_engaged_claim_and_warning() -> None:
    opinion = AgentOpinion(
        agent="climate",
        score=75.0,
        recommendation={"green_space_pct": 35.0},
        tension="Housing capacity competes with park space.",
        position="Keep enough park space to protect residents from heat.",
        reasoning="Cooling benefits outweigh the capacity tradeoff.",
        objections=[{
            "target_agent": "finance",
            "engages_with": "green_space_pct 30",
            "reason": "That number does not account for heat exposure.",
        }],
        confidence=0.8,
        engagement_warnings=["finance:green_space_pct 30"],
    )

    html = build_card_html("climate", 1, "D1 - R2", opinion)

    assert "Responding to Finance's claim that" in html
    assert '"green_space_pct 30"' in html
    assert "That number does not account for heat exposure." in html
    assert "weak engagement" in html
