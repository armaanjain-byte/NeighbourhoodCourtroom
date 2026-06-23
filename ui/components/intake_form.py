import streamlit as st

from engine.state import create_initial_proposal
from engine.session import create_session
from engine.history import AuditHistory

def render_intake_form():
    st.header("Case Filing")
    st.write("Submit a new neighborhood proposal to the courtroom for debate.")
    
    cities = st.session_state.data_loader.list_available_cities()
    
    st.subheader("Demo Scenarios")
    scenarios = {
        "climate_emergency": {
            "name": "🌪️ Climate Emergency", "city": "seattle_wa", "housing": 100, "green": 0.0, "parking": 200,
            "conflict_desc": "Finance vs Climate\n\nParameter:\ngreen_space_pct"
        },
        "budget_crisis": {
            "name": "📉 Budget Crisis", "city": "detroit_mi", "housing": 500, "green": 5.0, "parking": 50,
            "conflict_desc": "Finance vs Community\n\nParameter:\ncommunity_center_sqft"
        },
        "growth_explosion": {
            "name": "🏗️ Growth Explosion", "city": "austin_tx", "housing": 1000, "green": 20.0, "parking": 50,
            "conflict_desc": "Community vs Finance\n\nParameter:\nparking_spaces"
        },
        "balanced_city": {
            "name": "⚖️ Balanced City", "city": "phoenix_az", "housing": 200, "green": 20.0, "parking": 150,
            "conflict_desc": "Minor adjustments expected."
        }
    }
    
    cols = st.columns(4)
    for idx, (key, sdata) in enumerate(scenarios.items()):
        if cols[idx].button(sdata["name"]):
            st.session_state.active_scenario = key
            st.rerun()
            
    active_key = st.session_state.get("active_scenario")
    if active_key and active_key in scenarios:
        sdata = scenarios[active_key]
        st.info(f"**Expected Conflict**\n\n{sdata['conflict_desc']}")
        
        default_city = sdata["city"]
        default_housing = sdata["housing"]
        default_green = sdata["green"]
        default_parking = sdata["parking"]
    else:
        default_city = cities[0]
        default_housing = 100
        default_green = 20.0
        default_parking = 150
        
    st.markdown("---")
        
    with st.form("intake_form"):
        city_index = cities.index(default_city) if default_city in cities else 0
        
        city_slug = st.selectbox("City", cities, index=city_index)
        housing_units = st.number_input("Housing Units", min_value=0, value=default_housing)
        green_space_pct = st.number_input("Green Space (%)", min_value=0.0, max_value=100.0, value=default_green)
        parking_spaces = st.number_input("Parking Spaces", min_value=0, value=default_parking)
        
        submitted = st.form_submit_button("Start Courtroom")
        
        if submitted:
            if "active_scenario" in st.session_state:
                del st.session_state["active_scenario"]
                
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
            st.session_state.previous_proposal = initial_proposal
            
            st.success("Case filed! Navigate to the Courtroom tab to begin debates.")
