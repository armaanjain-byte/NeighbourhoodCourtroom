"""Timeline Engine — Generates a flat, ordered list of animation beats.

Purpose:
    Converts a CourtroomSession's debate_rounds into a flat, ordered list of "beats" —
    discrete animation events a frontend can step through one at a time, regardless
    of whether the session had 1, 2, or 3 rounds. Built from real session data.

Dependencies:
    engine.session.CourtroomSession, engine.debate.process_conflicts, models.agent_output.AgentOutput
"""

from __future__ import annotations

from typing import Any
from engine.session import CourtroomSession
from engine.debate import process_conflicts
from models.agent_output import AgentOutput


def build_courtroom_timeline(session: CourtroomSession) -> list[dict[str, Any]]:
    """Generate a flat, ordered list of animation beats from a courtroom session.

    Parameters
    ----------
    session : CourtroomSession
        The active or completed courtroom session containing debate rounds.

    Returns
    -------
    list[dict[str, Any]]
        A flat list of beat dictionaries representing discrete animation events.
    """
    beats: list[dict[str, Any]] = []
    stable_agents = ["finance", "climate", "community"]

    if not session.debate_rounds:
        return beats

    last_round_num = 1
    last_sub_round = 1

    for dr_index, dr in enumerate(session.debate_rounds):
        session_attempt = dr_index + 1
        sub_rounds = [
            (1, dr.round_1_opinions),
            (2, dr.round_2_opinions),
            (3, dr.round_3_opinions),
        ]

        for sub_round_num, op_dict in sub_rounds:
            if not op_dict:
                continue

            round_number = sub_round_num
            last_round_num = round_number
            last_sub_round = sub_round_num

            # 1. round_start beat
            if session_attempt == 1:
                message = f"Round {round_number} starting."
            else:
                message = f"Attempt #{session_attempt} — Round {round_number} of negotiation starting."

            beats.append({
                "beat_type": "round_start",
                "round_number": round_number,
                "session_attempt": session_attempt,
                "negotiation_round": sub_round_num,
                "duration_hint_seconds": 2.0,
                "content": {"message": message}
            })

            # 2. agent_statement beats (stable order: finance, climate, community)
            for agent_name in stable_agents:
                if agent_name in op_dict:
                    op = op_dict[agent_name]
                    beats.append({
                        "beat_type": "agent_statement",
                        "round_number": round_number,
                        "session_attempt": session_attempt,
                        "negotiation_round": sub_round_num,
                        "agent": agent_name,
                        "duration_hint_seconds": 8.0,
                        "content": {
                            "tension": op.tension,
                            "position": op.position,
                            "reasoning": op.reasoning,
                            "evidence": op.evidence,
                            "confidence": op.confidence,
                        }
                    })

            # 3. objection and support beats
            if sub_round_num in (2, 3):
                for agent_name in stable_agents:
                    if agent_name in op_dict:
                        op = op_dict[agent_name]
                        for obj in op.objections:
                            beats.append({
                                "beat_type": "objection",
                                "round_number": round_number,
                                "session_attempt": session_attempt,
                                "negotiation_round": sub_round_num,
                                "agent": agent_name,
                                "target_agent": obj.target_agent,
                                "duration_hint_seconds": 4.0,
                                "content": {
                                    "engages_with": obj.engages_with,
                                    "reason": obj.reason,
                                }
                            })
                        for sup in op.supports:
                            beats.append({
                                "beat_type": "support",
                                "round_number": round_number,
                                "session_attempt": session_attempt,
                                "negotiation_round": sub_round_num,
                                "agent": agent_name,
                                "target_agent": sup.target_agent,
                                "duration_hint_seconds": 4.0,
                                "content": {
                                    "engages_with": sup.engages_with,
                                    "reason": sup.reason,
                                }
                            })

            # 4. conflict_flare beats
            outputs = {
                name: AgentOutput(
                    agent_name=name,
                    score=op.score,
                    verdict="modify" if op.recommendation else "accept",
                    proposed_changes=op.recommendation,
                    reasoning_and_evidence=op.reasoning,
                    confidence=op.confidence,
                )
                for name, op in op_dict.items()
            }
            conflicts, _, summary = process_conflicts(dr.opening_state, outputs)
            
            # Sort conflicts deterministically by parameter, then agent_a, then agent_b
            conflicts = sorted(conflicts, key=lambda c: (c.parameter, c.agent_a, c.agent_b))

            for c in conflicts:
                beats.append({
                    "beat_type": "conflict_flare",
                    "round_number": round_number,
                    "session_attempt": session_attempt,
                    "negotiation_round": sub_round_num,
                    "agent": c.agent_a,
                    "target_agent": c.agent_b,
                    "severity": c.disagreement_severity,
                    "duration_hint_seconds": 2.0,
                    "content": {
                        "parameter": c.parameter,
                        "agent_a": c.agent_a,
                        "agent_b": c.agent_b,
                        "proposed_value_a": c.proposed_value_a,
                        "proposed_value_b": c.proposed_value_b,
                        "disagreement_severity": c.disagreement_severity,
                    }
                })

            # 5. concession beats
            for agent_name in stable_agents:
                if agent_name in op_dict:
                    op = op_dict[agent_name]
                    if op.concession_rationale:
                        beats.append({
                            "beat_type": "concession",
                            "round_number": round_number,
                            "session_attempt": session_attempt,
                            "negotiation_round": sub_round_num,
                            "agent": agent_name,
                            "duration_hint_seconds": 5.0,
                            "content": {
                                "concession_rationale": op.concession_rationale,
                            }
                        })

            # 6. round_resolution beat
            beats.append({
                "beat_type": "round_resolution",
                "round_number": round_number,
                "session_attempt": session_attempt,
                "negotiation_round": sub_round_num,
                "duration_hint_seconds": 4.0,
                "content": {
                    "engine_summary": summary,
                }
            })

    # 7. final_verdict beat
    status = session.status
    if status == "WAITING_FOR_JUDGE":
        outcome = "escalated to human review"
    elif status == "COMPLETED":
        outcome = "accepted"
    else:
        outcome = status.lower()

    unresolved = []
    unresolved_attempts = {}
    consecutive_unlocked_warnings = []

    if session.debate_rounds:
        last_dr = session.debate_rounds[-1]
        for c in last_dr.detected_conflicts:
            if c.disagreement_severity == "high" and c.parameter not in session.current_proposal.human_locks:
                unresolved.append(c.parameter)

        # Calculate unresolved attempts across all session rounds
        for dr in session.debate_rounds:
            for c in dr.detected_conflicts:
                if c.disagreement_severity == "high" and c.parameter not in session.current_proposal.human_locks:
                    unresolved_attempts[c.parameter] = unresolved_attempts.get(c.parameter, 0) + 1

        # Check for parameters flagged across 2+ consecutive session attempts without human lock/override
        if len(session.debate_rounds) >= 2:
            prev_dr = session.debate_rounds[-2]
            curr_dr = session.debate_rounds[-1]
            prev_highs = {c.parameter for c in prev_dr.detected_conflicts if c.disagreement_severity == "high"}
            curr_highs = {c.parameter for c in curr_dr.detected_conflicts if c.disagreement_severity == "high"}
            
            for param in curr_highs.intersection(prev_highs):
                # Verify whether human override was actually applied between session attempts
                has_override = (param in session.current_proposal.human_locks) or any(
                    ov.get("parameter") == param for ov in session.override_history
                )
                if not has_override:
                    consecutive_unlocked_warnings.append(
                        f"Parameter '{param}' has been flagged for human review across {unresolved_attempts.get(param, 2)} consecutive session attempts without an override. We strongly suggest using the override slider below to lock this parameter rather than re-running the debate, as re-running without intervening is unlikely to resolve a genuine values disagreement between agents."
                    )

    beats.append({
        "beat_type": "final_verdict",
        "round_number": last_round_num,
        "session_attempt": len(session.debate_rounds) if session.debate_rounds else 1,
        "negotiation_round": last_sub_round,
        "duration_hint_seconds": 5.0,
        "content": {
            "status": status,
            "outcome": outcome,
            "final_proposal": session.current_proposal.model_dump(),
            "unresolved_conflicts": sorted(list(set(unresolved))),
            "unresolved_attempts": unresolved_attempts,
            "consecutive_unlocked_warnings": consecutive_unlocked_warnings,
        }
    })

    return beats


def build_cinematic_timeline(timeline: list[dict[str, Any]], target_seconds: int = 180) -> list[dict[str, Any]]:
    """Generate a fixed-length cinematic replay timeline scaled to approximately target_seconds.

    In cinematic mode, beat timings are re-derived to ensure a consistent pacing (e.g. ~3 minutes
    for demo recording), regardless of how many real rounds the session had, without deleting or
    fabricating any content. Relative emphasis is preserved by giving proportionally more time to
    narratively critical beats (concessions, conflict flares, verdicts) than minor agent statements.

    If a session has only 1 round (early-stop case), this function scales up the duration of each
    beat so the pacing slows down gracefully rather than rushing through and sitting idle.
    If a session has 3 rounds with many beats, this function scales down (compresses) durations
    proportionally without dropping a single beat.

    Parameters
    ----------
    timeline : list[dict[str, Any]]
        The original flat list of beats from build_courtroom_timeline.
    target_seconds : int, optional
        The target total duration in seconds (default 180).

    Returns
    -------
    list[dict[str, Any]]
        A new list of beat dictionaries with adjusted duration_hint_seconds.
    """
    if not timeline:
        return []

    # Assign base cinematic weights reflecting relative narrative importance
    weights = {
        "concession": 10.0,
        "conflict_flare": 8.0,
        "final_verdict": 8.0,
        "agent_statement": 6.0,
        "round_resolution": 5.0,
        "objection": 4.0,
        "support": 4.0,
        "round_start": 2.0,
    }

    total_base = sum(weights.get(b["beat_type"], 5.0) for b in timeline)
    if total_base <= 0:
        return [dict(b) for b in timeline]

    scale = target_seconds / total_base
    cinematic_timeline = []

    for b in timeline:
        new_beat = dict(b)
        base_weight = weights.get(b["beat_type"], 5.0)
        new_beat["duration_hint_seconds"] = round(base_weight * scale, 2)
        cinematic_timeline.append(new_beat)

    return cinematic_timeline
