# Extensions

What is not built, and where each piece would attach. None of these changes the thesis: a
new source is an adapter with recorded fixtures, a new criterion is a config entry plus a
pure function, a new screen reads the bundle.

| Extension | Where it attaches | What it needs |
|---|---|---|
| Cost or abundance criterion | `scoring/criteria.py::cost` (always missing today), `criteria.cost` in the profiles | a public source with a license, an adapter with recorded fixtures, an entered config entry |
| AFLOW or OQMD | `adapters/` (OQMD is written against OPTIMADE and disabled after HTTP 502 on every query) | the service answering; a recording; the egress allowlist |
| Full-text evidence | `adapters/openalex.py` scope | a licensed full-text source; quotes stay verbatim-checked |
| Sensitivity page | the audit rows already carry each candidate's rank range over the weight perturbations | a screen that plots them |
| Compare-runs page | `cli/rundiff.diff` attributes every rank change | a screen over two bundles |
| Tablet layout | the CSS is responsive; it is not tested at tablet width | a Playwright run at that viewport |
| Live classification at scale | `CLASSIFY_MODE=live`, the classifier cache, the per-step budgets | a budget per run and a cost report; the eval harness already caps calls |
| Retention job | `provenance.store.MaintenanceStore.delete_fetch_events_before` with the maint role | a scheduler and a site setting |
| Runs in Postgres | `triage.runs` exists; runs are JSON files by decision | an API that queries across runs |
| Terraform apply | `infra/terraform` validates in CI and is never applied | an AWS account, an ECR push, a secrets fill |
| Second identity provider | `AUTH_MODE=oidc` with the three `OIDC_*` settings | the issuer's audience and role claim |
| Highlighted parse spans | the parse tool returns fields, not spans | a tool schema change and a verifier rule for spans |
| Evidence subject check that reads context | `verify/subject.py::names_candidate`, applied in `agent/classifier.py::check_subject` | a rule for the two known false negatives below, with its own tests |

## Stated limit: the evidence subject check

The check passes a supporting sentence only when it names the candidate as a standalone formula
(or, when the formula is absent, a listed synonym). It has two known false negatives, where real
evidence about the candidate is rejected as "evidence names another material":

- A sentence that does not name the material at all, such as "The dielectric constant is 13
  and dissipation factor, tan δ, is 0.003 at room temperature" (Y2O3). The abstract is about
  the candidate, but the chosen sentence says "the film" or nothing. Seven of the 70 labels in
  the recorded runs fail this way.
- Substrate notation, such as "a thin MgO/Mo(001) film". The slash marks a film on a substrate,
  but the check reads it as a mixed system.

Both lower a row's evidence; neither raises one. A rejected label stays in the audit view with
its reason.
