# web

Vite + React + TypeScript. Three screens: workspace (describe or rank, confirm criteria,
progress, PI and audit results), provenance drill-down, and the admin/FDE console. Types in
`src/api/types.ts` are generated from the FastAPI OpenAPI export (`npm run types` after
`uv run python scripts/export_openapi.py`); CI checks they match.

- `npm ci && npm run build` writes `dist/`, which `materials-triage serve` mounts at `/`.
- `npm run dev` serves on :5173 with `/api` proxied to the API on :8000
  (`uv run materials-triage serve --no-web`).
- Build with `VITE_AUTH_MODE=oidc` (and `VITE_OIDC_ISSUER`, `VITE_OIDC_CLIENT_ID`) for the
  Keycloak sign-in; otherwise the app asks for a bearer token when the API requires one.

The browser never computes or formats a number: every value comes from the API's view model
already formatted, and the PI view carries no record ids.
