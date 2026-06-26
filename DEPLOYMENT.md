# Deploying to Google Cloud Run 🚀

This guide documents how to deploy **Neighbourhood Courtroom** as a containerized application on [Google Cloud Run](https://cloud.google.com/run) — the production deployment path referenced in the course's Day 5 "Prototype to Production" material.

> **Why Cloud Run, not Vertex AI Agent Engine?**
> The course names two Google Cloud production paths: Cloud Run (any containerized app) and Vertex AI Agent Engine (ADK-shaped `Agent` objects). This project implements a custom multi-agent architecture that does **not** use ADK's `Agent` class, making Agent Engine architecturally incompatible. Cloud Run is the correct, honest fit — it accepts any OCI container and imposes no framework constraints.

---

## 📋 Prerequisites

Before running any commands, ensure the following are in place:

### 1. Google Cloud Project
- A Google Cloud project with **billing enabled**
- Note your **Project ID** (e.g., `my-project-123`) — you'll use it throughout

### 2. APIs Enabled
```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com
```

### 3. gcloud CLI Installed & Authenticated
```bash
# Install: https://cloud.google.com/sdk/docs/install
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud config set run/region us-central1
```

### 4. Set a shell variable for convenience
```bash
export PROJECT_ID=YOUR_PROJECT_ID
export REGION=us-central1
export IMAGE=us-central1-docker.pkg.dev/$PROJECT_ID/neighbourhood-courtroom/app
```

---

## 🗝️ Step 1: Store Secrets in Secret Manager (Recommended)

Google Secret Manager is the **production-recommended** approach for API keys on Cloud Run — keys are never stored as plain environment variables or in the container image.

```bash
# Store your Gemini API key as a secret
echo -n "your-gemini-api-key-here" | \
  gcloud secrets create GEMINI_API_KEY \
    --data-file=- \
    --replication-policy=automatic

# If you also have Groq / OpenRouter failover keys:
echo -n "your-groq-api-key-here" | \
  gcloud secrets create GROQ_API_KEY --data-file=- --replication-policy=automatic

echo -n "your-openrouter-api-key-here" | \
  gcloud secrets create OPENROUTER_API_KEY --data-file=- --replication-policy=automatic
```

> **Acceptable interim**: If you prefer to skip Secret Manager for a quick demo, you can pass `GEMINI_API_KEY` as a plain `--set-env-vars` flag in Step 4. This is documented below. **Never** commit the key to the image or repository.

---

## 📦 Step 2: Create the Artifact Registry Repository

Artifact Registry is where the container image is stored before Cloud Run pulls it.

```bash
gcloud artifacts repositories create neighbourhood-courtroom \
  --repository-format=docker \
  --location=$REGION \
  --description="Neighbourhood Courtroom container images"
```

---

## 🔨 Step 3: Build & Push the Container Image

This uses **Cloud Build** to build the image remotely on Google's infrastructure — **no local Docker installation required**.

```bash
# From the project root (where Dockerfile lives)
gcloud builds submit \
  --tag $IMAGE \
  --project $PROJECT_ID
```

Cloud Build will:
1. Upload the project source (respecting `.dockerignore`)
2. Build the Docker image using your `Dockerfile`
3. Push the built image to Artifact Registry automatically

Typical build time: 3–5 minutes on first build (subsequent builds are faster due to layer caching).

---

## 🚀 Step 4: Deploy to Cloud Run

### Option A: With Secret Manager (Recommended)

Grant Cloud Run's service account access to the secrets first:

```bash
# Get the default compute service account email
SA_EMAIL=$(gcloud iam service-accounts list \
  --filter="displayName:Compute Engine default service account" \
  --format="value(email)")

# Grant access to each secret
for SECRET in GEMINI_API_KEY GROQ_API_KEY OPENROUTER_API_KEY; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor" 2>/dev/null || true
done
```

Then deploy with secrets mounted as environment variables:

```bash
gcloud run deploy neighbourhood-courtroom \
  --image $IMAGE \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --set-secrets "GEMINI_API_KEY=GEMINI_API_KEY:latest" \
  --set-env-vars "LLM_PROVIDER_CHAIN=gemini,LLM_DAILY_BUDGET=200"
```

### Option B: Plain Environment Variables (Quick Demo / Interim)

```bash
gcloud run deploy neighbourhood-courtroom \
  --image $IMAGE \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars "GEMINI_API_KEY=your-api-key-here,LLM_PROVIDER_CHAIN=gemini,LLM_DAILY_BUDGET=200"
```

> ⚠️ With Option B, the key is visible in `gcloud run services describe` output and Cloud Run console. Use Option A for any non-throwaway deployment.

On success, the command prints:
```
Service [neighbourhood-courtroom] revision [neighbourhood-courtroom-00001-xxx] has been deployed
and is serving 100 percent of traffic.
Service URL: https://neighbourhood-courtroom-xxxxxxxxxx-uc.a.run.app
```

---

## 🛡️ Why `LLM_DAILY_BUDGET=200`?

In a shared, publicly accessible hosted environment, multiple judges and evaluators may test the application simultaneously.

Setting `LLM_DAILY_BUDGET=200` establishes a conservative, sensible safeguard:
- **Accommodates multi-turn evaluation**: Supports 5–10 judges running 1–3 round debate sessions (each involving multiple domain agent calls) without prematurely cutting off LLM interactions.
- **Graceful fallback**: Once 200 calls are reached, the system shifts to its built-in deterministic mathematical fallback engine (`_fallback_opinion`) — the app continues functioning perfectly rather than crashing.
- **Uninterrupted access**: No raw stack traces presented to evaluators; the session completes end-to-end regardless of quota state.

---

## 🔍 Step 5: Verify the Deployment

### Health Check
Visit the Service URL printed by the deploy command. You should see the Neighbourhood Courtroom UI within ~10 seconds (first request may take slightly longer due to cold start).

### Run a Full End-to-End Test
1. Submit a proposal (e.g., Phoenix AZ, 25% green space, 500 housing units)
2. Watch the live debate stream — Round 1 and Round 2
3. Check the **Courtroom Verdict** page loads with agent scores and transcript
4. Test the **Override Slider** component (the custom Streamlit component most likely to behave differently in a fresh container)
5. Lock a parameter and watch the re-negotiation stream

### View Logs
```bash
# Stream live logs
gcloud run services logs read neighbourhood-courtroom \
  --region $REGION \
  --limit 50

# Or tail in real time
gcloud beta run services logs tail neighbourhood-courtroom \
  --region $REGION
```

Common log patterns to look for:
- `[STARTUP SANITY CHECK] LLM_PROVIDER configured: GEMINI` — confirms env vars loaded correctly
- `Gemini call succeeded` — confirms API connectivity
- Any `ERROR` lines — investigate with `--limit 200` for more context

---

## 🔄 Redeploying After Code Changes

```bash
# Rebuild and push a new image
gcloud builds submit --tag $IMAGE --project $PROJECT_ID

# Redeploy (reuses all existing config — secrets, env vars, etc.)
gcloud run deploy neighbourhood-courtroom \
  --image $IMAGE \
  --region $REGION \
  --platform managed
```

---

## ↩️ Rollback

```bash
# List all revisions
gcloud run revisions list --service neighbourhood-courtroom --region $REGION

# Roll back to a previous revision
gcloud run services update-traffic neighbourhood-courtroom \
  --region $REGION \
  --to-revisions PREVIOUS_REVISION_NAME=100
```

---

## 🗑️ Teardown (When Done)

```bash
# Delete the Cloud Run service
gcloud run services delete neighbourhood-courtroom --region $REGION

# Delete the container image repository
gcloud artifacts repositories delete neighbourhood-courtroom --location $REGION

# Delete secrets (if no longer needed)
gcloud secrets delete GEMINI_API_KEY
```

---

## 📁 Files Added for Container Deployment

| File | Purpose |
|------|---------|
| `Dockerfile` | Container build instructions; uses `python:3.12-slim`, installs runtime deps, sets `$PORT`-aware entrypoint |
| `.dockerignore` | Excludes `.git`, `.venv`, `.env`, `tests/`, `__pycache__`, etc. from the image |
| `requirements-dev.txt` | Dev-only deps (`pytest`, `ruff`, etc.) excluded from the production image |
| `requirements.txt` | Runtime-only deps installed in the container |
