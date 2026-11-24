# SRE Triage & Postmortem Commander (`sre-triage-agent`)

> **Enterprise Agents Track** — Built with **Google Agent Development Kit (ADK-Python)**, **MCP**, **A2A**, **OpenTelemetry**, **FastAPI**, **Docker**, **Terraform**, and **GitHub Actions**.

## Problem & Solution

**Problem:** During high-severity production outages, on-call engineers lose critical Mean Time to Recovery (MTTR) manually jumping between alerting dashboards, application logs, deployment pipelines, runbooks, and stale postmortems—and then spend hours writing blameless postmortems afterward.

**Solution:** **SRE Triage & Postmortem Commander** is a production-structured multi-agent system built with Google ADK that:
1. Triages firing alerts and classifies severity (`SEV1`–`SEV4`).
2. Fans out in **parallel** across logs/metrics, recent deployments, runbooks, and **persistent institutional memory** of past incidents.
3. Iteratively refines and **safety-audits** a remediation plan via a Planner/Critic loop, enforcing **human-in-the-loop approval guardrails** before any production-mutating action.
4. Generates a downloadable **blameless postmortem artifact** and persists new lessons into long-term SQLite memory so future triage gets smarter over time.

---

## Architecture Overview

```mermaid
flowchart LR
    U([On-Call Engineer / A2A]) --> CMD[sre_incident_commander<br/>LlmAgent]
    CMD --> PIPE[incident_triage_pipeline<br/>SequentialAgent]
    PIPE --> S1[1. Intake Agent]
    S1 --> S2[2. Parallel Investigation<br/>Logs+Metrics | Deploys | Runbooks+Memory]
    S2 --> S3[3. Remediation Loop<br/>Planner <-> Safety Critic]
    S3 --> S4[4. Postmortem Agent<br/>Markdown Artifact + SQLite Memory]
```

See [docs/architecture.md](docs/architecture.md) for the full design, security model, and state flow.

---

## Alignment with Evaluation Criteria

| Pillar | Implementation in This Repo |
| :--- | :--- |
| **1. Tool & Interface Design** | Typed ADK tools with defensive validation (`sre_triage_agent/tools/`), Pydantic v2 schemas (`schemas.py`), FastMCP stdio server (`mcp_server/ops_mcp_server.py` + optional `McpToolset`), FastAPI REST API + ADK Web UI + A2A Agent Card (`server/app.py`). |
| **2. Context & Memory** | Short-term structured handoffs via ADK session `state` (`output_key`), bounded log windows for context hygiene, persistent SQLite institutional memory (`memory/incident_memory.py`), `DatabaseSessionService` factory (`memory/session_factory.py`), and Markdown postmortem artifacts (`tools/artifact_tools.py`). |
| **3. Orchestration & Logic** | Hybrid LLM router (`root_agent`) + 4-stage `SequentialAgent` + 3-way `ParallelAgent` + `LoopAgent` (`remediation_planner` ↔ `safety_critic` with `escalate` exit) + `before_tool_callback` HITL approval gate & `before_model_callback` PII/secret redaction (`callbacks.py`). |
| **4. Observability & Tracing** | OpenTelemetry `TracerProvider` (`console` / `otlp` / `gcp_trace`), structured JSON logging with `trace_id` correlation, runtime `/metrics` endpoint (`observability.py`), plus `adk eval` golden dataset (`eval/sre_triage.evalset.json`) and CI-safe offline evaluator (`eval/run_evals.py`). |
| **5. Infrastructure & CI/CD** | Multi-stage non-root `Dockerfile`, GCP Cloud Run + Artifact Registry + least-privilege IAM Terraform IaC (`deployment/terraform/`), and GitHub Actions CI + Cloud Run CD (`.github/workflows/`). |

---

## Quickstart

### 1. Install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Add your GOOGLE_API_KEY (or set GOOGLE_GENAI_USE_VERTEXAI=TRUE with GCP credentials)
```

### 2. Run Interactively with ADK Web UI or CLI
```bash
# Interactive ADK Web UI (recommended for demos)
adk web .

# Terminal CLI
adk run sre_triage_agent
```

### 3. Run the Production FastAPI + A2A Server
```bash
uvicorn server.app:app --host 0.0.0.0 --port 8080 --reload
```
Endpoints:
- `GET /healthz` & `GET /readyz` — Cloud Run health probes
- `GET /metrics` — Live tool latency, token usage, and guardrail metrics
- `GET /.well-known/agent.json` — Agent2Agent (A2A) discovery card
- `GET /api/v1/memory` — Inspect persisted historical incident memories
- `POST /api/v1/triage` — Invoke the Incident Commander programmatically

### 4. Run the Standalone MCP Server
```bash
python3 -m sre_triage_agent.mcp_server.ops_mcp_server
```
To route agent telemetry calls through the MCP server via ADK `McpToolset`, set `SRE_USE_MCP_TOOLS=true` in `.env`.

---

## Sample Prompts to Try

1. **Quick fleet status:**
   > `What production alerts are currently firing?`
2. **Institutional memory lookup:**
   > `Have we seen a DB connection pool exhaustion issue on payments-api before?`
3. **Full 4-stage incident triage & postmortem:**
   > `Triage the SEV1 outage on payments-api, identify the root cause, propose a safe remediation plan, and generate a blameless postmortem.`
4. **Human-in-the-loop guardrail demo:**
   > `Roll back payments-api to v2.18.3 immediately.` *(Blocked by `before_tool_callback` until an approval token is provided.)*
   > `Approved — use human_approval_token="ONCALL-ACK-412" to execute the rollback.`

---

## Testing, Linting & Evaluations

```bash
# Lint & typecheck
ruff check sre_triage_agent server eval tests
mypy sre_triage_agent server

# Unit & API tests
pytest

# Deterministic offline evaluation (CI-safe, no API key required)
python3 -m eval.run_evals --mode offline

# Live ADK trajectory + response evaluation (requires GOOGLE_API_KEY or Vertex AI)
adk eval sre_triage_agent eval/sre_triage.evalset.json --config_file_path eval/test_config.json
```

---

## Deployment (Docker & Terraform on Cloud Run)

```bash
# Local container build & smoke test
docker build -t sre-triage-agent:latest .
docker run --rm -p 8080:8080 --env-file .env sre-triage-agent:latest

# Provision GCP Cloud Run, Artifact Registry, and IAM via Terraform
cd deployment/terraform
terraform init
terraform plan \
  -var="project_id=YOUR_GCP_PROJECT" \
  -var="container_image=us-central1-docker.pkg.dev/YOUR_GCP_PROJECT/sre-triage-agent/sre-triage-agent:latest"
```
