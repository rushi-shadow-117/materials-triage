# Scientist guide

You describe what you want, or paste a list of formulas. The tool fetches public data, scores
every candidate in code, and shows you a ranked shortlist with the reasons, the exclusions,
and the things it could not see. Nothing on the page is estimated; a missing value says
missing.

## Two ways in

**Describe a request.** Type the request as you would say it. A model turns it into the
criteria form below the box. "Parse and run" starts the search at once when the parse left
nothing to confirm (no refusal, nothing missing, no clamp, every property you named covered
by a criterion); otherwise, and always with "Parse, then confirm", the form shows what will
run and you confirm or edit it before anything is fetched. While the model reads the request
a panel counts the seconds; it is one model call. The form says how each property you named
was understood ("wide band gaps: band gap"), and lists any property no source covers. If no
model is configured the box says so; fill the form by hand instead.

**Rank my list.** Paste formulas or names separated by commas, semicolons, or new lines, at
most 50. The server splits the text and shows what matched as chips; an entry that matches no
formula or known name is a red chip with the reason, is reported as not found, and the rest
are ranked. Run stays off while the list is empty. Listed materials are never dropped
silently: one that fails a hard rule appears in the exclusion list with the rule. A request
in the Describe box is at most 2,000 characters; the counter under the box shows the count.

## Confirming criteria

The form shows every setting the run will use:

- Hard filters: band gap minimum and maximum, the energy-above-hull cutoff, the maximum
  number of elements, top N.
- Weights, as sliders inside the limits the site admin set.
- Output settings: verbosity, terminology (general applies the site glossary), units.
- Compare against: a formula added as a reference row for this run; it stays ranked too.

Under the sliders the form says how many model calls the run may make ("up to N model calls,
hard cap M") and why; with no model configured it says so instead.

Three notices can appear:

- **Clamped.** You asked for a value outside the site bounds; the form shows what you asked
  for and what will be used. Ask a site admin to change the bounds.
- **Not available from configured sources.** A property you asked for (conductivity, for
  example) has no source here. It is dropped from the criteria and listed under "What this
  screen cannot tell you".
- **The request does not say what to search for.** A request with no chemistry and no
  property preference is not run; add either, or use Rank my list.

Anion policy and the hazard policy come from the profile and the site admin and are not
editable here. "Non-toxic" maps to that policy: radioactive elements and IARC Group 1
elements are excluded, the admin's flag list is flagged.

## While it runs

Each step streams as it happens and says whether code or the model did it. Fetching, scoring,
and verification are code. Classifying abstracts and writing the one-line rationale are the
model. Cancel is always available; a cancelled run saves nothing.

## Reading the result

**PI summary.** One row per ranked candidate: rank, score, a one-line rationale, the key
caveat, the evidence tier, the dielectric constant where a source has it, and what is
missing. Flags sit under the material name. The reference row (SiO2 in the dielectric profile)
shows where the incumbent would rank; it never takes a place. Below the table: the excluded
materials with their rule and the config entry that holds it, the caveat texts, and "What
this screen cannot tell you". The PI view names no record ids.

**The chart.** Above the table, band gap against dielectric constant for every scored
candidate that has both: the shortlist filled and labelled, ranked rows beyond top N hollow,
excluded candidates faint, the reference material as a diamond. Hover a point for its values
and sources. The dielectric constant is the computed (DFPT) value of the polymorph that was
scored; a candidate without one is listed under the chart, never placed at zero.

**Audit view.** The same rows expanded: every criterion's raw value, source, normalized
value, weight, contribution, and record; the polymorph table with the ground state and the
structure that was scored; the evidence quotes with their verification status; the hazard
line as "codes in M of N notifications"; the config sha, prompt hash, model, and source
versions; the decision log.

**Drill-down.** Every value in the audit view links to where it came from: the record id,
method, fetch time, raw response hash, the other values of the same property the run holds
and which one was used, and the config entry with the rule that chose.

**Exports.** Markdown (the view), CSV (one row per candidate with every raw value and record
id), JSON (the whole bundle). From the command line, `materials-triage replay` re-ranks a
stored run and `materials-triage diff` says why two runs differ.

## Some things to know

- **Evidence tiers** come from paper abstracts: computed only, synthesized in bulk,
  deposited as a thin film, characterized for the application. The model picks the label and
  must quote the sentence that supports it; code checks the quote is in the abstract, and a
  failed quote is withheld, never fixed. Without a model the tier is "unclassified" and the
  evidence criterion carries no weight.
- **Band gaps** show every source side by side: experimental where a compendium has it,
  TBmBJ from JARVIS, PBE from Materials Project. The profile says which one scores and flags a
  conflict above the configured tolerance.
- **Polymorphs** are grouped by formula; the ground state is scored unless you name a
  Materials Project id. Theoretical structures nobody has made are marked.
- **Molecular crystals** (CO2, water) are excluded by their structural dimensionality; a
  layered or network solid is not.
- **Too few results.** When fewer candidates than top N pass, the run lists the relaxations
  it computed, each with how many candidates it would add. Applying one starts a new run;
  the original stays in the history.
- **Partial runs.** If a source does not answer, the run finishes without it, says so at the
  top, and marks the affected values missing.
- **Refusals.** Requests for lab actions, private data, estimates, or configuration changes
  are refused with a fixed sentence and nothing is fetched.

## Help in the app

Every screen opens with a collapsible "How to use this screen" panel, and criterion names,
flags, caveat ids, exclusion rules, and evidence tiers carry a tooltip (hover, or focus with
the keyboard). The Help link in the top bar shows this guide and the admin guide as served
by the running installation. All of that text lives in `web/src/help.ts`.

In a local installation with no sign-in (`AUTH_MODE=none`) the top bar has a role switcher
to try the scientist, field engineer, and admin views; with a real sign-in the role comes
from your token and the switcher does not exist.

## What this screen cannot tell you

Breakdown field, leakage current, band offsets to your substrate, interface defect density,
crystallization temperature, interfacial reaction with the substrate, the film's actual phase
and density, and (in the dielectric profile) moisture sensitivity. No open structured source
records these. Measure or consult the literature before committing deposition time.
