"""Deterministic scoring (Track A). The LLM never touches a number: every score, rank,
exclusion, flag, and caveat trigger is computed here from owner-sourced config and the
normalized records. Public API in `scorer`; vocabularies in `records.bundle`."""
