# Neighbourhood Courtroom ⚖️
An AI-driven simulation engine where specialized LLM agents debate and negotiate urban planning trade-offs.

**Live demo:** [https://neighbourhood-courtroom.demo.app](https://neighbourhood-courtroom.demo.app)

---

## The core idea
Urban planning decisions often fail because they are designed in silos. A finance department will optimize purely for cost, ignoring the long-term environmental impacts. An environmental team will push for maximum green space without accounting for housing density demands or budget constraints. When humans finally meet to reconcile these disconnected plans, it usually results in compromised, zero-sum outcomes where trade-offs are misunderstood.

This application solves this by modeling the urban planning process as a multi-agent debate. Three specialized AI agents (Finance, Climate, and Community) are instantiated with genuinely different, partitioned datasets. They must negotiate a unified city proposal across multiple rounds, explicitly addressing their opponents' proposals to arrive at a balanced, data-driven consensus.

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

3. **Human override with causal chain:** You act as the judge. If you manually lock a parameter (e.g., forcing Housing Density to 35%), you don't just see a new final state. The system maps the causal chain:
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

## Run locally
```bash
pip install -r requirements.txt
export GEMINI_API_KEY=your-api-key-here
streamlit run app.py
```
