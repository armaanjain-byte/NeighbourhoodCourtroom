---
name: extend-conflict-resolution
description: Use when the user asks to modify conflict resolution rules, change agent domain weights, tweak disagreement severity thresholds, or inspect the deterministic conflict engine in engine/conflict.py.
---

# Extending Conflict Resolution in NeighbourhoodCourtroom

This guide provides instructions for safely modifying `engine/conflict.py`'s severity thresholds or resolution weights, while strictly preserving core safety invariants.

## 1. Core Architecture & Design

`engine/conflict.py` implements a fully deterministic disagreement detection and resolution system. It compares the `proposed_changes` dictionaries from multiple `AgentOutput` objects.
- **Fully Deterministic**: No LLM calls, no network access.
- **Severity Levels**: Computed from the relative percentage delta between two proposed values: `delta_pct = |a - b| / max(|a|, |b|) * 100`.
  - `LOW`: difference < 10%
  - `MEDIUM`: difference 10–25%
  - `HIGH`: difference > 25%

## 2. Modifying Severity Thresholds

To adjust the boundaries between LOW, MEDIUM, and HIGH severity, modify `calculate_conflict_severity` in `engine/conflict.py`.

```python
def calculate_conflict_severity(value_a: float, value_b: float) -> str:
    abs_a = abs(value_a)
    abs_b = abs(value_b)
    max_abs = max(abs_a, abs_b)

    if max_abs == 0.0:
        return "low"

    delta_pct = abs(value_a - value_b) / max_abs * 100

    # Modify thresholds here:
    if delta_pct < 10:
        return "low"
    elif delta_pct <= 25:
        return "medium"
    else:
        return "high"
```

## 3. Adjusting Agent Domain Weights

When resolving `MEDIUM` severity conflicts, `resolve_parameter` uses a combined weighted mean: `domain_weight * agent_confidence`.
To update domain weights, modify the `AGENT_WEIGHTS` dictionary in `engine/conflict.py`:

```python
AGENT_WEIGHTS: dict[str, float] = {
    "finance": 0.4,
    "climate": 0.3,
    "community": 0.3,
    # Add new agent weights here, e.g.:
    # "traffic": 0.25,
}

DEFAULT_AGENT_WEIGHT: float = 1.0 / 3  # fallback for unknown agent names
```

## 4. CRITICAL: High Severity Safety Invariant

**SAFETY INVARIANT**: A `HIGH` severity conflict (`delta_pct > 25%`) must **always** escalate to human review regardless of any weighting changes or domain priorities.
- `resolve_parameter` must return `None` when `worst_severity == "high"`.
- `resolve_conflicts` must catch `None` and append the parameter to `human_review_params`, setting `requires_human_review = True`.
- **Never** add an automated override or fallback weighting for `HIGH` severity conflicts. Human-in-the-loop review is a non-negotiable architectural guarantee.

## 5. Verification & Testing

After making changes to `engine/conflict.py`, verify that the deterministic rules and safety invariants are fully intact by running:
```bash
python -m pytest tests/test_conflict.py
```
