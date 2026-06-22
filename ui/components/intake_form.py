import streamlit as st

from engine.state import create_initial_proposal
from engine.session import create_session
from engine.history import AuditHistory

def render_intake_form():
    st.header("Case Filing")
    st.write("Submit a new neighborhood proposal to the courtroom for debate.")
    
    cities = st.session_state.data_loader.list_available_cities()
    
    if st.button("🚨 Load Detroit Crisis Template"):
        st.session_state.load_crisis = True
        st.rerun()
        
    with st.form("intake_form"):
        # Pre-fill crisis template values if triggered
        default_city = "detroit_mi" if st.session_state.get("load_crisis") else cities[0]
        default_housing = 500 if st.session_state.get("load_crisis") else 100
        default_green = 5.0 if st.session_state.get("load_crisis") else 20.0
        default_parking = 50 if st.session_state.get("load_crisis") else 150
        
        city_index = cities.index(default_city) if default_city in cities else 0
        
        city_slug = st.selectbox("City", cities, index=city_index)
        housing_units = st.number_input("Housing Units", min_value=0, value=default_housing)
        green_space_pct = st.number_input("Green Space (%)", min_value=0.0, max_value=100.0, value=default_green)
        parking_spaces = st.number_input("Parking Spaces", min_value=0, value=default_parking)
        
        submitted = st.form_submit_button("Start Courtroom")
        
        if submitted:
            # Clear crisis flag
            if "load_crisis" in st.session_state:
                del st.session_state["load_crisis"]
                
            # Create initial proposal
            initial_proposal = create_initial_proposal(
                city_slug=city_slug,
                housing_units=int(housing_units),
                green_space_pct=float(green_space_pct),
                parking_spaces=int(parking_spaces)
            )
            
            # Compute initial cost
            initial_cost = st.session_state.cost_calculator.calculate_estimated_cost(initial_proposal)
            initial_proposal.estimated_cost = initial_cost
            
            # Create session and history
            st.session_state.session = create_session(initial_proposal)
            st.session_state.audit = AuditHistory()
            
            st.success("Case filed! Navigate to the Courtroom tab to begin debates.")
