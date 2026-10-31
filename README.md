# materials-triage

An assistant that triages candidate materials before experiments. It pulls from public
sources only (Materials Project, JARVIS-DFT, an experimental band gap dataset, OpenAlex,
PubChem, COD), scores candidates with code, and uses a language model only to interpret
the request and explain the result. Every number traces to a source record.

Status: Phase 1 (data layer): adapters for every source, a normalized record model, and an
append-only Postgres provenance store with cache and replay modes. Not yet runnable as a
product. See `docs/` for decisions and wire findings.
