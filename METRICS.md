# KPI dictionary and honest interpretation
All records are fictional. Snapshot: 22 November 2026; latest daily data: 21 November.
Zone and Tier labels are demonstration planning groups, not official telecom LSAs.

| KPI | Definition / grain | Interpretation |
|---|---|---|
| MTD billed revenue | Sum of synthetic daily billed INR, Nov 1–21 | Actual-to-date in the simulation, not full-month forecast |
| Active base | Sum October 2026 closing subscribers | Synthetic population; the 30,000-row modeling sample is separate |
| October ARPU | October billed INR / mean(opening,closing base) | Recalculate from totals when filtering; do not average city ARPU |
| Monthly churn | October churned / October opening base × 100 | Not the model's predicted churn probability |
| Availability | 100 × (1 − unavailable site-minutes / eligible site-minutes), 7d | Site-time-weighted across RAT/cities |
| Call setup success | Successful setups / attempts × 100, 7d | Counter-weighted |
| Drop rate | Dropped calls / connected calls × 100, 7d | Counter-weighted |
| Handover success | Successful / attempted handovers × 100, 7d | Counter-weighted |
| Download throughput | Downloaded Mbit / active download seconds, 7d | Mbps, not an average of city rates |
| Latency | Sum latency-ms / probe count, 7d | Sample-weighted mean, not percentile latency |
| PRB utilization | Used resource units / available resource units × 100 | Capacity-weighted |
| Packet loss | Lost / sent packets × 100 | Packet-weighted |
| NPS | 100 × (promoters − detractors) / valid respondents | Suppressed below 30 respondents; negative NPS is possible |
| CSAT | Mean of synthetic 1–5 responses | Survey sample, not all subscribers |
| MTTR | Mean resolution hours for resolved registered tickets | Open tickets excluded; not a network incident reliability estimate |
| Internal target breaches | Open tickets older than 48 hours | Internal illustrative target, not a TRAI deadline |
| High review priority | Drop >2% OR availability <99% OR PRB >90% | Internal simulation thresholds, not legal compliance labels |
| Medium review priority | Otherwise drop >1%, availability <99.5%, PRB >80%, monthly churn >3%, or anomaly flag | Low otherwise; High/Medium/Low = red/green/blue |
| Review-linked billed revenue | MTD revenue in cities with High priority | Exposure proxy; never causal loss, expected loss or double-counted forecast |
| Anomaly share | Isolation Forest flags / scored network rows | Unlabelled screening; no proven incident precision |
| Forecast | Per-city monthly billing forecasts, additive by selected cities | Six-month holdout; next three months; not a guarantee |
| Churn model | Temporal holdout PR-AUC, ROC-AUC, Brier; zone subgroup metrics | Purged label maturity, val-only selection; synthetic generalization only |
| Drift | PSI with training-derived bins | Signal to investigate; fixed synthetic snapshot |
| RAG | Fixture hit@3, measured latency, abstention, source-ID validity, agent stages | Source-ID validity is not semantic correctness or an accuracy guarantee |
| Ops | Request counts, per-principal p50/p95 latency, review queue | Local process measures; production SLO availability, cloud costs and independent groundedness are N/A |

Additional production feeds: OSS/BSS/CDR mediation, alarms, cell/site topology, spectrum assignments,
finance reconciliation, CRM case ownership, recharge/collections, portability, enterprise SLA contracts,
device telemetry and consent-controlled customer events. These require governed connectors and official
definitions before using this prototype for operational reporting. No model output auto-denies service.

## Enriched scenario fields
- Asset status: 12 fictional samples/city. Online, Offline, Degraded and Telemetry missing are simulation states; they do not determine the city’s population risk metric. No heartbeat does not prove an outage.
- Asset criticality: Offline=High, Degraded/Telemetry missing=Medium, Online=Low, using internal sample rules.
- Hourly traffic: sum of 60 city scenarios on 21 Nov; PRB and latency use resource/probe denominators. Hourly scenarios are independent of daily OSS counters and cannot be reconciled as a daily partition.
- Service-plan mix: historical customer sample counts and mean bills/model scores; not the operator subscriber population or population ARPU.
- Complaint mix: counts by registered ticket category, with no population incidence claim.
- Offline file now contains 365 daily dates and 36 monthly dates. Full-year network charts retain counter-weighted rates.
