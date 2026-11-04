# Discovery questions

What the tool leaves to the scientist, because it is a preference, a fact no public source
records, or a decision the site owns. Each item names where the tool says so.

## Preferences the request should state

- **How simple is simple?** The element-count limit (default 3) and the ternary penalty are
  a preference, not chemistry (`config/scoring_profiles/*.yaml`, `criteria.simplicity`).
  Say "binary only" or "ternaries are fine".
- **How wide is wide?** The dielectric profile prefers gaps from 5 eV up as a soft ramp; the
  photocatalyst profile uses a 2.0 to 3.3 eV window. State a number if you have one; the
  confirm form shows what was assumed.
- **Which incumbent?** SiO2 is the reference row in the dielectric profile. Name another
  ("compare to HfO2") and it is added for the run.
- **Which deposition methods?** The site lists its methods; abstract labels that name a
  method are matched when the deposition criterion carries weight.
- **How much metastability?** The hull cutoff (94 meV/atom, Sun 2016's binary-oxide
  percentile) is a choice with precedent, adjustable per run inside the site bounds.

## Facts no configured source records

Shown as missing on every row ("What this screen cannot tell you"): breakdown field, leakage
current, band offsets to the substrate, interface trap and defect density, crystallization
temperature, interfacial reaction with the substrate, the film's actual phase and density,
and moisture sensitivity (dielectric profile). Any property a request names that no source
provides (conductivity, thermal conductivity) is reported as unavailable and not scored.

## Decisions the site owns

- The hazard policy: what is excluded, flagged, or caveated, with a cited source per entry.
  "Non-toxic" in a request maps to that policy; nothing in chat changes it.
- Weight and cutoff bounds, the glossary, the deposition method list.
- Which scoring profiles exist and what their thresholds are (field engineer).

## Known limits to ask about

- The 94 meV/atom cutoff was calibrated on binary oxides; under a non-oxide profile every
  row carries a caveat saying so.
- Experimental band gaps attach to the composition, not to the scored polymorph, and the
  compendium does not cite a primary source for each value.
- Evidence tiers come from abstracts, not full text; a paper that deposited a film without
  saying so in the abstract is not credited.
- The molecular-crystal rule uses the scored polymorph's structure; a layered solid (P2O5)
  passes it, and whether that is what you want is your call.
