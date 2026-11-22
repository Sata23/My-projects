# Validation record — 22 November 2026

| Check | Result |
|---|---|
| Full notebook default path | All 13 code cells executed in a fresh IPython process, including live API startup and exports |
| Synthetic data scale | 60 cities; 30,000 historical sample subscribers; 43,800 city/date/RAT network rows; 36 finance months; 10,000 tickets; 720 assets; 1,440 hourly city observations |
| Backend security and KPI suite | 10 tests passed: weighted reconciliation, temporal label purge, CSRF/session, scoped ABAC/role/PII, RAG/abstention, HITL, ingestion review, fail-closed config and mapping example |
| Live browser | All 12 tabs, city filtering, citations and regulatory abstention, map/zoom/tooltip, scoped CSV, role reset, mobile; no JavaScript errors |
| Standalone HTML browser | All 12 tabs, 60-city map with all marker bounds inside viewport, normal-page-scroll stability, weighted counter reconciliation, cohesive chat/abstention, independent simulated human review, CSV, role reset, mobile; zero external requests and no JavaScript errors |
| Notebook/compose/workflow structure | nbformat and YAML parsing passed |
| Actual neural models | Optional download/inference path not executed; tested path is TF-IDF + extractive |
| Real Microsoft Entra sign-in | Not exercised; tenant/client/host/credentials are outstanding |
| Local container build | Not executed; Docker is not installed in the artifact build environment. GitHub CI performs this check after push. |
| Cloud rollout | Not performed; deployment platform and production services remain to be configured |

The notebook transport in the build workspace did not support Jupyter ZMQ sockets, so cells were
executed through IPython in one fresh Python process and their outputs were captured into valid
nbformat. Colab-specific proxy rendering and real SSO require target-environment verification.
Known dependency warnings concerned pytest plugin naming and automatic physical-core detection;
they did not fail tests. Synthetic results and fixed RAG fixtures are not production performance evidence.

Enrichment revision: offline daily history expanded to 365 dates; 36 finance months; sample plan/ticket/asset and weighted RAT breakdowns. Both live and offline browser suites passed with no JavaScript errors; offline made zero external requests. Notebook code cells and backend suite passed after enrichment.
