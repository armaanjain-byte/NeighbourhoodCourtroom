"""Tests for Timeline Engine.

Purpose:
    Validates that CourtroomSession debate rounds are correctly converted into a flat,
    ordered list of animation beats with deterministic sequencing and stable agent ordering.

Covers:
    - 1-round early-stop session produces a timeline with no Round 2/3 beats
    - 3-round session with an unresolved-then-resolved HIGH conflict produces correct beats
    - Beat ordering is deterministic and stable agent-order (finance, climate, community) is respected
"""

import pytest
from models.proposal import Proposal
from models.agent_output import AgentOutput
from models.agent_opinion import AgentOpinion, TargetStatement
from models.debate_round import DebateRound
from models.conflict import Conflict
from engine.session import CourtroomSession
from engine.timeline import build_courtroom_timeline


@pytest.fixture
def base_proposal() -> Proposal:
    return Proposal(
        city_slug="phoenix_az",
        green_space_pct=20.0,
        affordable_housing_pct=15.0,
        housing_units=200,
        parking_spaces=300,
        community_center_sqft=5000.0,
        
    )


def test_empty_session_timeline(base_proposal: Proposal) -> None:
    """Verify an empty session produces an empty timeline."""
    session = CourtroomSession(current_proposal=base_proposal)
    beats = build_courtroom_timeline(session)
    assert beats == []


def test_one_round_early_stop_timeline(base_proposal: Proposal) -> None:
    """Verify a 1-round early-stop session produces a timeline with no Round 2/3 beats."""
    op_finance = AgentOpinion(
        agent="finance",
        score=85.0,
        recommendation={"green_space_pct": 21.0},
        tension="Tension finance.",
        position="Position finance.",
        reasoning="Reasoning finance.",
        evidence=["Ev finance."],
        confidence=0.9,
    )
    op_climate = AgentOpinion(
        agent="climate",
        score=88.0,
        recommendation={"green_space_pct": 22.0},
        tension="Tension climate.",
        position="Position climate.",
        reasoning="Reasoning climate.",
        evidence=["Ev climate."],
        confidence=0.9,
    )
    op_community = AgentOpinion(
        agent="community",
        score=90.0,
        recommendation={},
        tension="Tension community.",
        position="Position community.",
        reasoning="Reasoning community.",
        evidence=["Ev community."],
        confidence=0.9,
    )

    dr = DebateRound(
        round_number=1,
        opening_state=base_proposal,
        agent_outputs={
            "finance": AgentOutput(agent_name="finance", score=85.0, verdict="modify", proposed_changes={"green_space_pct": 21.0}, reasoning_and_evidence="R", confidence=0.9),
            "climate": AgentOutput(agent_name="climate", score=88.0, verdict="modify", proposed_changes={"green_space_pct": 22.0}, reasoning_and_evidence="R", confidence=0.9),
            "community": AgentOutput(agent_name="community", score=90.0, verdict="accept", proposed_changes={}, reasoning_and_evidence="R", confidence=0.9),
        },
        detected_conflicts=[
            Conflict(parameter="green_space_pct", agent_a="finance", agent_b="climate", proposed_value_a=21.0, proposed_value_b=22.0, disagreement_severity="low")
        ],
        closing_state=base_proposal,
        engine_summary="Auto-resolved low conflict.",
        round_1_opinions={"finance": op_finance, "climate": op_climate, "community": op_community},
        round_2_opinions={},
        round_3_opinions={},
    )

    session = CourtroomSession(current_proposal=base_proposal, debate_rounds=[dr], status="COMPLETED")
    beats = build_courtroom_timeline(session)

    # Assert no Round 2 or 3 beats
    assert all(beat["round_number"] == 1 for beat in beats)

    # Check beat types present
    beat_types = [beat["beat_type"] for beat in beats]
    assert "round_start" in beat_types
    assert "agent_statement" in beat_types
    assert "conflict_flare" in beat_types
    assert "round_resolution" in beat_types
    assert "final_verdict" in beat_types

    # Check stable agent order for agent_statements
    statement_agents = [beat["agent"] for beat in beats if beat["beat_type"] == "agent_statement"]
    assert statement_agents == ["finance", "climate", "community"]

    # Check duration hints
    assert beats[0]["duration_hint_seconds"] == 2.0  # round_start
    assert beats[1]["duration_hint_seconds"] == 8.0  # agent_statement
    assert beats[-1]["duration_hint_seconds"] == 5.0 # final_verdict


def test_three_round_unresolved_then_resolved_timeline(base_proposal: Proposal) -> None:
    """Verify a 3-round session with an unresolved-then-resolved HIGH conflict produces correct ordered beats."""
    # Round 1 opinions (independent)
    r1_opinions = {
        "finance": AgentOpinion(agent="finance", score=50, recommendation={"green_space_pct": 10.0}, tension="T", position="P", reasoning="R", confidence=0.8),
        "climate": AgentOpinion(agent="climate", score=50, recommendation={"green_space_pct": 90.0}, tension="T", position="P", reasoning="R", confidence=0.8),
    }

    # Round 2 opinions (HIGH conflict persists, objections/supports added, concession rationale added)
    r2_opinions = {
        "finance": AgentOpinion(
            agent="finance", score=55, recommendation={"green_space_pct": 15.0}, tension="T", position="P", reasoning="R", confidence=0.8,
            objections=[TargetStatement(target_agent="climate", engages_with="90% green space", reason="Too expensive.")],
            concession_rationale="Moved from 10% to 15% to compromise."
        ),
        "climate": AgentOpinion(
            agent="climate", score=55, recommendation={"green_space_pct": 85.0}, tension="T", position="P", reasoning="R", confidence=0.8,
            supports=[TargetStatement(target_agent="finance", engages_with="budget concern", reason="Agree budget matters.")],
        ),
    }

    # Round 3 opinions (final attempt, resolved to LOW conflict)
    r3_opinions = {
        "finance": AgentOpinion(
            agent="finance", score=80, recommendation={"green_space_pct": 48.0}, tension="T", position="P", reasoning="R", confidence=0.9,
            concession_rationale="Final concession to 48%."
        ),
        "climate": AgentOpinion(
            agent="climate", score=80, recommendation={"green_space_pct": 50.0}, tension="T", position="P", reasoning="R", confidence=0.9,
            concession_rationale="Final concession to 50%."
        ),
    }

    dr = DebateRound(
        round_number=1,
        opening_state=base_proposal,
        agent_outputs={
            "finance": AgentOutput(agent_name="finance", score=80.0, verdict="modify", proposed_changes={"green_space_pct": 48.0}, reasoning_and_evidence="R", confidence=0.9),
            "climate": AgentOutput(agent_name="climate", score=80.0, verdict="modify", proposed_changes={"green_space_pct": 50.0}, reasoning_and_evidence="R", confidence=0.9),
        },
        detected_conflicts=[
            Conflict(parameter="green_space_pct", agent_a="finance", agent_b="climate", proposed_value_a=48.0, proposed_value_b=50.0, disagreement_severity="low")
        ],
        closing_state=base_proposal,
        engine_summary="Converged in Round 3.",
        round_1_opinions=r1_opinions,
        round_2_opinions=r2_opinions,
        round_3_opinions=r3_opinions,
    )

    session = CourtroomSession(current_proposal=base_proposal, debate_rounds=[dr], status="COMPLETED")
    beats = build_courtroom_timeline(session)

    # Verify rounds 1, 2, and 3 are present in the timeline
    round_numbers = sorted(list(set(beat["round_number"] for beat in beats)))
    assert round_numbers == [1, 2, 3]

    # Verify Round 2 beats contain objection, support, HIGH conflict flare, and concession
    r2_beats = [b for b in beats if b["round_number"] == 2]
    r2_types = [b["beat_type"] for b in r2_beats]
    
    assert "objection" in r2_types
    assert "support" in r2_types
    assert "concession" in r2_types
    assert "conflict_flare" in r2_types

    # Check HIGH conflict flare in Round 2
    flare_r2 = [b for b in r2_beats if b["beat_type"] == "conflict_flare"][0]
    assert flare_r2["severity"] == "high"
    assert flare_r2["content"]["proposed_value_a"] == 85.0
    assert flare_r2["content"]["proposed_value_b"] == 15.0

    # Check LOW conflict flare in Round 3
    r3_beats = [b for b in beats if b["round_number"] == 3]
    flare_r3 = [b for b in r3_beats if b["beat_type"] == "conflict_flare"][0]
    assert flare_r3["severity"] == "low"
    assert flare_r3["content"]["proposed_value_a"] == 50.0
    assert flare_r3["content"]["proposed_value_b"] == 48.0

    # Verify deterministic beat ordering within a round
    # round_start -> agent_statement -> objection/support -> conflict_flare -> concession -> round_resolution
    expected_type_order = {"round_start": 0, "agent_statement": 1, "objection": 2, "support": 2, "conflict_flare": 3, "concession": 4, "round_resolution": 5}
    
    # Check ordering for r2_beats (excluding final_verdict which is at the very end of r3)
    previous_rank = -1
    for b in r2_beats:
        rank = expected_type_order[b["beat_type"]]
        assert rank >= previous_rank
        previous_rank = rank


def test_build_cinematic_timeline(base_proposal: Proposal) -> None:
    """Verify build_cinematic_timeline re-paces 1, 2, and 3 round sessions to ~180s without dropping beats."""
    from engine.timeline import build_cinematic_timeline

    op_finance = AgentOpinion(agent="finance", score=85.0, recommendation={"green_space_pct": 21.0}, tension="T", position="P", reasoning="R", confidence=0.9)
    op_climate = AgentOpinion(agent="climate", score=88.0, recommendation={"green_space_pct": 22.0}, tension="T", position="P", reasoning="R", confidence=0.9)
    
    # 1-Round Session
    dr1 = DebateRound(
        round_number=1, opening_state=base_proposal,
        agent_outputs={"finance": AgentOutput(agent_name="finance", score=85.0, verdict="modify", proposed_changes={"green_space_pct": 21.0}, reasoning_and_evidence="R", confidence=0.9)},
        detected_conflicts=[Conflict(parameter="green_space_pct", agent_a="finance", agent_b="climate", proposed_value_a=21.0, proposed_value_b=22.0, disagreement_severity="low")],
        closing_state=base_proposal, engine_summary="Summary.",
        round_1_opinions={"finance": op_finance, "climate": op_climate},
        round_2_opinions={}, round_3_opinions={}
    )
    session_1 = CourtroomSession(current_proposal=base_proposal, debate_rounds=[dr1], status="COMPLETED")

    # 2-Round Session
    dr2 = DebateRound(
        round_number=1, opening_state=base_proposal,
        agent_outputs={"finance": AgentOutput(agent_name="finance", score=85.0, verdict="modify", proposed_changes={"green_space_pct": 21.0}, reasoning_and_evidence="R", confidence=0.9)},
        detected_conflicts=[Conflict(parameter="green_space_pct", agent_a="finance", agent_b="climate", proposed_value_a=21.0, proposed_value_b=22.0, disagreement_severity="low")],
        closing_state=base_proposal, engine_summary="Summary.",
        round_1_opinions={"finance": op_finance, "climate": op_climate},
        round_2_opinions={"finance": op_finance, "climate": op_climate},
        round_3_opinions={}
    )
    session_2 = CourtroomSession(current_proposal=base_proposal, debate_rounds=[dr2], status="COMPLETED")

    # 3-Round Session
    dr3 = DebateRound(
        round_number=1, opening_state=base_proposal,
        agent_outputs={"finance": AgentOutput(agent_name="finance", score=85.0, verdict="modify", proposed_changes={"green_space_pct": 21.0}, reasoning_and_evidence="R", confidence=0.9)},
        detected_conflicts=[Conflict(parameter="green_space_pct", agent_a="finance", agent_b="climate", proposed_value_a=21.0, proposed_value_b=22.0, disagreement_severity="low")],
        closing_state=base_proposal, engine_summary="Summary.",
        round_1_opinions={"finance": op_finance, "climate": op_climate},
        round_2_opinions={"finance": op_finance, "climate": op_climate},
        round_3_opinions={"finance": op_finance, "climate": op_climate}
    )
    session_3 = CourtroomSession(current_proposal=base_proposal, debate_rounds=[dr3], status="COMPLETED")

    for session in [session_1, session_2, session_3]:
        beats = build_courtroom_timeline(session)
        cinematic_beats = build_cinematic_timeline(beats, target_seconds=180)

        # 1. No beats dropped (same count in, same count out)
        assert len(cinematic_beats) == len(beats)

        # 2. Total duration is within tolerance of 180 seconds (e.g. ±15s)
        total_duration = sum(b["duration_hint_seconds"] for b in cinematic_beats)
        assert abs(total_duration - 180.0) <= 15.0

        # 3. Check that only durations changed (types and content remain identical)
        for original, cinematic in zip(beats, cinematic_beats):
            assert original["beat_type"] == cinematic["beat_type"]
            assert original["content"] == cinematic["content"]


def test_multi_attempt_timeline(base_proposal: Proposal) -> None:
    """Verify that multiple session attempts don't inflate round_number and correctly track session_attempt."""
    op_finance = AgentOpinion(agent="finance", score=85.0, recommendation={"green_space_pct": 21.0}, tension="T", position="P", reasoning="R", confidence=0.9)
    op_climate = AgentOpinion(agent="climate", score=88.0, recommendation={"green_space_pct": 22.0}, tension="T", position="P", reasoning="R", confidence=0.9)

    # Attempt 1: Early stop
    dr1 = DebateRound(
        round_number=1,
        opening_state=base_proposal,
        agent_outputs={},
        detected_conflicts=[Conflict(parameter="green_space_pct", agent_a="finance", agent_b="climate", proposed_value_a=21.0, proposed_value_b=22.0, disagreement_severity="high")],
        closing_state=base_proposal,
        engine_summary="Escalated to human.",
        round_1_opinions={"finance": op_finance, "climate": op_climate},
        round_2_opinions={},
        round_3_opinions={},
    )

    # Attempt 2: Early stop
    dr2 = DebateRound(
        round_number=1,
        opening_state=base_proposal,
        agent_outputs={},
        detected_conflicts=[],
        closing_state=base_proposal,
        engine_summary="Resolved.",
        round_1_opinions={"finance": op_finance, "climate": op_climate},
        round_2_opinions={},
        round_3_opinions={},
    )

    session = CourtroomSession(current_proposal=base_proposal, debate_rounds=[dr1, dr2], status="COMPLETED")
    beats = build_courtroom_timeline(session)

    # Verify attempt 1 beats
    attempt_1_beats = [b for b in beats if b.get("session_attempt") == 1 and b["beat_type"] != "final_verdict"]
    assert len(attempt_1_beats) > 0
    for beat in attempt_1_beats:
        assert beat["round_number"] == 1
        if beat["beat_type"] == "round_start":
            assert beat["content"]["message"] == "Round 1 starting."

    # Verify attempt 2 beats
    attempt_2_beats = [b for b in beats if b.get("session_attempt") == 2 and b["beat_type"] != "final_verdict"]
    assert len(attempt_2_beats) > 0
    for beat in attempt_2_beats:
        assert beat["round_number"] == 1  # Should be 1, NOT 4
        if beat["beat_type"] == "round_start":
            assert beat["content"]["message"] == "Attempt #2 — Round 1 of negotiation starting."

    # Verify final verdict beat
    final_verdict_beat = beats[-1]
    assert final_verdict_beat["beat_type"] == "final_verdict"
    assert final_verdict_beat["session_attempt"] == 2
    assert final_verdict_beat["round_number"] == 1
