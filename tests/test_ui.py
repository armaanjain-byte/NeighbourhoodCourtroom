"""Smoke tests for the Streamlit UI."""

import pytest
import sys
from unittest.mock import patch, MagicMock

# Skip all tests in this file if streamlit is not installed
st = pytest.importorskip("streamlit")

# Attempt imports to ensure no syntax errors or top-level import crashes
from ui.app import init_session_state
from ui.components.intake_form import render_intake_form
from ui.components.courtroom_view import render_courtroom_view
from ui.components.history_panel import render_history_panel
from ui.components.verdict_panel import render_verdict_panel

@patch("ui.app.st")
def test_ui_initialization_smoke(mock_st) -> None:
    """Smoke test to ensure session state initializes cleanly."""
    mock_st.session_state = {}
    init_session_state()
    
    assert "data_loader" in mock_st.session_state
    assert "cost_calculator" in mock_st.session_state
    assert "agents" in mock_st.session_state
    assert "session" in mock_st.session_state
    assert "audit" in mock_st.session_state
    
    # Check that 3 agents were loaded
    assert len(mock_st.session_state["agents"]) == 3
