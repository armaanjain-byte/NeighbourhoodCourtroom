import streamlit as st

def render_verdict_panel():
    st.header("Case Verdict")
    
    session = st.session_state.session
    if not session:
        st.warning("Please file a case in the Intake Form first.")
        return
        
    if session.status != "COMPLETED":
        st.info("The session is not yet completed. You can complete the session here.")
        if st.button("Generate Final Verdict"):
            st.session_state.verdict = session.generate_verdict()
            st.rerun()
            
    if session.status == "COMPLETED" and "verdict" in st.session_state:
        verdict = st.session_state.verdict
        st.success(verdict["audit_summary"])
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Final Proposal")
            final_proposal = verdict["final_proposal"]
            st.metric("Housing Units", final_proposal.housing_units)
            st.metric("Green Space", f"{final_proposal.green_space_pct}%")
            st.metric("Parking Spaces", final_proposal.parking_spaces)
            st.metric("Community Center Sqft", final_proposal.community_center_sqft)
            st.metric("Final Estimated Cost", f"${final_proposal.estimated_cost:,.2f}")
            
        with col2:
            st.subheader("Session Meta")
            st.write(f"**Total Rounds:** {verdict['total_rounds']}")
            st.write(f"**Final Version:** {final_proposal.version}")
            
            st.subheader("Unresolved Conflicts")
            if verdict["unresolved_conflicts"]:
                for c in verdict["unresolved_conflicts"]:
                    st.markdown(f"- :red[{c}]")
            else:
                st.write("None.")
                
            st.subheader("Human Overrides")
            if session.override_history:
                for o in session.override_history:
                    st.write(f"- `{o['parameter']}` overridden to {o['value']} in round {o['round_number']}")
            else:
                st.write("None.")
