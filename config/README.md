# config

Owner-sourced values and policies. Nothing in this directory is asserted by the code's author;
every entry names who entered it, when, and from which public source.

Files:
- `reference_values.yaml`: experimental values entered with citation and material form.
- `hazard_policy.yaml`: element-level hazard tiers (admin-owned).
- `scoring_profiles/*.yaml`: weights, thresholds, band gap policy (FDE-owned, versioned).
- `site_profile.default.yaml`: deposition methods, always-missing list, glossary (admin-owned).

Status vocabulary (every entry has one):
- `entered`: value with a located open source. The only status the loader uses.
- `pending_verification`: owner-supplied value whose primary source is not yet located or not
  yet checked against the primary text. Shown as missing with this status.
- `pending_signoff`: the owner asked to sign off before use. Shown as missing with this status.
- `open`: no value yet.

Material form vocabulary for reference values: `crystalline_bulk`, `amorphous_film`,
`thin_film` (crystallinity not stated by the source).

Schema version 0 is plain YAML validated by `tests/test_config_entries.py`. The Phase 2
Pydantic schema is built to fit these files.
