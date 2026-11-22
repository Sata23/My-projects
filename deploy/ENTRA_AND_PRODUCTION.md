# Entra setup and production acceptance
1. Register a single-tenant Web application in your organization’s Entra tenant. If using a Gmail identity,
   first have the administrator provision/invite the identity and choose supported external identity
   federation. Email ownership by itself grants no application role. Use a top-level browser redirect.
2. Set the exact HTTPS redirect URI `https://YOUR-HOST/auth/callback`. Configure the HTTPS issuer as
   `https://login.microsoftonline.com/TENANT-ID/v2.0`. Set the app client ID and securely stored confidential
   client credential. Do not put secrets in notebooks, GitHub, HTML or chat.
3. Create a random session signing secret (32+ chars) and persistent Fernet key through a secret manager.
   Example local key generation: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   Retain the key securely; rotating it requires re-encrypting stored contacts. Demo runs use disposable keys.
4. Configure PUBLIC_BASE_URL and blank-by-default OIDC_LOGIN_HINT if desired. An optional login hint
   only prefills the sign-in form. Authlib validates the signed ID token, issuer, audience, nonce/state
   and PKCE flow. No unsigned email or browser role claim authorizes an API request.
5. Populate ACCESS_MAP_JSON with verified issuer|sub keys and approved tenant, role, zone, city and purpose
   attributes. Allowed role examples: telecom_analyst, noc_engineer, customer_support, compliance_reviewer.
   API scope is narrowed by filters; a client cannot widen it. Support contact access additionally requires
   purpose `case_resolution` and the subscriber’s authorized geography. PII reads are audited by record hash.
6. Deploy `deploy/compose.entra.yaml` behind a TLS reverse proxy. Set the production secret environment
   externally, preserve the encrypted database volume and expose only HTTPS. Start with one worker/replica.
   Docker build/launch and real SSO were not exercised in the local build environment.
7. Validate with real non-production test identities: consent, MFA/Conditional Access, issuer/audience
   rejection, expired/revoked sessions, scope denial, CSRF/origin attacks, guest lifecycle, key rotation,
   audit retention, concurrent review races and tenant isolation. Local tests cover negative token/state
   handling and mapping, not an actual Microsoft sign-in.

## Scale-up design (implementation work, not an active connector)
Separate identity/API, ingestion workers, retrieval, model serving, workflow and reporting by capacity
boundary. Queue ingestion and long forecasts; use idempotency keys, bounded retries/backoff, dead letters,
outbox and sagas for cross-service business actions. Keep RAG authorization before retrieval and before
final output. Cache by tenant, permissions, version and query—not query alone. Persist policy reviews,
models and sessions; never retrain a real production model on every service startup.

Replace SQLite with managed PostgreSQL/pgvector using a non-owner, non-bypassrls app role, transaction-local
trusted attributes and pooled-connection reset. The included SQL is a reference: application wiring,
migrations, query plans/indexing and integration tests remain to be implemented. Default model dimensions
differ: TF-IDF is corpus-specific; MiniLM is384. Do not mix models in one vector index.

Export OpenTelemetry spans/metrics with redaction; no raw prompts, contacts or tokens in logs. Capture
API rate/errors/p95, queue lag, data age, schema failures, policy expiry, retrieval recall, groundedness
from independent adjudication, abstention reasons, model drift/calibration, HITL turnaround and actual
metered costs. N/A in the current app is intentional where a production instrument does not exist.

## Sources reviewed for design
- https://docs.authlib.org/en/v1.5.2/client/starlette.html
- https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow
- https://learn.microsoft.com/en-us/entra/external-id/google-federation
- https://huggingface.co/docs/huggingface_hub/guides/download
- https://www.trai.gov.in/node/13235
- https://www.trai.gov.in/release-publication/standing-directions/quality-of-Service
- https://www.dot.gov.in/static/uploads/2026/02/b110cdc386d3a4e41c8483d7ffd7c410.pdf
These links inform the starter; legislation must be revalidated at ingestion/deployment time.
