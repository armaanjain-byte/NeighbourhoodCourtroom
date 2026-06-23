"""Main Streamlit Entry Point for Neighbourhood Courtroom MVP."""

import sys
import os
import streamlit as st

# Ensure the root directory is in the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.data_loader import DataLoader
from tools.cost_calculator import CostCalculator
from agents.finance_agent import FinanceAgent
from agents.climate_agent import ClimateAgent
from agents.community_agent import CommunityAgent

from ui.components.intake_form import render_intake_form
from ui.components.courtroom_view import render_courtroom_view
from ui.components.history_panel import render_history_panel
from ui.components.verdict_panel import render_verdict_panel

st.set_page_config(page_title="Neighbourhood Courtroom", layout="wide")

def init_session_state():
    if "data_loader" not in st.session_state:
        dl = DataLoader()
        st.session_state.data_loader = dl
        st.session_state.cost_calculator = CostCalculator(dl)
        
        # Initialize deterministic agents
        st.session_state.agents = [
            FinanceAgent(st.session_state.cost_calculator),
            ClimateAgent(dl),
            CommunityAgent(dl)
        ]
        
    if "session" not in st.session_state:
        st.session_state.session = None
        
    if "audit" not in st.session_state:
        st.session_state.audit = None

def main():
    init_session_state()
    
    st.title("🏛️ Neighbourhood Courtroom")
    st.markdown("A multi-agent debate engine for urban planning.")
    
    st.sidebar.title("Competition Mode")
    if st.sidebar.checkbox("Enable Demo Guide", value=True):
        st.sidebar.info(
            "**3-Minute Demo Script:**\n\n"
            "1. **Case Filing**: Click `🌪️ Climate Emergency` and Start Courtroom.\n"
            "2. **Courtroom**: Click `Run Debate Round`.\n"
            "3. **Conflict**: Point out the massive difference between Finance (10%) and Climate (40%) on `green_space_pct` and the 🛑 HALT.\n"
            "4. **Override**: Force `green_space_pct` to `35`. Point out the Ripple Effects (Cost increase, Score adjustments).\n"
            "5. **History**: Go to History tab, explain `green_space_pct` to show the full visual timeline.\n"
            "6. **Verdict**: Click Generate Verdict, then `Generate Judge Brief (Gemini)`."
        )
    
    tab1, tab2, tab3, tab4 = st.tabs(["Case Filing", "Courtroom", "History", "Verdict"])
    
    with tab1:
        render_intake_form()
        
    with tab2:
        render_courtroom_view()
        
    with tab3:
        render_history_panel()
        
    with tab4:
        render_verdict_panel()

if __name__ == "__main__":
    main()
