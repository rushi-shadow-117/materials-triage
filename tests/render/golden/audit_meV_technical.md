# Audit view: oxide_dielectric_thin_film

## Run

- Run id: 00000000-0000-4000-8000-000000000001
- Started: 2026-11-02T12:00:00+00:00, finished 2026-11-02T12:00:00+00:00
- Fetch mode: replay; partial: no
- Config sha: 84a5f8eb7b120e4897e4e2d6289f760ff3368d946717703ec426b856b3db67a9
- Profile: oxide_dielectric_thin_film version 0; hazard policy version 0
- Prompt hash: none (no LLM)
- Model: none; provider: none
- Source versions: materials_project=2026.09.28, jarvis_dft_3d=d4c64660e9e1, expt_gap=2d0980e3533c
- Budgets: none recorded
- Note: SAMPLE BUNDLE: groups, provenance, hazards, gaps, and literature are real recorded data; score normalizations are illustrative placeholders, not Track A scoring. Scoring profile notes: dielectric_constant: target band unusable (status not entered); weight stays 0

## Criteria

- Request: Rank the eleven baseline oxides as thin-film dielectric candidates.
- Parsed by: criteria_file; confirmed: 2026-11-02T12:00:00+00:00
- Mode: candidate_list; candidates: HfO2, ZrO2, Al2O3, SiO2, TiO2, ThO2, La2O3, BaTiO3, BeO, Y2O3, Ta2O5
- Defaults applied: verbosity=standard; view=pi_summary
- Clamps: none
- Not found in any source: none
- Not available from configured sources: none
- Units shown: meV

## Ranked candidates

### Al2O3: 1, total 1.000
- Rationale: Al2O3 ranks 1 on stability (energy above hull) and band gap; see caveats.
- Flags: none
- Sensitivity: rank 1 to 2 over 12 perturbations (stable)
- Band gap source: tbmbj

| Criterion | Raw | Source | Normalized | Weight | Contribution | Record | Fetched |
|---|---|---|---|---|---|---|---|
| stability (energy above hull) | 0 meV/atom | GGA_GGA+U_R2SCAN | 1.000 | 1.000 | 1.000 | none |  |
| band gap | 7571 meV | tbmbj | 1.000 | 1.000 | 1.000 | none |  |
| hazard | missing | config/hazard_policy.yaml | 1.000 | 1.000 | 1.000 | none |  |
| simplicity | 2 elements | composition | 1.000 | 1.000 | 1.000 | none |  |
| evidence | 5 abstracts | openalex | 1.000 | 1.000 | 1.000 | none |  |
| dielectric constant | 9.7 | mp_dfpt | missing | 0.000 | 0.000 | none |  |
- hazard notes: GHS codes in 3142 notifications: ['H335', 'H372']

Polymorphs: 89 with MP ids (7 observed, 85 theoretical, 0 unknown).
- Ground state: mp-1143 (R-3c), hull 0 meV/atom, observed
- Scored polymorph is the ground state: yes; hull status conflict among functionals: no
- mp-1143 (R-3c): hull 0 meV/atom, observed; materials_project mp-1143 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.219939+00:00
- mp-7048 (C2/m): hull 17 meV/atom, observed; materials_project mp-7048 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.219939+00:00
- mp-2254 (Pna2_1): hull 21 meV/atom, observed; materials_project mp-2254 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.219939+00:00
- mp-776475 (Ia-3): hull 35 meV/atom, not observed; materials_project mp-776475 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.219939+00:00
- mp-759943 (P2/c): hull 35 meV/atom, not observed; materials_project mp-759943 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.219939+00:00

Experimental gaps: none in the public gap tables

Hazard: GHS codes H335, H372 in 225 of 3142 notifications (ECHA attribution applies)
Literature: 10698 matched, 7142 with abstracts, 5 read (title_and_abstract; query 'Al2O3 thin film')
Caveats:
- band_offsets_not_checked: Band offsets to the substrate are not checked by this screen. (source: scoring_profile#criteria.band_gap.standing_caveat)

### HfO2: 2, total 1.000
- Rationale: HfO2 ranks 2 on stability (energy above hull) and band gap; see caveats.
- Flags: none
- Sensitivity: rank 1 to 3 over 12 perturbations (stable)
- Band gap source: experimental_median

| Criterion | Raw | Source | Normalized | Weight | Contribution | Record | Fetched |
|---|---|---|---|---|---|---|---|
| stability (energy above hull) | 0 meV/atom | GGA_GGA+U_R2SCAN | 1.000 | 1.000 | 1.000 | none |  |
| band gap | 5550 meV | experimental_median | 1.000 | 1.000 | 1.000 | none |  |
| hazard | missing | config/hazard_policy.yaml | 1.000 | 1.000 | 1.000 | none |  |
| simplicity | 2 elements | composition | 1.000 | 1.000 | 1.000 | none |  |
| evidence | 5 abstracts | openalex | 1.000 | 1.000 | 1.000 | none |  |
| dielectric constant | 18.7 | mp_dfpt | missing | 0.000 | 0.000 | none |  |
- hazard notes: GHS codes in 344 notifications: []

Polymorphs: 15 with MP ids (5 observed, 10 theoretical, 0 unknown).
- Ground state: mp-352 (P2_1/c), hull 0 meV/atom, observed
- Scored polymorph is the ground state: yes; hull status conflict among functionals: no
- mp-352 (P2_1/c): hull 0 meV/atom, observed; materials_project mp-352 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.185807+00:00
- mp-775757 (Pbca): hull 10 meV/atom, not observed; materials_project mp-775757 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.185807+00:00
- mp-1858 (Pbca): hull 16 meV/atom, observed; materials_project mp-1858 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.185807+00:00
- mp-685097 (Pca2_1): hull 22 meV/atom, not observed; materials_project mp-685097 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.185807+00:00
- mp-776532 (P4_2/mnm): hull 37 meV/atom, not observed; materials_project mp-776532 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.185807+00:00

Experimental gaps: 5550 meV to 5550 meV across 1 value(s), median 5550 meV
- expt_gap: 5550 meV; expt_gap expt_gap:3:HfO2 fetched 2026-11-02T12:00:00+00:00

Hazard: no GHS hazard codes in 344 notifications (ECHA attribution applies)
Literature: 3496 matched, 2469 with abstracts, 5 read (title_and_abstract; query 'HfO2 thin film')
- https://openalex.org/W2024600253 (2015): thin_film_deposited; verified quote: "Here, we present a structural study on the origin of ferroelectricity in Gd doped HfO2 thin films."
- https://openalex.org/W2114118400 (2007): dielectric_characterized; not verified (quote not found verbatim in stored abstract); claimed: "This sentence does not appear in the abstract and was planted to show a failed quote check."
Caveats:
- band_offsets_not_checked: Band offsets to the substrate are not checked by this screen. (source: scoring_profile#criteria.band_gap.standing_caveat)

### La2O3: 3, total 1.000
- Rationale: La2O3 ranks 3 on stability (energy above hull) and band gap; see caveats.
- Flags: hull_status_conflict
- Sensitivity: rank 2 to 4 over 12 perturbations (stable)
- Band gap source: experimental_median

| Criterion | Raw | Source | Normalized | Weight | Contribution | Record | Fetched |
|---|---|---|---|---|---|---|---|
| stability (energy above hull) | 0 meV/atom | GGA_GGA+U_R2SCAN | 1.000 | 1.000 | 1.000 | none |  |
| band gap | 5400 meV | experimental_median | 1.000 | 1.000 | 1.000 | none |  |
| hazard | missing | config/hazard_policy.yaml | 1.000 | 1.000 | 1.000 | none |  |
| simplicity | 2 elements | composition | 1.000 | 1.000 | 1.000 | none |  |
| evidence | 5 abstracts | openalex | 1.000 | 1.000 | 1.000 | none |  |
| dielectric constant | missing (not_computed) | mp_dfpt | missing | 0.000 | 0.000 | none |  |
- hazard notes: GHS codes in 618 notifications: ['H315', 'H319', 'H335']

Polymorphs: 6 with MP ids (3 observed, 4 theoretical, 0 unknown).
- Ground state: mp-1968 (P-3m1), hull 0 meV/atom, observed
- Scored polymorph is the ground state: yes; hull status conflict among functionals: yes
- mp-1968 (P-3m1): hull 0 meV/atom, observed; materials_project mp-1968 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.392371+00:00
- mp-2292 (Ia-3): hull 2 meV/atom, observed; materials_project mp-2292 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.392371+00:00
- mp-557691 (C2/m): hull 31 meV/atom, observed; materials_project mp-557691 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.392371+00:00
- mp-1180635 (P6/mmm): hull 236 meV/atom, not observed, excluded by stability.cutoff; materials_project mp-1180635 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.392371+00:00
- mp-553347 (P-62m): hull 242 meV/atom, not observed, excluded by stability.cutoff; materials_project mp-553347 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.392371+00:00

Experimental gaps: 5400 meV to 5400 meV across 1 value(s), median 5400 meV
- expt_gap: 5400 meV; expt_gap expt_gap:12:La2O3 fetched 2026-11-02T12:00:00+00:00

Hazard: GHS codes H315, H319, H335 in 248 of 618 notifications (ECHA attribution applies)
Literature: 383 matched, 218 with abstracts, 5 read (title_and_abstract; query 'La2O3 thin film')
Caveats:
- band_offsets_not_checked: Band offsets to the substrate are not checked by this screen. (source: scoring_profile#criteria.band_gap.standing_caveat)

### Y2O3: 4, total 1.000
- Rationale: Y2O3 ranks 4 on stability (energy above hull) and band gap; see caveats.
- Flags: none
- Sensitivity: rank 3 to 5 over 12 perturbations (stable)
- Band gap source: experimental_median

| Criterion | Raw | Source | Normalized | Weight | Contribution | Record | Fetched |
|---|---|---|---|---|---|---|---|
| stability (energy above hull) | 0 meV/atom | GGA_GGA+U_R2SCAN | 1.000 | 1.000 | 1.000 | none |  |
| band gap | 5600 meV | experimental_median | 1.000 | 1.000 | 1.000 | none |  |
| hazard | missing | config/hazard_policy.yaml | 1.000 | 1.000 | 1.000 | none |  |
| simplicity | 2 elements | composition | 1.000 | 1.000 | 1.000 | none |  |
| evidence | 5 abstracts | openalex | 1.000 | 1.000 | 1.000 | none |  |
| dielectric constant | missing (not_computed) | mp_dfpt | missing | 0.000 | 0.000 | none |  |
- hazard notes: GHS codes in 548 notifications: ['H315', 'H319', 'H320', 'H335', 'H413']

Polymorphs: 14 with MP ids (4 observed, 12 theoretical, 0 unknown).
- Ground state: mp-2652 (Ia-3), hull 0 meV/atom, observed
- Scored polymorph is the ground state: yes; hull status conflict among functionals: no
- mp-2652 (Ia-3): hull 0 meV/atom, observed; materials_project mp-2652 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.437577+00:00
- mp-558573 (C2/m): hull 34 meV/atom, observed; materials_project mp-558573 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.437577+00:00
- mp-775907 (P2_1/m): hull 42 meV/atom, not observed; materials_project mp-775907 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.437577+00:00
- mp-754759 (R-3c): hull 49 meV/atom, not observed; materials_project mp-754759 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.437577+00:00
- mp-13061 (P-3m1): hull 57 meV/atom, observed; materials_project mp-13061 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.437577+00:00

Experimental gaps: 5600 meV to 5600 meV across 1 value(s), median 5600 meV
- expt_gap: 5600 meV; expt_gap expt_gap:13:Y2O3 fetched 2026-11-02T12:00:00+00:00

Hazard: GHS codes H315, H319, H320, H335, H413 in 274 of 548 notifications (ECHA attribution applies)
Literature: 1480 matched, 839 with abstracts, 5 read (title_and_abstract; query 'Y2O3 thin film')
Caveats:
- band_offsets_not_checked: Band offsets to the substrate are not checked by this screen. (source: scoring_profile#criteria.band_gap.standing_caveat)

### ZrO2: 5, total 1.000
- Rationale: ZrO2 ranks 5 on stability (energy above hull) and band gap; see caveats.
- Flags: none
- Sensitivity: rank 4 to 6 over 12 perturbations (stable)
- Band gap source: experimental_median

| Criterion | Raw | Source | Normalized | Weight | Contribution | Record | Fetched |
|---|---|---|---|---|---|---|---|
| stability (energy above hull) | 0 meV/atom | GGA_GGA+U_R2SCAN | 1.000 | 1.000 | 1.000 | none |  |
| band gap | 4990 meV | experimental_median | 0.998 | 1.000 | 0.998 | none |  |
| hazard | missing | config/hazard_policy.yaml | 1.000 | 1.000 | 1.000 | none |  |
| simplicity | 2 elements | composition | 1.000 | 1.000 | 1.000 | none |  |
| evidence | 5 abstracts | openalex | 1.000 | 1.000 | 1.000 | none |  |
| dielectric constant | 21.3 | mp_dfpt | missing | 0.000 | 0.000 | none |  |
- hazard notes: GHS codes in 1116 notifications: []

Polymorphs: 20 with MP ids (6 observed, 14 theoretical, 0 unknown).
- Ground state: mp-2858 (P2_1/c), hull 0 meV/atom, observed
- Scored polymorph is the ground state: yes; hull status conflict among functionals: no
- mp-2858 (P2_1/c): hull 0 meV/atom, observed; materials_project mp-2858 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.200392+00:00
- mp-776404 (Pbca): hull 9 meV/atom, not observed; materials_project mp-776404 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.200392+00:00
- mp-1190186 (Pbca): hull 13 meV/atom, observed; materials_project mp-1190186 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.200392+00:00
- mp-556605 (Pca2_1): hull 17 meV/atom, observed; materials_project mp-556605 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.200392+00:00
- mp-2574 (P4_2/nmc): hull 27 meV/atom, observed; materials_project mp-2574 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.200392+00:00

Experimental gaps: 4990 meV to 4990 meV across 1 value(s), median 4990 meV
- expt_gap: 4990 meV; expt_gap expt_gap:0:ZrO2 fetched 2026-11-02T12:00:00+00:00

Hazard: no GHS hazard codes in 1116 notifications (ECHA attribution applies)
Literature: 3767 matched, 2298 with abstracts, 5 read (title_and_abstract; query 'ZrO2 thin film')
Caveats:
- band_offsets_not_checked: Band offsets to the substrate are not checked by this screen. (source: scoring_profile#criteria.band_gap.standing_caveat)

### Ta2O5: 6, total 0.968
- Rationale: Ta2O5 ranks 6 on stability (energy above hull) and band gap; see caveats.
- Flags: hull_status_conflict
- Sensitivity: rank 5 to 7 over 12 perturbations (stable)
- Band gap source: experimental_median

| Criterion | Raw | Source | Normalized | Weight | Contribution | Record | Fetched |
|---|---|---|---|---|---|---|---|
| stability (energy above hull) | 0 meV/atom | GGA_GGA+U_R2SCAN | 1.000 | 1.000 | 1.000 | none |  |
| band gap | 4200 meV | experimental_median | 0.840 | 1.000 | 0.840 | none |  |
| hazard | missing | config/hazard_policy.yaml | 1.000 | 1.000 | 1.000 | none |  |
| simplicity | 2 elements | composition | 1.000 | 1.000 | 1.000 | none |  |
| evidence | 5 abstracts | openalex | 1.000 | 1.000 | 1.000 | none |  |
| dielectric constant | 33.8 | mp_dfpt | missing | 0.000 | 0.000 | none |  |
- hazard notes: GHS codes in 80 notifications: []

Polymorphs: 24 with MP ids (3 observed, 21 theoretical, 0 unknown).
- Ground state: mp-10390 (C2/c), hull 0 meV/atom, observed
- Scored polymorph is the ground state: yes; hull status conflict among functionals: yes
- mp-10390 (C2/c): hull 0 meV/atom, observed; materials_project mp-10390 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.452757+00:00
- mp-1539317 (Pmmn): hull 14 meV/atom, not observed; materials_project mp-1539317 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.452757+00:00
- mp-1238961 (P2/m): hull 14 meV/atom, not observed; materials_project mp-1238961 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.452757+00:00
- mp-1392387 (Pmmn): hull 15 meV/atom, not observed; materials_project mp-1392387 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.452757+00:00
- mp-1218312 (Pm): hull 52 meV/atom, not observed; materials_project mp-1218312 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.452757+00:00

Experimental gaps: 4200 meV to 4200 meV across 1 value(s), median 4200 meV
- expt_gap: 4200 meV; expt_gap expt_gap:8:Ta2O5 fetched 2026-11-02T12:00:00+00:00

Hazard: no GHS hazard codes in 80 notifications (ECHA attribution applies)
Literature: 1683 matched, 1116 with abstracts, 5 read (title_and_abstract; query 'Ta2O5 thin film')
Caveats:
- band_offsets_not_checked: Band offsets to the substrate are not checked by this screen. (source: scoring_profile#criteria.band_gap.standing_caveat)

### TiO2: 7, total 0.932
- Rationale: TiO2 ranks 7 on stability (energy above hull) and band gap; see caveats.
- Flags: hull_status_conflict
- Sensitivity: rank 6 to 8 over 12 perturbations (stable)
- Band gap source: experimental_median

| Criterion | Raw | Source | Normalized | Weight | Contribution | Record | Fetched |
|---|---|---|---|---|---|---|---|
| stability (energy above hull) | 0 meV/atom | GGA_GGA+U_R2SCAN | 1.000 | 1.000 | 1.000 | none |  |
| band gap | 3300 meV | experimental_median | 0.660 | 1.000 | 0.660 | none |  |
| hazard | missing | config/hazard_policy.yaml | 1.000 | 1.000 | 1.000 | none |  |
| simplicity | 2 elements | composition | 1.000 | 1.000 | 1.000 | none |  |
| evidence | 5 abstracts | openalex | 1.000 | 1.000 | 1.000 | none |  |
| dielectric constant | 63.2 | mp_dfpt | missing | 0.000 | 0.000 | none |  |
- hazard notes: GHS codes in 11189 notifications: ['H319', 'H320', 'H335', 'H351', 'H372', 'H413']

Polymorphs: 46 with MP ids (17 observed, 37 theoretical, 0 unknown).
- Ground state: mp-390 (I4_1/amd), hull 0 meV/atom, observed
- Scored polymorph is the ground state: yes; hull status conflict among functionals: yes
- mp-390 (I4_1/amd): hull 0 meV/atom, observed; materials_project mp-390 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.343270+00:00
- mp-1840 (Pbca): hull 3 meV/atom, observed; materials_project mp-1840 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.343270+00:00
- mp-1439 (Pbcn): hull 5 meV/atom, observed; materials_project mp-1439 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.343270+00:00
- mp-554278 (C2/m): hull 6 meV/atom, observed; materials_project mp-554278 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.343270+00:00
- mp-2657 (P4_2/mnm): hull 10 meV/atom, observed; materials_project mp-2657 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.343270+00:00

Experimental gaps: 3300 meV to 3300 meV across 1 value(s), median 3300 meV
- expt_gap: 3300 meV; expt_gap expt_gap:1:TiO2 fetched 2026-11-02T12:00:00+00:00

Hazard: GHS codes H319, H320, H335, H351, H372, H413 in 4157 of 11189 notifications (ECHA attribution applies)
Literature: 21132 matched, 13032 with abstracts, 5 read (title_and_abstract; query 'TiO2 thin film')
Caveats:
- band_offsets_not_checked: Band offsets to the substrate are not checked by this screen. (source: scoring_profile#criteria.band_gap.standing_caveat)

### BaTiO3: 8, total 0.822
- Rationale: BaTiO3 ranks 8 on stability (energy above hull) and band gap; see caveats.
- Flags: hull_status_conflict
- Sensitivity: rank 7 to 8 over 12 perturbations (stable)
- Band gap source: experimental_median

| Criterion | Raw | Source | Normalized | Weight | Contribution | Record | Fetched |
|---|---|---|---|---|---|---|---|
| stability (energy above hull) | 0 meV/atom | GGA_GGA+U_R2SCAN | 1.000 | 1.000 | 1.000 | none |  |
| band gap | 3060 meV | experimental_median | 0.612 | 1.000 | 0.612 | none |  |
| hazard | missing | config/hazard_policy.yaml | 1.000 | 1.000 | 1.000 | none |  |
| simplicity | 3 elements | composition | 0.500 | 1.000 | 0.500 | none |  |
| evidence | 5 abstracts | openalex | 1.000 | 1.000 | 1.000 | none |  |
| dielectric constant | 13.0 | mp_dfpt | missing | 0.000 | 0.000 | none |  |
- hazard notes: GHS codes in 0 notifications: []

Polymorphs: 11 with MP ids (11 observed, 1 theoretical, 0 unknown).
- Ground state: mp-5777 (Amm2), hull 0 meV/atom, observed
- Scored polymorph is the ground state: yes; hull status conflict among functionals: yes
- mp-5777 (Amm2): hull 0 meV/atom, observed; materials_project mp-5777 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.406487+00:00
- mp-5020 (R3m): hull 0 meV/atom, observed; materials_project mp-5020 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.406487+00:00
- mp-558125 (C222_1): hull 1 meV/atom, observed; materials_project mp-558125 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.406487+00:00
- mp-5986 (P4mm): hull 2 meV/atom, observed; materials_project mp-5986 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.406487+00:00
- mp-5933 (P6_3/mmc): hull 3 meV/atom, observed; materials_project mp-5933 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.406487+00:00

Experimental gaps: 2960 meV to 3130 meV across 5 value(s), median 3060 meV
- expt_gap: 3100 meV; expt_gap expt_gap:2:BaTiO3 fetched 2026-11-02T12:00:00+00:00
- expt_gap: 3040 meV; expt_gap expt_gap:4:BaTiO3 fetched 2026-11-02T12:00:00+00:00
- expt_gap: 2960 meV; expt_gap expt_gap:6:BaTiO3 fetched 2026-11-02T12:00:00+00:00
- expt_gap: 3130 meV; expt_gap expt_gap:7:BaTiO3 fetched 2026-11-02T12:00:00+00:00
- expt_gap: 3060 meV; expt_gap expt_gap:10:BaTiO3 fetched 2026-11-02T12:00:00+00:00

Hazard: no GHS notification counts available; hazard unknown
Literature: 3181 matched, 2092 with abstracts, 5 read (title_and_abstract; query 'BaTiO3 thin film')
Caveats:
- band_offsets_not_checked: Band offsets to the substrate are not checked by this screen. (source: scoring_profile#criteria.band_gap.standing_caveat)


## Reference anchors (never ranked)

### SiO2: would rank 1 of 8, total 1.000
- Flags: none
- Band gap source: tbmbj

| Criterion | Raw | Source | Normalized | Weight | Contribution | Record | Fetched |
|---|---|---|---|---|---|---|---|
| stability (energy above hull) | 0 meV/atom | GGA_GGA+U_R2SCAN | 1.000 | 1.000 | 1.000 | none |  |
| band gap | 8097 meV | tbmbj | 1.000 | 1.000 | 1.000 | none |  |
| hazard | missing | config/hazard_policy.yaml | 1.000 | 1.000 | 1.000 | none |  |
| simplicity | 2 elements | composition | 1.000 | 1.000 | 1.000 | none |  |
| evidence | 5 abstracts | openalex | 1.000 | 1.000 | 1.000 | none |  |
| dielectric constant | 4.6 | mp_dfpt | missing | 0.000 | 0.000 | none |  |
- hazard notes: GHS codes in 9127 notifications: ['H315', 'H319', 'H320', 'H335', 'H341', 'H350', 'H350i', 'H372', 'H373']

Polymorphs: 322 with MP ids (209 observed, 238 theoretical, 0 unknown).
- Ground state: mp-7000 (P3_121), hull 0 meV/atom, observed
- Scored polymorph is the ground state: yes; hull status conflict among functionals: yes
- mp-7000 (P3_121): hull 0 meV/atom, observed; materials_project mp-7000 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.300696+00:00
- mp-6930 (P3_221): hull 1 meV/atom, observed; materials_project mp-6930 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.300696+00:00
- mp-12787 (C2/c): hull 3 meV/atom, observed; materials_project mp-12787 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.283223+00:00
- mp-7029 (P4_32_12): hull 5 meV/atom, observed; materials_project mp-7029 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.300696+00:00
- mp-6945 (P4_12_12): hull 5 meV/atom, observed; materials_project mp-6945 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.300696+00:00

Experimental gaps: none in the public gap tables

Hazard: GHS codes H315, H319, H320, H335, H341, H350, H350i, H372, H373 in 1403 of 9127 notifications (ECHA attribution applies)
Literature: 21347 matched, 14434 with abstracts, 5 read (title_and_abstract; query 'SiO2 thin film')


## Excluded

### ThO2: excluded
- Excluded: hazard.radioactive_exclude (['Th'] has no stable isotope); rule source config/hazard_policy.yaml#tiers.radioactive_exclude
- Flags: band_gap_conflict
- Band gap source: experimental_median

| Criterion | Raw | Source | Normalized | Weight | Contribution | Record | Fetched |
|---|---|---|---|---|---|---|---|
| stability (energy above hull) | 0 meV/atom | GGA_GGA+U_R2SCAN | 1.000 | 1.000 | 1.000 | none |  |
| band gap | 3400 meV | experimental_median | 0.680 | 1.000 | 0.680 | none |  |
| hazard | missing | config/hazard_policy.yaml | 0.000 | 1.000 | 0.000 | none |  |
| simplicity | 2 elements | composition | 1.000 | 1.000 | 1.000 | none |  |
| evidence | 5 abstracts | openalex | 1.000 | 1.000 | 1.000 | none |  |
| dielectric constant | missing (not_computed) | mp_dfpt | missing | 0.000 | 0.000 | none |  |
- hazard notes: GHS codes in 213 notifications: ['H301', 'H311', 'H331', 'H350', 'H373']

Polymorphs: 2 with MP ids (2 observed, 0 theoretical, 0 unknown).
- Ground state: mp-643 (Fm-3m), hull 0 meV/atom, observed
- Scored polymorph is the ground state: yes; hull status conflict among functionals: no
- mp-643 (Fm-3m): hull 0 meV/atom, observed; materials_project mp-643 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.379700+00:00
- mp-1102569 (Pnma): hull 150 meV/atom, observed, excluded by stability.cutoff; materials_project mp-1102569 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.379700+00:00

Experimental gaps: 3300 meV to 3500 meV across 2 value(s), median 3400 meV
- expt_gap: 3500 meV; expt_gap expt_gap:5:ThO2 fetched 2026-11-02T12:00:00+00:00
- expt_gap: 3300 meV; expt_gap expt_gap:11:ThO2 fetched 2026-11-02T12:00:00+00:00

Hazard: GHS codes H301, H311, H331, H350, H373 in an unreported number of 213 notifications (ECHA attribution applies)
Literature: 31 matched, 20 with abstracts, 5 read (title_and_abstract; query 'ThO2 thin film')
Caveats:
- band_offsets_not_checked: Band offsets to the substrate are not checked by this screen. (source: scoring_profile#criteria.band_gap.standing_caveat)

### BeO: excluded
- Excluded: hazard.exclude (IARC Group 1: beryllium and beryllium compounds); rule source config/hazard_policy.yaml#tiers.exclude.Be
- Flags: none
- Band gap source: experimental_median

| Criterion | Raw | Source | Normalized | Weight | Contribution | Record | Fetched |
|---|---|---|---|---|---|---|---|
| stability (energy above hull) | 0 meV/atom | GGA_GGA+U_R2SCAN | 1.000 | 1.000 | 1.000 | none |  |
| band gap | 10390 meV | experimental_median | 1.000 | 1.000 | 1.000 | none |  |
| hazard | missing | config/hazard_policy.yaml | 0.000 | 1.000 | 0.000 | none |  |
| simplicity | 2 elements | composition | 1.000 | 1.000 | 1.000 | none |  |
| evidence | 5 abstracts | openalex | 1.000 | 1.000 | 1.000 | none |  |
| dielectric constant | 7.3 | mp_dfpt | missing | 0.000 | 0.000 | none |  |
- hazard notes: GHS codes in 49 notifications: ['H301', 'H305', 'H315', 'H317', 'H319', 'H330', 'H334', 'H335', 'H350', 'H350i', 'H361', 'H370', 'H372']

Polymorphs: 9 with MP ids (4 observed, 6 theoretical, 0 unknown).
- Ground state: mp-2542 (P6_3mc), hull 0 meV/atom, observed
- Scored polymorph is the ground state: yes; hull status conflict among functionals: no
- mp-2542 (P6_3mc): hull 0 meV/atom, observed; materials_project mp-2542 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.421036+00:00
- mp-1778 (F-43m): hull 7 meV/atom, observed; materials_project mp-1778 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.421036+00:00
- mp-7599 (P4_2/mnm): hull 15 meV/atom, observed; materials_project mp-7599 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.421036+00:00
- mp-1244907 (P1): hull 257 meV/atom, not observed, excluded by stability.cutoff; materials_project mp-1244907 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.421036+00:00
- mp-1244919 (P1): hull 264 meV/atom, not observed, excluded by stability.cutoff; materials_project mp-1244919 (GGA_GGA+U_R2SCAN) fetched 2026-11-02T23:34:49.421036+00:00

Experimental gaps: 10390 meV to 10390 meV across 1 value(s), median 10390 meV
- expt_gap: 10390 meV; expt_gap expt_gap:9:BeO fetched 2026-11-02T12:00:00+00:00

Hazard: GHS codes H301, H305, H315, H317, H319, H330, H334, H335, H350, H350i, H361, H370, H372 in an unreported number of 49 notifications (ECHA attribution applies)
Literature: 164 matched, 105 with abstracts, 5 read (title_and_abstract; query 'BeO thin film')
Caveats:
- band_offsets_not_checked: Band offsets to the substrate are not checked by this screen. (source: scoring_profile#criteria.band_gap.standing_caveat)


## What this screen cannot tell you

- breakdown field
- leakage current density
- band offsets to the substrate
- interface trap and defect density
- crystallization temperature
- interfacial reaction with the substrate
- the film's actual phase and density

## Verifier

- Checked 8 slot(s) and 2 evidence hit(s); passed: no
- quote_mismatch at evidence:https://openalex.org/W2114118400 (hit_dropped): This sentence does not appear in the abstract and was planted to show a failed quote check.

## Decision log

- 2026-11-02T12:00:00+00:00 pipeline build_sample: sample bundle generated from recorded cassettes with illustrative scores
