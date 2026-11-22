# TelecomIQ — Enterprise Telecom CRM, RAG and Observability
POC to Production 2. A responsive glass dashboard for a telecom analyst, with a runnable Python API,
downloadable notebook and standalone HTML simulation. India: 60 cities, 6 planning zones, synthetic
population aggregates, 30,000 historical model sample customers, 365 days of network counters,
36 months of finance and 10,000 case records. This is a tested prototype and production deployment
starter, not an already deployed or certified enterprise system.

## Open the deliverables
- `notebooks/TelecomIQ_POC_to_Production_2.ipynb`: self-contained Colab/Jupyter setup, analytics,
  temporal ML, agent pipeline, live API, offline exporter and GitHub source exporter.
- `simulation/TelecomIQ_POC_to_Production_2.html`: open locally in a browser; no CDN or backend needed.
  Demo role selection is deliberately not SSO. Only synthetic aggregates and pseudonymous records are embedded.

## Run locally
Python 3.12 recommended.
```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
TELECOM_DEMO=true PUBLIC_BASE_URL=http://127.0.0.1:8000 uvicorn telecomiq.api:create_app --factory --port 8000
```
Open http://127.0.0.1:8000. Or `docker compose -f compose.demo.yaml up --build`.
Run `pip install -r requirements-dev.txt` then `python -m pytest -q tests`.

## Analyst experience
Executive KPIs, city/zone/tier filters; Network & coverage with zoom/pan/tooltips and RGB priority map;
masked Customers; Revenue & churn; Forecast & recommendations; synthetic Spectrum planning;
Policy hub; grounded Chat agent; independent HITL review queue; separate Observability; Architecture.
CSV exports obey current server scope. Print-to-PDF is available through the browser. This release
does not claim native Power BI embedding or native XLSX/PPT export; the CSV gold tables can feed Power BI.

## RAG and agents
Ingestion: catalogue → parse → redact → overlapping chunks → embedding → SQLite vector persistence.
Query: intent → trusted ABAC scope → authorized vector candidates → similarity → typed tool facts →
context → generation → exact-passage/source validation → answer or abstention → independent HITL draft.
These are observable logical specialist tools, not a separate LLM call for every deterministic task.

Default is offline-compatible TF-IDF cosine retrieval + extractive generation. It is explicitly not
neural embeddings or a live generative model. Install `requirements-llm.txt`, choose
`EMBEDDING_BACKEND=minilm` and `LLM_BACKEND=hf` for real pinned Hugging Face MiniLM and Qwen3-0.6B.
Model downloads and target-device evaluation are required; this optional mode was not executed in the
artifact build environment. The LLM only selects an exact authorized passage; typed KPI calculations
and policy gates remain deterministic. Never promise near-perfect recommendations.

Knowledge includes 4 dated official-reference digests and 40 synthetic internal SOPs plus ACL fixtures.
These are not consolidated legal documents. Exact TRAI compliance benchmarks abstain until full current
approved instruments are ingested and validated. Role-restricted uploads are staged, redacted and reviewed;
optional Hugging Face dataset ingestion requires a pinned revision and licence note. Never indiscriminately
import all customer data. Source volume is bounded and quality/authority/ACL/freshness are required.

## Microsoft Entra ID + containers
Read `deploy/ENTRA_AND_PRODUCTION.md`. The supplied email is only a login hint; it is deliberately absent
from public source and is never an authorization key. No tenant/client IDs or public app URL were provided.
Production mode therefore fails closed until configured. No live Entra roundtrip or cloud deployment has
been performed. Containers default to production mode; demo must be explicitly enabled.

## CI/CD
GitHub Actions validates tests, notebook schema and container build on push/PR. The manually dispatched
release workflow publishes a commit-tagged image to GHCR using a `production` environment. Configure
required reviewers/branch protections in GitHub before use. Hosting-specific rollout remains to be wired
after selecting a platform; no external deployment is triggered by this starter.

## Production boundary
Current runtime uses synthetic data, single-process SQLite, in-memory request telemetry and a local
encrypted PII store. It must not be horizontally scaled as-is. `deploy/postgres_reference.sql` is a
reference RLS schema, not a wired adapter. Adopt managed PostgreSQL/pgvector + transactional outbox,
shared sessions/cache, durable telemetry, KMS, workload identity, rate limiting/WAF, secrets rotation,
signed provenance, access review, retention policies, human adjudication, load/chaos/failover tests,
backup restore evidence and representative multilingual RAG evaluations before go-live.
Read `METRICS.md` for definitions, aggregation rules and limitations.
