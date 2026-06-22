import streamlit as st

from engine.state import MUTABLE_PARAMETERS

def render_courtroom_view():
    st.header("Neighborhood Courtroom")
    
    session = st.session_state.session
    if not session:
        st.warning("Please file a case in the Intake Form first.")
        return
        
    proposal = session.get_current_state()
    audit = st.session_state.audit
    agents = st.session_state.agents
    cost_calculator = st.session_state.cost_calculator
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        st.subheader("Current Proposal")
        st.metric("Housing Units", proposal.housing_units)
        st.metric("Green Space", f"{proposal.green_space_pct}%")
        st.metric("Parking Spaces", proposal.parking_spaces)
        st.metric("Community Center Sqft", proposal.community_center_sqft)
        st.metric("Estimated Cost", f"${proposal.estimated_cost:,.2f}")
        st.metric("Version", proposal.version)
        st.info(f"Session Status: {session.status}")
        
    with col2:
        st.subheader("Agent Outputs")
        
        # Evaluate deterministically for UI display
        agent_outputs = {}
        for agent in agents:
            agent_outputs[agent.agent_name] = agent.evaluate(proposal, {})
            
        # Agent Avatars mapping
        agent_emojis = {
            "finance": "👔",
            "climate": "🌳",
            "community": "🏘️"
        }
        
        agent_cols = st.columns(len(agent_outputs))
        for idx, (name, output) in enumerate(agent_outputs.items()):
            with agent_cols[idx]:
                emoji = agent_emojis.get(name.lower(), "🤖")
                st.markdown(f"**{emoji} {name.capitalize()}**")
                st.caption(f"Verdict: {output.verdict} | Score: {output.score:.1f}")
                for param, val in output.proposed_changes.items():
                    current_val = getattr(proposal, param, 0.0)
                    delta = val - current_val
                    st.metric(param, f"{val:g}", f"{delta:+g}")
                
        if session.status in ["CREATED", "IN_PROGRESS"]:
            if st.button("Run Debate Round"):
                round_number = len(session.debate_rounds) + 1
                
                # Record decisions to history
                for name, output in agent_outputs.items():
                    for param, val in output.proposed_changes.items():
                        audit.record_decision(round_number, name, param, val)
                        
                # Execute round
                debate_round = session.run_round(agents, {}, cost_calculator)
                
                # Record conflicts and resolutions
                for conflict in debate_round.detected_conflicts:
                    audit.record_conflict(round_number, conflict)
                    if conflict.disagreement_severity == "high":
                        audit.record_resolution(round_number, conflict.parameter, "human review required")
                    else:
                        # Auto-resolved
                        # The exact resolved value is on the updated proposal
                        new_val = getattr(session.get_current_state(), conflict.parameter)
                        audit.record_resolution(round_number, conflict.parameter, "auto-resolved", new_val)
                        
                st.rerun()
                
    with col3:
        st.subheader("Conflict Panel")
        if session.debate_rounds:
            last_round = session.debate_rounds[-1]
            if last_round.detected_conflicts:
                for c in last_round.detected_conflicts:
                    if c.disagreement_severity == "high":
                        st.error(f"🛑 **HIGH CONFLICT: {c.parameter}**\n\n{c.agent_a.capitalize()} vs {c.agent_b.capitalize()}")
                    elif c.disagreement_severity == "medium":
                        st.warning(f"⚠️ **{c.parameter}** ({c.agent_a} vs {c.agent_b})")
                    else:
                        st.success(f"✅ **{c.parameter}** ({c.agent_a} vs {c.agent_b})")
            else:
                st.success("No conflicts in last round.")
        else:
            st.write("No rounds run yet.")
            
        st.markdown("---")
        st.subheader("Judge Overrides")
        st.write("Force a parameter to a specific value and lock it.")
        
        with st.form("override_form"):
            param = st.selectbox("Parameter", list(MUTABLE_PARAMETERS))
            val = st.number_input("Value")
            submit_override = st.form_submit_button("Apply Override")
            
            if submit_override:
                if session.status == "COMPLETED":
                    st.error("Session completed. Cannot override.")
                else:
                    old_cost = proposal.estimated_cost
                    session.apply_override(param, val)
                    audit.record_override(len(session.debate_rounds), param, val)
                    new_cost = session.get_current_state().estimated_cost
                    cost_delta = new_cost - old_cost
                    
                    st.toast(f"Override applied! Cost changed by ${cost_delta:,.2f}", icon="⚠️")
                    st.rerun()
