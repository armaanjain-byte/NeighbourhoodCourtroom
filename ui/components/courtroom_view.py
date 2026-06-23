import streamlit as st

from engine.state import MUTABLE_PARAMETERS

def render_courtroom_view():
    st.header("Neighborhood Courtroom")
    
    session = st.session_state.session
    if not session:
        st.warning("Please file a case in the Intake Form first.")
        return
        
    if session.status == "WAITING_FOR_JUDGE":
        st.error("## ⚖️ CASE STATUS: WAITING FOR JUDGE")
    elif session.status == "COMPLETED":
        st.success("## ⚖️ CASE STATUS: COMPLETED")
    else:
        st.info(f"## ⚖️ CASE STATUS: {session.status.replace('_', ' ')}")
        
    proposal = session.get_current_state()
    audit = st.session_state.audit
    agents = st.session_state.agents
    cost_calculator = st.session_state.cost_calculator
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        st.subheader("Court Record")
        prev = st.session_state.get("previous_proposal", proposal)
        
        dhousing = proposal.housing_units - prev.housing_units
        dgreen = proposal.green_space_pct - prev.green_space_pct
        dparking = proposal.parking_spaces - prev.parking_spaces
        dcenter = proposal.community_center_sqft - prev.community_center_sqft
        dcost = proposal.estimated_cost - prev.estimated_cost
        
        st.metric("Housing Units", proposal.housing_units, f"{dhousing:+g}" if dhousing else None)
        st.metric("Green Space", f"{proposal.green_space_pct}%", f"{dgreen:+g}%" if dgreen else None)
        st.metric("Parking Spaces", proposal.parking_spaces, f"{dparking:+g}" if dparking else None)
        st.metric("Community Center Sqft", proposal.community_center_sqft, f"{dcenter:+g}" if dcenter else None)
        st.metric("Estimated Cost", f"${proposal.estimated_cost:,.2f}", f"${dcost:+,.2f}" if dcost else None)
        st.metric("Version", proposal.version)
        
    with col2:
        st.subheader("Agent Counsel")
        
        # Agent Avatars mapping
        agent_emojis = {
            "finance": "👔",
            "climate": "🌳",
            "community": "🏘️"
        }
        
        # Render the transcript
        if hasattr(session, "transcript") and session.transcript.entries:
            for entry in session.transcript.entries:
                emoji = agent_emojis.get(entry.agent.lower(), "🤖")
                with st.chat_message(name=entry.agent, avatar=emoji):
                    if entry.statement_type == "position":
                        st.markdown(entry.content)
                    elif entry.statement_type == "evidence":
                        st.info(f"**Evidence:** {entry.content}")
                    elif entry.statement_type == "objection":
                        st.error(f"🚨 **Objection to {str(entry.target_agent).capitalize()}:** {entry.content}")
                    elif entry.statement_type == "support":
                        st.success(f"🤝 **Support for {str(entry.target_agent).capitalize()}:** {entry.content}")
        else:
            st.write("No arguments presented yet. Run the debate to begin.")
                
        if session.status in ["CREATED", "IN_PROGRESS"]:
            if st.button("Run Debate Round"):
                st.session_state.previous_proposal = proposal.model_copy(deep=True)
                round_number = len(session.debate_rounds) + 1
                
                # Record decisions to history
                # We need to compute deterministic math first to save to audit since we removed it from UI pre-calc
                agent_outputs = {}
                for agent in agents:
                    out = agent.evaluate(proposal, {})
                    agent_outputs[agent.agent_name] = out
                    for param, val in out.proposed_changes.items():
                        audit.record_decision(round_number, agent.agent_name, param, val)
                        
                with st.spinner("Agents are debating..."):
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
        st.subheader("Judge Bench")
        if session.debate_rounds:
            last_round = session.debate_rounds[-1]
            if last_round.detected_conflicts:
                for c in last_round.detected_conflicts:
                    with st.container(border=True):
                        # Determine severity header
                        if c.disagreement_severity == "high":
                            st.markdown("### 🛑 HIGH CONFLICT")
                            status = "Awaiting Judge Decision"
                            diff_color = "red"
                        elif c.disagreement_severity == "medium":
                            st.markdown("### ⚠️ MEDIUM CONFLICT")
                            status = "Auto-resolved"
                            diff_color = "orange"
                        else:
                            st.markdown("### ✅ LOW CONFLICT")
                            status = "Auto-resolved"
                            diff_color = "green"
                            
                        st.write("**Parameter:**")
                        st.code(c.parameter)
                        
                        emoji_a = agent_emojis.get(c.agent_a.lower(), "🤖")
                        emoji_b = agent_emojis.get(c.agent_b.lower(), "🤖")
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.markdown(f"**{emoji_a} {c.agent_a.capitalize()} Agent**")
                            st.write(f"Proposed: `{c.proposed_value_a:g}`")
                        with col_b:
                            st.markdown(f"**{emoji_b} {c.agent_b.capitalize()} Agent**")
                            st.write(f"Proposed: `{c.proposed_value_b:g}`")
                            
                        diff = abs(c.proposed_value_a - c.proposed_value_b)
                        st.markdown(f"**Difference:** :{diff_color}[{diff:g}]")
                        st.caption(f"**Status:** {status}")
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
                    st.session_state.previous_proposal = proposal.model_copy(deep=True)
                    old_cost = proposal.estimated_cost
                    old_scores = {agent.agent_name: agent.evaluate(proposal, {}).score for agent in agents}
                    old_val = getattr(proposal, param)
                    
                    session.apply_override(param, val)
                    audit.record_override(len(session.debate_rounds), param, val)
                    
                    new_proposal = session.get_current_state()
                    new_cost = new_proposal.estimated_cost
                    cost_delta = new_cost - old_cost
                    new_scores = {agent.agent_name: agent.evaluate(new_proposal, {}).score for agent in agents}
                    
                    st.session_state.last_override_ripple = {
                        "param": param,
                        "old_val": old_val,
                        "new_val": val,
                        "cost_delta": cost_delta,
                        "score_deltas": {name: new_scores[name] - old_scores[name] for name in new_scores}
                    }
                    
                    st.toast(f"Override applied! Cost changed by ${cost_delta:,.2f}", icon="⚠️")
                    st.rerun()
                    
        if "last_override_ripple" in st.session_state:
            st.markdown("---")
            st.subheader("Ripple Effects")
            ripple = st.session_state.last_override_ripple
            
            st.write(f"**Judge Override**")
            st.code(f"{ripple['param']}\n{ripple['old_val']:g} → {ripple['new_val']:g}")
            
            st.write("**Consequences**")
            r_col1, r_col2 = st.columns(2)
            with r_col1:
                st.metric("Estimated Cost", "", f"${ripple['cost_delta']:+,.2f}")
            with r_col2:
                for name, delta in ripple["score_deltas"].items():
                    emoji = agent_emojis.get(name.lower(), "🤖")
                    st.metric(f"{emoji} {name.capitalize()} Score", "", f"{delta:+.1f}")
