import os
import json

base_dir = r"c:\random\Desktop\NeighbourhoodCourtroom"
os.chdir(base_dir)

directories = [
    ".streamlit",
    "data/scenarios",
    "agents",
    "engine",
    "tools",
    "ui",
    "models",
    "scripts",
    "tests"
]

files = {
    "README.md": "# Neighborhood Courtroom\n\nScaffolding project structure.\n",
    "requirements.txt": "streamlit\npydantic>=2.0.0\nplotly\npytest\npytest-cov\nmypy\nruff\nanthropic\n",
    ".env.example": "ANTHROPIC_API_KEY=your_api_key_here\n",
    ".gitignore": "venv/\n__pycache__/\n.env\n.pytest_cache/\n.mypy_cache/\n.ruff_cache/\n",
    ".pre-commit-config.yaml": """repos:
-   repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.5
    hooks:
    -   id: ruff
        args: [--fix]
    -   id: ruff-format
-   repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
    -   id: mypy
""",
    "pyproject.toml": """[tool.pytest.ini_options]
minversion = "6.0"
addopts = "-ra -q --cov=."
testpaths = [
    "tests",
]

[tool.ruff]
line-length = 88
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
""",
    ".streamlit/secrets.toml.example": "ANTHROPIC_API_KEY=\"your_key_here\"\n",
    "app.py": """\"\"\"
TODO: Streamlit application entry point.
Purpose: Initializes the UI, coordinates debate engine and agent interactions.
Dependencies: streamlit, engine, agents, tools, ui.
Expected public interface: Run via `streamlit run app.py`.
\"\"\"

def main() -> None:
    # TODO: Implement Streamlit UI
    pass

if __name__ == "__main__":
    main()
""",
}

# Add data files (empty json dicts)
data_files = [
    "cities.json", "demographics.json", "climate.json", "walkability.json", 
    "construction_costs.json", "land_use.json", "scenarios/phoenix_vacant_lot.json", 
    "scenarios/detroit_brownfield.json", "scenarios/denver_transit_hub.json"
]
for data_file in data_files:
    files[f"data/{data_file}"] = "{\n}\n"

# Python modules stubs
modules = {
    "agents": ["base_agent", "finance_agent", "climate_agent", "community_agent", "orchestrator"],
    "engine": ["state", "conflict", "debate", "override"],
    "tools": ["data_loader", "cost_calculator", "scorer", "diff"],
    "ui": ["input_panel", "debate_view", "proposal_view", "schematic", "charts"],
    "models": ["proposal", "agent_output", "conflict", "debate_round"],
    "scripts": ["preprocess_data", "validate_dataset"]
}

for folder, mods in modules.items():
    files[f"{folder}/__init__.py"] = ""
    for mod in mods:
        filename = f"{folder}/{mod}.py"
        files[filename] = f'"""\nTODO: Module {mod} in {folder}.\nPurpose: Provide specific functionality for {mod}.\nDependencies: logging, typing, related models.\nExpected public interface: Main class or functions for {mod}.\n"""\nfrom typing import Any\n\ndef dummy_{mod}() -> None:\n    pass\n'

# Test files stubs
test_files = [
    "test_proposal", "test_agent_output", "test_debate_round", "test_conflict_model",
    "test_data_loader", "test_cost_calculator",
    "test_state", "test_conflict", "test_debate", "test_override",
    "test_base_agent", "test_finance_agent", "test_climate_agent", "test_community_agent",
    "test_ui"
]

files["tests/__init__.py"] = ""
files["tests/conftest.py"] = '"""\nTODO: Pytest fixtures for the testing suite.\nPurpose: Shared setup and mocking.\nDependencies: pytest, models.\nExpected public interface: pytest fixtures.\n"""\nimport pytest\nfrom typing import Generator, Any\n\n@pytest.fixture\ndef sample_fixture() -> Generator[Any, None, None]:\n    # TODO: Setup fixture\n    yield None\n    # TODO: Teardown fixture\n'

for test_mod in test_files:
    filename = f"tests/{test_mod}.py"
    files[filename] = f'"""\nTODO: Tests for {test_mod.replace("test_", "")}.\nPurpose: Validate the behavior of {test_mod.replace("test_", "")}.\nDependencies: pytest, {test_mod.replace("test_", "")} module.\nExpected public interface: pytest test functions.\n"""\nimport pytest\nfrom typing import Any\n\ndef test_{test_mod.replace("test_", "")}_initialization(sample_fixture: Any) -> None:\n    # TODO: Arrange, Act, Assert\n    assert True\n'

for d in directories:
    os.makedirs(os.path.join(base_dir, d), exist_ok=True)

for f, content in files.items():
    filepath = os.path.join(base_dir, f)
    with open(filepath, "w", encoding="utf-8") as file:
        file.write(content)

# Now write the markdown output file
output_md = []
output_md.append("```text\\nneighborhood-courtroom/")

def generate_tree(dir_path, prefix=""):
    entries = sorted(os.listdir(dir_path))
    # filter out hidden/system things except .streamlit etc if they are relevant
    entries = [e for e in entries if e not in [".git", "venv", "__pycache__", "scaffold.py", "output.md", "Architectutre.md"]]
    
    for i, entry in enumerate(entries):
        is_last = (i == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        output_md.append(f"{prefix}{connector}{entry}")
        
        full_path = os.path.join(dir_path, entry)
        if os.path.isdir(full_path):
            extension_prefix = "    " if is_last else "│   "
            generate_tree(full_path, prefix + extension_prefix)

generate_tree(base_dir)
output_md.append("```\\n")

for f, content in files.items():
    output_md.append(f"### `{f}`\\n")
    if f.endswith(".json"):
        output_md.append("```json\\n" + content.strip() + "\\n```\\n")
    elif f.endswith(".yaml") or f.endswith(".yml"):
        output_md.append("```yaml\\n" + content.strip() + "\\n```\\n")
    elif f.endswith(".toml"):
        output_md.append("```toml\\n" + content.strip() + "\\n```\\n")
    elif f.endswith(".md"):
        output_md.append("```markdown\\n" + content.strip() + "\\n```\\n")
    elif f.endswith(".txt") or f.endswith(".example") or f == ".gitignore":
        output_md.append("```text\\n" + content.strip() + "\\n```\\n")
    else:
        output_md.append("```python\\n" + content.strip() + "\\n```\\n")

with open(os.path.join(base_dir, "output.md"), "w", encoding="utf-8") as f:
    f.write("\\n".join(output_md).replace("\\n", "\\n"))
