# Permissions

Roles come only from the bearer token (`AUTH_MODE=static` or `oidc`). Nothing in a request
body, a query string, another header, or chat text changes a role. Every refused request is
written to the audit log.

`AUTH_MODE=none` is for development and is refused when `SITE_MODE=true`. In that mode every
request carries `DEV_ROLE`, and the header `X-Dev-Role` (the role switcher in the app's
header) may pick one of the three roles for a request; static and OIDC modes never read it,
and `tests/api/test_auth.py` sends it in each mode.

The enforcing code is the FastAPI dependency named in the last column
(`src/materials_triage/api/auth.py`). `tests/api/test_permissions.py` checks every route in
this table against the app, so the table cannot drift from the code.

## API routes

| Route | Scientist | FDE | Admin | Dependency |
|---|---|---|---|---|
| GET /api/me | yes | yes | yes | current_principal |
| GET /api/health | yes | yes | yes | none (no identity needed) |
| GET /api/profiles | yes | yes | yes | any_role |
| POST /api/parse | yes | yes | yes | any_role |
| POST /api/criteria/resolve | yes | yes | yes | any_role |
| POST /api/runs | yes | yes | yes | any_role |
| GET /api/runs | yes | yes | yes | any_role |
| GET /api/runs/{run_id} | yes | yes | yes | any_role |
| GET /api/runs/{run_id}/status | yes | yes | yes | any_role |
| GET /api/runs/{run_id}/events | yes | yes | yes | any_role |
| POST /api/runs/{run_id}/cancel | yes | yes | yes | any_role |
| GET /api/runs/{run_id}/view | yes | yes | yes | any_role |
| GET /api/runs/{run_id}/export | yes | yes | yes | any_role |
| GET /api/runs/{run_id}/drill/{composition}/{criterion} | yes | yes | yes | any_role |
| GET /api/runs/{run_id}/relaxations | yes | yes | yes | any_role |
| POST /api/runs/{run_id}/relax | yes | yes | yes | any_role |
| GET /api/config/effective | yes | yes | yes | any_role |
| GET /api/config/layers | no | yes | yes | console_roles |
| GET /api/hazard-policy | no | yes | yes | console_roles |
| GET /api/weight-bounds | yes | yes | yes | any_role |
| POST /api/admin/profiles/validate | no | yes | yes | console_roles |
| POST /api/admin/profiles | no | yes | yes | console_roles |
| POST /api/admin/refresh | no | no | yes | admin_only |
| GET /api/audit | no | no | yes | admin_only |
| GET /api/help/keys | yes | yes | yes | any_role |
| GET /api/help/{guide} | yes | yes | yes | any_role |

Weight bounds are readable by every role: the workspace shows the sliders' limits to the
scientist, who can move weights only inside them.

## Screen actions

| Action | Scientist | FDE | Admin |
|---|---|---|---|
| Describe a request, confirm criteria, run, cancel | yes | yes | yes |
| Rank my list | yes | yes | yes |
| Read PI and audit views, exports, drill-down, run history | yes | yes | yes |
| Read the Help page and the in-app help | yes | yes | yes |
| Apply a code-computed relaxation as a new run | yes | yes | yes |
| Open the console | no (403 page) | yes | yes |
| Read effective configuration, hazard policy, weight bounds, source health | no | yes | yes |
| Validate and save a scoring profile (new version only) | no | yes | yes |
| Request a source refresh (audit note required) | no | no | yes |
| Read the audit log | no | no | yes |
| Change hazard policy, weight bounds, site defaults | no | no | no (config files, reviewed in git) |

## What no role can do from the product

- Change a role or a permission.
- Edit the hazard policy, the site profile, or an existing scoring profile in place.
- Make the model fetch, write, or run anything: the model has four tools (parse, classify,
  write rationale, propose relaxation) and none of them changes state.
- Reach a host outside the egress allowlist.
