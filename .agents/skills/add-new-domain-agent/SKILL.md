---
name: add-new-domain-agent
description: Use when the user asks to add a new agent, create a new domain perspective, or extend the courtroom system with an additional stakeholder or agent class.
---

# Adding a New Domain Agent to NeighbourhoodCourtroom

This guide provides instructions for correctly adding a new domain agent to the courtroom system based on existing architectural conventions established by `FinanceAgent`, `ClimateAgent`, and `CommunityAgent`.

## 1. Subclassing `BaseAgent`

Create a new file in `agents/<domain>_agent.py` (e.g., `agents/traffic_agent.py`). Your agent must inherit from `agents.base_agent.BaseAgent`.

### Required Class Attributes & Properties
- `PERSONALITY_BRIEF`: A vivid archetype description defining the agent's background, speaking style, and focus (e.g., grounded specifics vs. financial formulas).
- `RISK_TOLERANCE`: A clear statement of the agent's risk tolerance regarding its domain metrics.
- `agent_name`: Property returning the lowercase string identifier of the agent (e.g., `"traffic"`).
- `personality_brief`: Property returning `self.PERSONALITY_BRIEF`.
- `risk_tolerance`: Property returning `self.RISK_TOLERANCE`.

## 2. Registering Tools

If your agent requires data tools (e.g., fetching traffic metrics or land use), define them in the `tool_declarations` property and implement their execution in `execute_tool_call`.

```python
@property
def tool_declarations(self) -> list[Any]:
    return [
        {
            "name": "get_traffic_data",
            "description": "Get traffic flow data for a city.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "city_slug": {"type": "STRING"}
                },
                "required": ["city_slug"]
            }
        }
    ]

def execute_tool_call(self, name: str, args: dict[str, Any]) -> Any:
    if name == "get_traffic_data":
        return self.data_loader.get_traffic_data(args["city_slug"])
    return super().execute_tool_call(name, args)
```

## 3. Implementing `evaluate` and `generate_opinion`

- `generate_opinion`: Forward calls to `super().generate_opinion(...)` to enable Gemini-based generation for Round 1 (independent) and Round 2 (rebuttal).
- `evaluate`: Implement the deterministic fallback evaluation logic. Calculate a score (0.0 to 100.0). If the score is `< 85.0`, set verdict to `"modify"` and populate `changes` with proposed parameter adjustments. If `>= 85.0`, set verdict to `"accept"` and leave `changes` empty. Always return `self.build_output(...)`.

## 4. Registering the Agent in the System

You must register your new agent by adding an instance of it (e.g., `TrafficAgent(data_loader)`) to the agent list constructed in `app.py` wherever `ClimateAgent`, `FinanceAgent`, and `CommunityAgent` are currently instantiated together. 

Note that this agent list appears in more than one place in `app.py`:
1. **Main Debate Flow**: Inside `stage_debating()` (around line 554), where agents are instantiated for the initial rounds.
2. **Override / Re-negotiation Flow**: Inside `stage_override_debating()` (around line 895), where agents are instantiated for the post-override re-negotiation rounds.

Both locations must have the new agent added consistently to ensure it participates in both the main debate and any subsequent human override sessions.

## 5. Writing Unit Tests

Create `tests/test_<domain>_agent.py` following the structure in `tests/test_community_agent.py`.
Verify:
- Successful initialization and correct properties (`agent_name`, `personality_brief`).
- `evaluate()` fallback logic produces correct verdicts (`accept`, `modify`) and filters unknown parameters.
- Tool execution correctly dispatches to `DataLoader`.
