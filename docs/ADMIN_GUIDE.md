# Admin guide

For the site administrator and the field engineer. The scientist's view is
`docs/SCIENTIST_GUIDE.md`; the configuration layers are in `docs/CONFIGURING.md`.

## Install

**Docker Compose** (primary):

```
cp .env.example .env            # fill in what you use; nothing is required for the offline demo
docker compose up -d            # postgres and api on :8000
docker compose exec api alembic upgrade head
docker compose --profile auth up -d keycloak      # optional: dev identity provider on :8080
docker compose --profile split-web up -d          # optional: nginx front on :8081
```

The `api` image serves the web app too; `split-web` is for sites that deploy the static app
separately. The image contains the recorded source data, so it answers from the cassettes
with no keys unless `FETCH_MODE` is set and Postgres answers.

**From source:** `uv sync`, `cd web && npm ci && npm run build`, `uv run materials-triage
serve`. Postgres 16 on host port 5433 comes from Compose; create the roles with
`src/materials_triage/provenance/roles.sql` and migrate with `uv run alembic upgrade head`.

**Apptainer:** `apptainer/materials-triage.def` builds from the `api` image
(`docker build --target api -t materials-triage:api .` first). It was written against the
Apptainer definition reference and not built here (no Apptainer on the development machine);
treat the first build on your cluster as the test.

## Settings (`.env`)

| Variable | Meaning |
|---|---|
| `DATABASE_URL`, `DATABASE_URL_MIGRATE`, `DATABASE_URL_MAINT` | the three Postgres roles: app (select and insert), migrate (DDL), maint (select and delete) |
| `MP_API_KEY`, `OPENALEX_API_KEY`, `OPENALEX_MAILTO` | source credentials, injected at send time, never stored in records |
| `FETCH_MODE` | unset (default): recorded cassettes only; `live` (store first, network on a miss), `replay` (store only), `refresh` (always network) |
| `LLM_PROVIDER`, `LLM_MODEL`, `ANTHROPIC_API_KEY`, `LLM_BASE_URL`, `LLM_API_KEY`, `AWS_REGION` | the model: `anthropic`, `bedrock`, `openai_compatible`, or `none` |
| `CLASSIFY_MODE` | `live` (default; within the classify budget, estimate returned by `/criteria/resolve`) or `cache_only` (never calls the model for an abstract) |
| `AUTH_MODE`, `DEV_ROLE`, `STATIC_TOKENS`, `SITE_MODE`, `ALLOW_STATIC_TOKENS`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_ROLES_CLAIM` | sign-in, below |
| `DATA_CACHE_DIR` | run bundles, the classifier cache, the audit log, screenshots |

The default model is `claude-sonnet-5-5`. A missing key, a rejected key, or an exhausted
credit balance turns the model off for the process: `/health` reports `llm_status`
(`missing_key`, `invalid_key`, `no_credit`), the app shows a banner, and runs complete with
template rationale and unclassified evidence. Restart after fixing the key. The demo
configuration (one parse call per request): `LLM_PROVIDER=anthropic`,
`LLM_MODEL=claude-sonnet-5-5`, `CLASSIFY_MODE=cache_only`.

## Sign-in and roles

Roles are `scientist`, `fde`, `admin`, and they come only from the bearer token. The
permission matrix is `docs/PERMISSIONS.md`; a test keeps it equal to the code.

- `AUTH_MODE=none`: every request carries `DEV_ROLE`. Local use only.
- `AUTH_MODE=static`: `STATIC_TOKENS=token:role,token:role`. A site deployment
  (`SITE_MODE=true`) refuses to start with static tokens unless `ALLOW_STATIC_TOKENS=true`.
- `AUTH_MODE=oidc`: RS256 JWTs from `OIDC_ISSUER` for `OIDC_AUDIENCE`, validated against the
  issuer's JWKS, roles read from `OIDC_ROLES_CLAIM` (default `realm_access.roles`, Keycloak's
  realm roles). Token validation allows 60 seconds of clock leeway between the issuer and
  the API host; the dev Keycloak container's clock ran ahead of the host by a few seconds.

**Keycloak dev realm.** `docker compose --profile auth up -d keycloak` imports
`deploy/keycloak/realm-materials-triage.json`: realm `materials-triage`, the three roles,
users `scientist`, `fde`, `admin` with their names as passwords (development only), and a
public PKCE client `materials-triage-web` whose access tokens carry the audience
`materials-triage-api`. The API then runs with:

```
AUTH_MODE=oidc
OIDC_ISSUER=http://localhost:8080/realms/materials-triage
OIDC_AUDIENCE=materials-triage-api
```

and the web app is built with `VITE_AUTH_MODE=oidc`. To swap in your own provider, set the
three `OIDC_*` variables to its issuer, the audience it puts in access tokens, and the claim
that carries roles; map your groups to the three role names there. Change the dev passwords
or delete the dev users before any shared deployment.

Every refused request (401, 403) and every admin action is appended to
`DATA_CACHE_DIR/audit.log` as JSON lines; admins read it at `GET /audit`.

## The console

Field engineers and admins open Console in the top bar.

- **Effective configuration:** each setting by the layer that set it, for a chosen profile.
- **Hazard policy** and **weight bounds:** read-only tables with the config entry behind
  each row. These are edited in the YAML files and reviewed in git, not in the console.
- **Profiles (YAML):** paste or upload a scoring profile. It is validated with the scorer's
  own loader and the site bounds; errors name the entry. A valid profile is saved as a new
  file `config/scoring_profiles/<profile>_v<version>.yaml`; existing files are never
  overwritten, so an old run's profile stays what it was.
- **Source health:** per source, whether records are stored or recorded, the last fetch, and
  the allowed host. Admins may request a refresh with a required audit note: the next run
  that uses the Postgres store refetches that source; earlier runs keep their snapshot and
  hashes.

## Egress

Two layers:

1. **Application check** (`adapters/egress.py`): every outbound request is checked against
   `CoreConfig.allowed_hosts` (`api.materialsproject.org`, `api.openalex.org`,
   `pubchem.ncbi.nlm.nih.gov`, `www.crystallography.net`) plus the configured model endpoint
   (`api.anthropic.com`, the Bedrock Mantle host for the region, or `LLM_BASE_URL`'s host)
   before it is sent. The model's own HTTP client carries the same check.
2. **Network.** Compose puts Postgres and Keycloak on an internal network with no outside
   route and only the API on the egress network. That limits which service may reach the
   internet; it does not filter by hostname. A network-level domain allowlist needs an egress
   proxy or a firewall with domain rules (AWS Network Firewall, for example), configured with
   the host list above. The Terraform reference module routes egress through a NAT gateway and
   filters by IP in security groups; it does not enforce the hostname list.

## Data retention and backups

- The Postgres store holds every raw response with its hash, so a bundle's numbers can be
  traced after the source changes. Back it up like any Postgres database. The maintenance
  role (`triage_maint`) may delete fetch events older than a retention window; no job runs
  this automatically yet (see `docs/EXTENSIONS.md`).
- Run bundles are JSON files under `DATA_CACHE_DIR/runs`; keep that directory with the
  store. `materials-triage replay` needs only the bundle.
- The classifier cache under `DATA_CACHE_DIR/classifier` holds evidence labels keyed by
  abstract hash, prompt hash, and model version; losing it means paying the model again.

## Licenses

Materials Project documents under the GNoME `BY-NC` license are dropped at the adapter and
never scored; deployment accounts never accept that license. JARVIS and the experimental gap
compendium are pinned snapshots with their licenses in `docs/DATA_SOURCES.md`. Rows whose
hazard record cites ECHA show the required attribution line.

## Health

`GET /health` reports the fetch source (store or cassettes), fetch mode, model provider and
model, classify mode, auth mode, and per source the record count, last fetch, and allowed
host. The Docker image's health check calls it.
