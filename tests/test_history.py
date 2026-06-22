"""Tests for engine/history.py — Explainability and History Engine.

Covers:
    - Conflict, decision, resolution, and override tracking
    - Parameter history filtering
    - Agent history filtering
    - Multi-round complex scenarios
    - Audit report logic
    - Explainability narratives formatting
"""

import pytest

from models.conflict import Conflict
from engine.history import AuditHistory


# ── Tests ───────────────────────────────────────────────────────────────────

class TestAuditHistory:
    def test_record_decision(self) -> None:
        history = AuditHistory()
        history.record_decision(1, "finance", "green_space_pct", 15.0)
        
        assert len(history.decisions) == 1
        assert history.decisions[0].agent == "finance"
        assert history.decisions[0].proposed_value == 15.0

    def test_record_conflict(self) -> None:
        history = AuditHistory()
        conflict = Conflict(
            parameter="green_space_pct",
            agent_a="finance",
            agent_b="climate",
            proposed_value_a=15.0,
            proposed_value_b=40.0,
            disagreement_severity="high"
        )
        history.record_conflict(1, conflict)
        
        assert len(history.conflicts) == 1
        assert history.conflicts[0].severity == "high"
        
        timeline = history.get_conflict_timeline()
        assert len(timeline) == 1
        assert timeline[0].parameter == "green_space_pct"

    def test_record_resolution(self) -> None:
        history = AuditHistory()
        history.record_resolution(1, "green_space_pct", "auto-resolved", 27.5)
        
        assert len(history.resolutions) == 1
        assert history.resolutions[0].resolved_value == 27.5

    def test_record_override(self) -> None:
        history = AuditHistory()
        history.record_override(2, "green_space_pct", 35.0)
        
        assert len(history.overrides) == 1
        assert history.overrides[0].locked_value == 35.0

    def test_get_agent_history(self) -> None:
        history = AuditHistory()
        history.record_decision(1, "finance", "parking_spaces", 100)
        history.record_decision(1, "climate", "green_space_pct", 40)
        history.record_decision(2, "finance", "housing_units", 200)
        
        finance_history = history.get_agent_history("finance")
        assert len(finance_history) == 2
        assert finance_history[0].parameter == "parking_spaces"
        assert finance_history[1].parameter == "housing_units"

    def test_get_parameter_history(self) -> None:
        history = AuditHistory()
        history.record_decision(1, "finance", "green_space_pct", 15)
        history.record_decision(1, "climate", "green_space_pct", 40)
        history.record_override(2, "green_space_pct", 35)
        history.record_decision(1, "finance", "parking_spaces", 100)
        
        param_hist = history.get_parameter_history("green_space_pct")
        assert len(param_hist["decisions"]) == 2
        assert len(param_hist["overrides"]) == 1
        assert len(param_hist["conflicts"]) == 0

    def test_generate_audit_report(self) -> None:
        history = AuditHistory()
        history.record_decision(1, "finance", "green_space_pct", 15)
        history.record_resolution(1, "green_space_pct", "auto-resolved", 15.0)
        
        report = history.generate_audit_report()
        assert report["total_decisions"] == 1
        assert report["total_conflicts"] == 0
        assert report["total_resolutions"] == 1
        assert report["total_overrides"] == 0

    def test_explain_parameter_found(self) -> None:
        history = AuditHistory()
        
        # Round 1
        history.record_decision(1, "finance", "green_space_pct", 15.0)
        history.record_decision(1, "climate", "green_space_pct", 40.0)
        conflict = Conflict(
            parameter="green_space_pct",
            agent_a="finance",
            agent_b="climate",
            proposed_value_a=15.0,
            proposed_value_b=40.0,
            disagreement_severity="high"
        )
        history.record_conflict(1, conflict)
        history.record_resolution(1, "green_space_pct", "human review required")
        
        # Round 2
        history.record_override(2, "green_space_pct", 35.0)
        
        explanation = history.explain_parameter("green_space_pct")
        
        expected_substrings = [
            "### Round 1",
            "🌳 **Climate Agent** proposed `40`",
            "👔 **Finance Agent** proposed `15`",
            "🛑 **SYSTEM HALTED:** High Severity Conflict Detected.",
            "Resolution: human review required",
            "### Round 2",
            "🧑‍⚖️ **JUDGE OVERRIDE:** Forced to `35`",
            "### Final value: `35`"
        ]
        
        for sub in expected_substrings:
            assert sub in explanation

    def test_explain_parameter_unresolved(self) -> None:
        history = AuditHistory()
        history.record_decision(1, "finance", "parking_spaces", 50)
        history.record_resolution(1, "parking_spaces", "dropped")
        explanation = history.explain_parameter("parking_spaces")
        assert "### Final value:" in explanation
        assert "Unresolved or unknown" in explanation
        assert "Resolution:" in explanation
        assert "dropped" in explanation

    def test_explain_parameter_not_found(self) -> None:
        history = AuditHistory()
        explanation = history.explain_parameter("nonexistent")
        assert "No history found" in explanation
