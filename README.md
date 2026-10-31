# materials-triage

An assistant that triages candidate materials before experiments. It pulls from public
sources only (Materials Project, JARVIS-DFT, an experimental band gap dataset, OpenAlex,
PubChem, COD), scores candidates with code, and uses a language model only to interpret
the request and explain the result. Every number traces to a source record.

Status: Phase 0 (foundations). Not yet runnable as a product. See `docs/` for decisions
and wire findings.
