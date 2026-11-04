# infra

Docker Compose (`compose.yaml` at the repository root) is the primary deployment, and
`apptainer/materials-triage.def` is the recipe for clusters without Docker at run time.
`terraform/` holds a reference AWS module that CI validates and nobody applies from here; see
`terraform/README.md` for what it creates, what it costs, and what it leaves out.
