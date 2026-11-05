# Shortlist: oxide_dielectric_thin_film

Run 00000000-0000-4000-8000-000000000001, replay data, started 2026-11-02T12:00:00+00:00.
Note: SAMPLE BUNDLE: groups, provenance, hazards, gaps, and literature are real recorded data; score normalizations are illustrative placeholders, not Track A scoring. Scoring profile notes: dielectric_constant: target band unusable (status not entered); weight stays 0

Request: Rank the eleven baseline oxides as thin-film dielectric candidates.

## What this screen cannot tell you

- breakdown field
- leakage current density
- band offsets to the substrate
- interface trap and defect density
- crystallization temperature
- interfacial reaction with the substrate
- the film's actual phase and density


## Applies to every row

- Band offsets to the substrate are not checked by this screen.

| Rank | Material | Why | Key caveat | Evidence | k | Missing |
|---|---|---|---|---|---|---|
| 1= | Al2O3 | Al2O3 ranks 1= on stability (stability margin) and insulating gap; see caveats. | none specific to this row | no abstracts | 9.7 | none |
| 1= | HfO2 | HfO2 ranks 1= on stability (stability margin) and insulating gap; see caveats. | none specific to this row | thin_film_deposited | 18.7 | none |
| 1= | La2O3 | La2O3 ranks 1= on stability (stability margin) and insulating gap; see caveats. | none specific to this row | no abstracts | missing | none |
| 1= | Y2O3 | Y2O3 ranks 1= on stability (stability margin) and insulating gap; see caveats. | none specific to this row | no abstracts | missing | none |
| 1= | ZrO2 | ZrO2 ranks 1= on stability (stability margin) and insulating gap; see caveats. | none specific to this row | no abstracts | 21.3 | none |
| 6 | Ta2O5 | Ta2O5 ranks 6 on stability (stability margin) and insulating gap; see caveats. | none specific to this row | no abstracts | 33.8 | none |
| 7 | TiO2 | TiO2 ranks 7 on stability (stability margin) and insulating gap; see caveats. | none specific to this row | no abstracts | 63.2 | none |
| 8 | BaTiO3 | BaTiO3 ranks 8 on stability (stability margin) and insulating gap; see caveats. | none specific to this row | no abstracts | 13.0 | none |

Equal scores are tied; tied rows are listed alphabetically.

## Reference anchors (never ranked)

- SiO2 (reference): would place 1st of 9, above Al2O3

## Excluded

- BeO: hazard.exclude (IARC Group 1: beryllium and beryllium compounds)
- ThO2: hazard.radioactive_exclude (['Th'] has no stable isotope)

## Caveats

- band_offsets_not_checked: Band offsets to the substrate are not checked by this screen.
## Settings applied

- Defaults: verbosity=standard; view=pi_summary
- Clamps: none
- Verifier: failures removed (1 failure(s))
