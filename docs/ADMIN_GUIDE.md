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

Two Compose files. `compose.yaml` is for development: one network, with Postgres
(`127.0.0.1:5433`) and Keycloak (`127.0.0.1:8080`) published on the loopback address only, so
the host's tools, migrations, and the browser's sign-in page reach them. `compose.site.yaml`
is the site override:

```
docker compose -f compose.yaml -f compose.site.yaml up -d
```

It moves Postgres and Keycloak to an internal network (`internal: true`) and removes their
host ports; the api joins that network and the `egress` network, and the split web front
joins it and a `front` network for its port. Docker publishes no host port for a service whose
only network is internal, which is why the split lives in the site file and not the dev one.

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
| `LLM_PROVIDER`, `LLM_MODEL`, `ANTHROPIC_API_KEY`, `LLM_BASE_URL`, `LLM_API_KEY`, `AWS_REGION` | the model: `anthropic`, `bedrock`, `openai_compatible`, `openai`, `gemini`, or `none` |
| `OPENAI_API_KEY`, `GEMINI_API_KEY` | the keys of the `openai` and `gemini` presets (experimental, below) |
| `CLASSIFY_MODE` | `live` (default; within the classify budget, estimate returned by `/api/criteria/resolve`) or `cache_only` (never calls the model for an abstract) |
| `AUTH_MODE`, `DEV_ROLE`, `STATIC_TOKENS`, `SITE_MODE`, `ALLOW_STATIC_TOKENS`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_ROLES_CLAIM` | sign-in, below |
| `DATA_CACHE_DIR` | run bundles, the classifier cache, the audit log, screenshots |

The default model is `claude-haiku-5-5`. A missing key, a rejected key, or an exhausted
credit balance turns the model off for the process: `/api/health` reports `llm_status`
(`missing_key`, `invalid_key`, `no_credit`), the app shows a banner, and runs complete with
template rationale and unclassified evidence. Restart after fixing the key. The demo
configuration: `LLM_PROVIDER=anthropic`, `LLM_MODEL=claude-haiku-5-5`, `CLASSIFY_MODE=live`
(one parse call, up to five classify calls per shown row, one rationale call; the confirm step
shows the estimate). With `cache_only`, if some shown rows have cached labels and others do not,
evidence is dropped for every row in that run and the page says so.

## Sign-in and roles

Roles are `scientist`, `fde`, `admin`, and they come only from the bearer token. The
permission matrix is `docs/PERMISSIONS.md`; a test keeps it equal to the code.

- `AUTH_MODE=none`: every request carries `DEV_ROLE`, and the header `X-Dev-Role` (the
  role switcher in the app's top bar) may pick one of the three roles for a request. Local
  use only: the API refuses to start in this mode when `SITE_MODE=true`, and the other two
  modes never read the header.
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
`DATA_CACHE_DIR/audit.log` as JSON lines; admins read it at `GET /api/audit`.

## The console

Field engineers and admins open Console in the top bar.

- **Effective configuration:** each setting by the layer that set it, for a chosen profile.
- **Hazard policy** and **weight bounds:** read-only tables with the config entry behind
  each row. These are edited in the YAML files and reviewed in git, not in the console.
- **Profiles (YAML):** paste or upload a scoring profile. It is validated with the scorer's
  own loader and the site bounds; errors name the entry. A valid profile is saved as a new
  file `config/scoring_profiles/<profile>_v<version>.yaml`; existing files are never
  overwritten, so an old run's profile stays what it was.
- **Source health:** a read-only Model panel (provider, model, classify mode, status; the
  provider is a site decision made in `.env`, never in the console), then per source whether
  records are stored or recorded, the last fetch, and the allowed host. Admins may request a refresh with a required audit note: the next run
  that uses the Postgres store refetches that source; earlier runs keep their snapshot and
  hashes.

## Model providers

`anthropic` (the default, evaluated in `docs/EVAL.md`), `bedrock`, and `openai_compatible`
(any chat-completions server at `LLM_BASE_URL`) are as before. Two named presets are new and
**experimental: not evaluated**. `LLM_PROVIDER=openai` uses `OPENAI_API_KEY` and
`https://api.openai.com/v1`; `LLM_PROVIDER=gemini` uses `GEMINI_API_KEY` and Gemini's
OpenAI-compatible endpoint `https://generativelanguage.googleapis.com/v1beta/openai`.
Both need an explicit `LLM_MODEL` (the Claude default is refused), `LLM_BASE_URL` overrides
the preset URL (a proxy, for example), and the preset's host joins the egress allowlist
automatically. The base URLs come from the providers' public documentation and were not
exercised on the wire by this repository. A 401 or 403 from such an endpoint sets
`invalid_key`, a 402 or a quota 429 sets `no_credit`, and the run falls back to no model the
same way as for Anthropic. The eval suite, the classifier prompts, and the verifier were
tuned against the Anthropic model only.

## Input limits

Core configuration (`CoreConfig`, code-owned): a request of at most 2,000 characters and a
candidate list of at most 50 entries. The API answers over either with a 422 and a sentence;
the web app shows a counter and the limit before sending. Candidate text is split by the API
on commas, semicolons, and new lines (`src/materials_triage/config/limits.py`); the browser never parses a list.

## Help routes

`GET /api/help/scientist` and `GET /api/help/admin` serve `docs/SCIENTIST_GUIDE.md` and
`docs/ADMIN_GUIDE.md` as Markdown from a fixed two-entry allowlist (no path reaches the
filesystem); the Docker image copies those two files. `GET /api/help/keys` lists the closed
vocabularies that `web/src/help.ts` must cover; `tests/test_help_text.py` checks it.

## Egress

Two layers:

1. **Application check** (`adapters/egress.py`): every outbound request is checked against
   `CoreConfig.allowed_hosts` (`api.materialsproject.org`, `api.openalex.org`,
   `pubchem.ncbi.nlm.nih.gov`, `www.crystallography.net`) plus the configured model endpoint
   (`api.anthropic.com`, the Bedrock Mantle host for the region, or `LLM_BASE_URL`'s host)
   before it is sent. The model's own HTTP client carries the same check.
2. **Network.** With `compose.site.yaml`, Postgres and Keycloak sit on an internal network
   with no outside route and only the API is on the egress network. That limits which service may reach the
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

`GET /api/health` reports the fetch source (store or cassettes), fetch mode, model provider and
model, classify mode, auth mode, and per source the record count, last fetch, and allowed
host. The Docker image's health check calls it.
