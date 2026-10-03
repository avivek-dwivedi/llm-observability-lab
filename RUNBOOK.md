# From Zero — Exact Steps After `docker compose down -v`

> Full wipe of both stacks. Run these commands **in order**. No explanations — just do.
> Companion to [README.md](README.md) (overview) and [docs/](docs/) (per-backend details).

**Prerequisites:** Docker Desktop, Python ≥ 3.11, a Groq API key
(console.groq.com), optionally a LangSmith API key.

---

## 1. Start Langfuse (self-hosted)

> Langfuse runs from its **own official repo**, separate from this project.
> Clone it once; afterwards you just do `docker compose up -d` in that folder.

```powershell
git clone https://github.com/langfuse/langfuse.git D:\langfuse
cd D:\langfuse
docker compose up -d
```

Wait ~30s, then open http://localhost:3000

> Already cloned before? Skip the clone — just `cd` into the folder and
> `docker compose up -d` (optionally `git pull` first to stay current).

## 2. Create Langfuse Account + Project + Keys (only if fresh wipe)

1. http://localhost:3000 → **Sign up** (any email/password)
2. Create org → type any name
3. Create project → type any name
4. Settings → API Keys → Create new API keys
5. Copy `pk-lf-...` (public key) and `sk-lf-...` (secret key)

## 2b. Get LangSmith API Key (SaaS — skip if you don't need LangSmith)

1. Go to https://smith.langchain.com
2. Sign in (or create account)
3. Settings → API Keys → Create API Key
4. Copy `lsv2_pt_...`

## 3. Put Keys in .env

```powershell
cd d:\Observation_Layer
notepad .env
```

Set these lines:
```ini
GROQ_API_KEY=gsk_your_key
GROQ_MODEL=allam-2-7b
LANGFUSE_PUBLIC_KEY="pk-lf-xxxx"
LANGFUSE_SECRET_KEY="sk-lf-xxxx"
LANGSMITH_API_KEY=lsv2_pt_xxxx
LANGSMITH_OTLP_ENDPOINT=https://api.smith.langchain.com/otel
LANGSMITH_PROJECT=llm-observability-lab
ALLOW_LIVE_CALLS=1
```

## 4. Sync Keys to Collector

> Requires the keys from step 3 to be saved in `.env` first.

```powershell
cd d:\Observation_Layer
.\infrastructure\sync-keys.ps1
```

## 5. Start This Stack

```powershell
cd d:\Observation_Layer
docker compose up -d
```

Verify:
```powershell
docker ps --format "{{.Names}} {{.Status}}"
```

Should see: phoenix, prometheus, grafana, otel-collector — all Up.

## 6. Configure Langfuse Model Definition (automatic)

```powershell
cd d:\Observation_Layer
$env:PYTHONPATH = "d:\Observation_Layer"
.venv\Scripts\python.exe infrastructure\setup_langfuse_model.py
```

> This creates the Model Definition via Langfuse API so the Cost dashboard
> shows real $ amounts instead of $0. Reads model name + prices from .env.
> Safe to run multiple times — skips if already exists.

## 6b. Langfuse Built-in Dashboards (automatic)

> Langfuse has its **own** dashboards — completely independent from Grafana.
> They appear **automatically** when traces arrive. No setup needed.

### What Langfuse shows on the Home page (http://localhost:3000 → Home):

| Panel | What it shows | When it appears |
|---|---|---|
| Traces | Total trace count + chart over time | Automatic — any trace |
| Model costs | Total USD | Automatic — after Model Definition (step 6) |
| Model Usage | Cost by model, Usage by model, Cost by type | Automatic — after Model Definition |
| Token usage | Input vs output tokens | Automatic — any trace with token counts |
| Trace latency | P50/P90/P95/P99 per trace name | Automatic — any trace with latency |
| Generation latency | P50/P90/P95/P99 per generation | Automatic — any Completions span |
| Scores | Score averages over time | Automatic — any trace with score attributes |
| User consumption | Cost per user | Automatic — traces with user IDs |

### What Langfuse shows on the Tracing page (http://localhost:3000 → Tracing):

| Column | What it shows |
|---|---|
| Name | Trace name (e.g. `single_call`, `rag_pipeline`, `eval.primary_colors`) |
| Input | Prompt text (clean — no SDK objects) |
| Output | Response text |
| Latency | Duration per trace |
| Tokens | Input → Output (total) |
| Total Cost | USD per trace |
| Scores | Quality scores (for eval traces) |

> **Langfuse dashboards ≠ Grafana dashboards.** They are completely separate:
> - **Langfuse** = trace-level dashboards (cost, latency, scores per trace) — built-in, automatic
> - **Grafana** = system-level dashboards (SLO, error budget, P50-P99 trends) — custom, via Prometheus

## 7. Run Scripts

```powershell
cd d:\Observation_Layer
$env:PYTHONPATH = "d:\Observation_Layer"
$env:PYTHONIOENCODING = "utf-8"

.venv\Scripts\python.exe examples\01_single_call.py
.venv\Scripts\python.exe examples\02_multiple_calls.py
.venv\Scripts\python.exe examples\04_failures.py
.venv\Scripts\python.exe examples\05_batch_dashboard.py
.venv\Scripts\python.exe examples\06_synthetic_metrics.py
.venv\Scripts\python.exe examples\07_evaluation.py
```

### What each script does:

| Script | Traces | Pattern | API calls? | What you see |
|---|---|---|---|---|
| `01_single_call.py` | 1 | Single standalone trace | Yes | 1 trace with clean Input/Output, cost, tokens |
| `02_multiple_calls.py` | 1 | Nested RAG pipeline (retrieve → generate → evaluate) | Yes | 1 trace with 3 child stages, each with Completions |
| `03_concurrent_calls.py` | 50 | 25 sequential + 25 concurrent individual traces | Yes | 50 separate trace rows, each independently searchable |
| `04_failures.py` | 3 | 3 failure types (timeout, rate_limit, transient) | No | 3 traces with 🚨 ERROR status, real exceptions, retry children |
| `05_batch_dashboard.py` | 30 | 15 sequential + 15 concurrent individual traces | Yes | 30 traces with varied prompts, cost, latency for dashboards |
| `06_synthetic_metrics.py` | 0 traces | 1500 synthetic metric observations (3 scenarios) | No | Fills Grafana dashboards with Normal/LLM Degraded/System Failure data |
| `07_evaluation.py` | 5 | 5 individual eval traces with quality scores | Yes | 5 traces, each with Input/Output + 4 scores (success, relevance, completeness, conciseness) |

> Script 03 takes ~1 min (25 calls × 2s rate-limit delay). Run separately if needed.
> Script 06 generates NO traces — only Prometheus metrics for Grafana.

## 8. Import Grafana Dashboards

```powershell
cd d:\Observation_Layer
$env:PYTHONPATH = "d:\Observation_Layer"
.venv\Scripts\python.exe infrastructure\import_dashboards.py
```

This creates 3 dashboards:
1. **Normal** — healthy system (99% success, fast latency)
2. **LLM Degraded** — slow LLM responses (P95/P99 spikes, retry cost)
3. **System Failure** — rate limits + timeouts (errors, budget exhausted)

## 9. Check Dashboards

| What | URL | What you see |
|---|---|---|
| Langfuse Home dashboard | http://localhost:3000 → Home | Model costs, trace count, latency P50-P99, token usage, scores |
| Langfuse traces | http://localhost:3000 → Tracing | Individual traces with clean Input/Output, cost, tokens |
| Grafana dashboards (3) | http://localhost:3001 (admin/admin) | Normal, LLM Degraded, System Failure |
| Phoenix traces | http://localhost:6006 | Trace waterfall with input/output JSON |
| LangSmith traces | https://smith.langchain.com | Trace inspection + evaluation |
| Prometheus raw | http://localhost:9095 | Raw metric queries |

## 10. Stop Everything

```powershell
cd d:\Observation_Layer
docker compose down

cd D:\langfuse
docker compose down
```

> Add `-v` to wipe all data (traces, metrics, Grafana dashboards, volumes).