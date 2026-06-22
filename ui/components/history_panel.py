import streamlit as st

from engine.state import MUTABLE_PARAMETERS

def render_history_panel():
    st.header("Debate History & Explainability")
    
    session = st.session_state.session
    if not session:
        st.warning("Please file a case in the Intake Form first.")
        return
        
    audit = st.session_state.audit
    
    st.subheader("Explain Parameter")
    st.write("Understand exactly how any parameter reached its current value.")
    
    selected_param = st.selectbox("Select Parameter", list(MUTABLE_PARAMETERS))
    if st.button("Explain"):
        explanation = audit.explain_parameter(selected_param)
        with st.container(border=True):
            st.markdown(explanation)
        
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Audit Overview")
        report = audit.generate_audit_report()
        st.json(report)
        
    with col2:
        st.subheader("Agent Timeline")
        agent_names = ["finance", "climate", "community"]
        selected_agent = st.selectbox("Select Agent", agent_names)
        agent_hist = audit.get_agent_history(selected_agent)
        
        if agent_hist:
            for item in agent_hist:
                st.write(f"**Round {item.round_number}:** Proposed `{item.parameter}` = {item.proposed_value:g}")
        else:
            st.write("No decisions found for this agent.")
            
    st.markdown("---")
    st.subheader("Conflict Timeline")
    conflicts = audit.get_conflict_timeline()
    if conflicts:
        for c in conflicts:
            st.write(f"**Round {c.round_number}:** `{c.parameter}` ({c.severity} severity) - {c.agent_a} ({c.proposed_value_a}) vs {c.agent_b} ({c.proposed_value_b})")
    else:
        st.write("No conflicts logged yet.")
