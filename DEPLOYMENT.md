# Deploying to Streamlit Community Cloud 🚀

This guide documents exactly how to deploy the **Neighbourhood Courtroom** application to [Streamlit Community Cloud](https://streamlit.io/cloud) as a publicly accessible web app with zero login or paywall barriers.

---

## 📋 Pre-Deployment Verification

1. **Self-Contained Architecture**: The custom Streamlit components (`ui_component_dir/index.html` and `ui_component_dir/override_slider/index.html`) are pure static web bundles. They require no external compilation steps, `node_modules`, or system-level binary dependencies, ensuring seamless operation in Streamlit Cloud's containerized Python environment.
2. **Dynamic Path Resolution**: All file paths (including `data/` JSON records and UI assets) use dynamic relative path resolution via Python's `pathlib.Path(__file__)`.
3. **Pinned Requirements**: All packages in `requirements.txt` are explicitly pinned to stable version ranges to prevent upstream dependency breaking.

---

## 🛠️ Step-by-Step Deployment Guide (5 Minutes)

### Step 1: Connect Your GitHub Repository
1. Log into [Streamlit Community Cloud](https://share.streamlit.io/).
2. Click **New app** from the dashboard.
3. Select **Deploy a public app from GitHub**.

### Step 2: Configure the App Settings
Fill in the deployment details as follows:
- **Repository**: Select your GitHub repository (e.g., `armaanjain-byte/NeighbourhoodCourtroom`).
- **Branch**: `main` (or your primary deployment branch).
- **Main file path**: `app.py` (this is the primary entrypoint for the application).
- **App URL**: Customize your public subdomain (e.g., `neighbourhood-courtroom.streamlit.app`).

### Step 3: Configure Environment Secrets & Budget Limits
Before clicking deploy, click on **Advanced settings** (or go to **App Settings -> Secrets** from the dashboard menu) to configure your environment variables in TOML format.

Copy the structure from `.streamlit/secrets.toml.example` and configure your keys, failover chain, and daily budget:

```toml
# Google Gemini API Key for the LLM Provider abstraction
GEMINI_API_KEY = "your-google-gemini-api-key-here"

# Failover Provider Chain Configuration (gemini -> groq -> openrouter)
LLM_PROVIDER_CHAIN = "gemini,groq,openrouter"

# Fallback Provider API Keys (optional)
GROQ_API_KEY = "your-groq-api-key-here"
OPENROUTER_API_KEY = "your-openrouter-api-key-here"

# Set a sensible daily budget appropriate for public/judge traffic
LLM_DAILY_BUDGET = "200"
```

#### 🛡️ Why set `LLM_DAILY_BUDGET = "200"`?
In a shared, publicly accessible hosted environment, multiple judges and evaluators may test the application around the same time. A single enthusiastic visitor (or automated scraper) could easily exhaust the Gemini API free-tier daily quota, rendering the live demo non-functional for subsequent evaluators. 
Setting `LLM_DAILY_BUDGET = "200"` establishes a conservative, sensible safeguard:
- **Accommodates Multi-Turn Evaluation**: A budget of 200 comfortably supports 5 to 10 judges testing 1-to-3 round debate sessions (each involving multiple domain agent calls) without prematurely cutting off their live LLM interactions.
- **Proactive Safeguard**: Once 200 calls are reached, the system gracefully shifts to its built-in deterministic mathematical fallback engine (`_fallback_opinion`).
- **Uninterrupted Access**: Allows the app to continue functioning perfectly end-to-end without crashing or presenting raw stack traces to visitors, fulfilling the deployability requirement for 24/7 public availability.

### Step 4: Deploy!
Click **Deploy**. Streamlit Community Cloud will automatically provision a container, install the pinned packages from `requirements.txt`, and launch `app.py`. Your interactive urban planning simulation will be live and publicly accessible worldwide at `https://neighbourhood-courtroom.streamlit.app` in just a few minutes!
