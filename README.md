# Neighbourhood Courtroom ⚖️
An AI-driven simulation engine where specialized LLM agents debate and negotiate urban planning trade-offs.

**Live demo:** [https://neighbourhood-courtroom.demo.app](https://neighbourhood-courtroom.demo.app)

---

## The core idea
Urban planning decisions often fail because they are designed in silos. A finance department will optimize purely for cost, ignoring the long-term environmental impacts. An environmental team will push for maximum green space without accounting for housing density demands or budget constraints. When humans finally meet to reconcile these disconnected plans, it usually results in compromised, zero-sum outcomes where trade-offs are misunderstood.

This application solves this by modeling the urban planning process as a multi-agent debate. Three specialized AI agents (Finance, Climate, and Community) are instantiated with genuinely different, partitioned datasets and sharp, distinctive real-world personality archetypes. They must negotiate a unified city proposal across multiple rounds, explicitly addressing their opponents' proposals to arrive at a balanced, data-driven consensus.

### Agent Personality Archetypes
- **💰 Finance Agent**: Archetype of a pragmatic municipal budget officer who has personally seen projects fail from severe cost overruns. Skeptical of unfunded idealism, values measurable ROI and strict budget discipline, but remains dedicated to practical civic development. *(Risk tolerance: Low on budget overruns)*
- **🌿 Climate Agent**: Archetype of a field-experienced urban resilience planner who has seen specific climate failures (heat islands, severe flood damage) up close. Highly evidence-driven and urgent about immediate physical risks, but maintains a calm, non-alarmist tone. *(Risk tolerance: Low on environmental harm and climate vulnerability)*
- **🏘️ Community Agent**: Archetype of a longtime resident-advocate who has sat through countless public hearings and knows exactly what real residents complain about. Grounded in lived specifics and daily community needs, avoiding abstract policy jargon to keep human impact front and center. *(Risk tolerance: Low on displacement and inequity)*


## What makes this different from a chatbot
Unlike a standard single-prompt LLM asking to "balance a budget," this system enforces adversarial truth-seeking through architectural constraints:

1. **Agent information partitioning:** Agents do not share a hive-mind. They use Gemini's function calling to fetch only the data relevant to their persona.
   | Agent | Sees Construction Cost? | Sees Heat Risk? | Sees Walkability? |
   |-------|------------------------|-----------------|-------------------|
   | 💰 Finance | ✓ Yes | ✗ No | ✗ No |
   | 🌿 Climate | ✗ No | ✓ Yes | ✗ No |
   | 🏘️ Community | ✗ No | ✗ No | ✓ Yes |

2. **Real conflict output:** Agents actively review and reject each other's outputs based on their own localized data. For example:
   * **Finance Agent** proposed reducing green space to 12% to stay under budget.
   * **Climate Agent** objected: *"Finance wants to cut parks to 12% to save money, but that leaves zero shade in a city where summer temperatures hit 104°F."*

3. **Hybrid Conflict Resolution:** While Round 2 LLM agents generate the quantitative proposals via explicit cross-agent rebuttal (e.g., proposing to reduce green space to 12% in response to another agent's demands), the actual arbitration of these LLM opinions is handled by a deterministic mathematical conflict engine. This prevents hallucinations during conflict resolution by applying weighted means to low/medium conflicts and flagging high-severity conflicts for human review.

4. **Human override with causal chain:** You act as the judge. If you manually lock a parameter (e.g., forcing Housing Density to 35%), you don't just see a new final state. The system maps the causal chain:
   `Human locked Density at 35%` → `Finance responded: Lowered Infrastructure Bond ceiling` → `Community responded: Increased Transit Demand` → `Engine settled: Balanced equilibrium`.

## Architecture
```text
                  ┌─────────────────┐
                  │ Proposal State  │
                  └────────┬────────┘
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Finance   │ ──▶ │  Conflict   │ ◀── │   Climate   │
│    Agent    │     │   Engine    │     │    Agent    │
└─────────────┘     └─────────────┘     └─────────────┘
                           ▲
                           │
                    ┌─────────────┐
                    │  Community  │
                    │    Agent    │
                    └─────────────┘
```

## Data sources
* **ACS 2022**: American Community Survey demographics and housing data
* **NOAA / ASHRAE**: Historical climate data, heat island risk, and HVAC load metrics
* **RSMeans**: Construction cost estimation indexes
* **Walk Score**: Neighborhood walkability and transit access metrics

## Prerequisites
- **Python**: Python 3.10 or higher.
- **API Key**: A valid [Google Gemini API Key](https://aistudio.google.com/app/apikey) with access to the `gemini-2.5-flash` model.

## Run locally
```bash
pip install -r requirements.txt
export GEMINI_API_KEY=your-api-key-here
streamlit run app.py
```

## Running tests
To verify the entire test suite cleanly without external API calls, run: `python3 -m pytest`


## Security
- **API Keys**: The `GEMINI_API_KEY` is strictly managed via environment variables (e.g., `.env`). It is never committed to the repository and never exposed to the frontend/client.
- **Input Validation**: All proposal parameters submitted via the UI intake form are strictly validated and clamped server-side before reaching the core engine. This prevents invalid types or out-of-bounds parameters (e.g., negative housing units or percentages > 100) from bypassing UI constraints and causing engine failures.
