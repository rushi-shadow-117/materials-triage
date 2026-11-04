"""Attribute every rank change between two bundles to data, config, model, the candidate
set, or displacement by another changed composition. All applicable causes are listed."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from materials_triage.records import Provenance
from materials_triage.records.bundle import Anchor, Candidate, ProvenanceBundle

CAUSE_ORDER = ("candidate_set", "data", "config", "model", "displaced")


def fingerprint(row: Candidate | Anchor) -> frozenset[tuple[str, str, str, str | None]]:
    """Every provenance reachable from the row's summary, minus fetch time and raw row id."""
    found: list[Provenance] = []
    g = row.group
    p = g.polymorphs
    for prow in [p.ground_state, p.lowest_observed, p.scored, *p.top_by_hull]:
        if prow is None:
            continue
        if prow.hull_energy is not None:
            found.append(prow.hull_energy.provenance)
        found.extend(v.provenance for v in prow.band_gap.values())
        found.extend(v.provenance for v in prow.dielectric.values())
    if g.hazard is not None:
        found.append(g.hazard.provenance)
    if g.experimental_gaps is not None:
        found.extend(v.value_ev.provenance for v in g.experimental_gaps.values)
    if g.literature is not None:
        found.extend(h.provenance for h in g.literature.hits)
    found.extend(r.provenance for r in g.reference_values)
    if row.score is not None:
        found.extend(cs.provenance for cs in row.score.criteria if cs.provenance is not None)
    return frozenset((f.source, f.source_record_id, f.raw_sha256, f.source_version) for f in found)


@dataclass
class Change:
    composition: str
    rank_a: int | None
    rank_b: int | None
    excluded_a: str | None
    excluded_b: str | None
    causes: list[str] = field(default_factory=list)
    detail: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.rank_a != self.rank_b or self.excluded_a != self.excluded_b

    @property
    def delta(self) -> str:
        if self.rank_a is None or self.rank_b is None:
            return "n/a"
        return f"{self.rank_b - self.rank_a:+d}"


@dataclass
class DiffReport:
    run_a: str
    run_b: str
    header: list[str]
    changes: list[Change]
    anchors: list[str]
    unchanged: int


def _labels(bundle: ProvenanceBundle, composition: str) -> Counter[str]:
    return Counter(e.label.value for e in bundle.evidence if e.composition == composition)


def _settings_diff(a: ProvenanceBundle, b: ProvenanceBundle) -> list[str]:
    sa, sb = a.criteria.effective_settings, b.criteria.effective_settings
    out = [
        f"{k}: {sa.get(k)} -> {sb.get(k)}"
        for k in sorted(set(sa) | set(sb))
        if sa.get(k) != sb.get(k)
    ]
    if a.run.policy_version != b.run.policy_version:
        out.append(f"policy_version: {a.run.policy_version} -> {b.run.policy_version}")
    return out


def _crossed(ch: Change, other: Change) -> bool:
    """`other` moved past `ch`: ranks swapped order, or `other` left from above / arrived
    above `ch` (a ranked row that disappears or appears shifts everything below it)."""
    assert ch.rank_a is not None and ch.rank_b is not None
    if other.rank_a is not None and other.rank_b is not None:
        return (other.rank_a - ch.rank_a) * (other.rank_b - ch.rank_b) < 0
    if other.rank_a is not None and other.rank_b is None:
        return other.rank_a < ch.rank_a and ch.rank_b < ch.rank_a
    if other.rank_a is None and other.rank_b is not None:
        return other.rank_b < ch.rank_b and ch.rank_b > ch.rank_a
    return False


def diff(a: ProvenanceBundle, b: ProvenanceBundle) -> DiffReport:
    rows_a = {c.composition: c for c in a.candidates}
    rows_b = {c.composition: c for c in b.candidates}
    config_changed = (
        a.run.config_sha != b.run.config_sha or a.run.policy_version != b.run.policy_version
    )
    model_changed = (
        a.run.model_version != b.run.model_version
        or a.run.prompt_hash != b.run.prompt_hash
        or a.run.provider != b.run.provider
    )
    settings_detail = _settings_diff(a, b)
    changes: list[Change] = []
    for comp in sorted(set(rows_a) | set(rows_b)):
        ca, cb = rows_a.get(comp), rows_b.get(comp)
        ch = Change(
            comp,
            ca.rank if ca else None,
            cb.rank if cb else None,
            ca.excluded.rule.value if ca and ca.excluded else None,
            cb.excluded.rule.value if cb and cb.excluded else None,
        )
        if ca is None or cb is None:
            ch.causes.append("candidate_set")
            ch.detail.append("present in run " + ("A only" if cb is None else "B only"))
            changes.append(ch)
            continue
        if not ch.changed:
            changes.append(ch)
            continue
        fa, fb = fingerprint(ca), fingerprint(cb)
        if fa != fb:
            # With the config changed, data is a cause only when a source version moved (the
            # run's source versions, or a record present in both runs at another version).
            # Within one version a record's provenance differs only by the call that supplied
            # it: an enriched row carries the per-formula summary and thermo documents, a
            # summary-level row the discovery page. Enrichment follows rank, so that
            # difference is a consequence of the config change.
            va: dict[tuple[str, str], set[str | None]] = {}
            vb: dict[tuple[str, str], set[str | None]] = {}
            for src, rid, _sha, ver in fa:
                va.setdefault((src, rid), set()).add(ver)
            for src, rid, _sha, ver in fb:
                vb.setdefault((src, rid), set()).add(ver)
            changed = a.run.source_versions != b.run.source_versions or any(
                va[k] != vb[k] for k in va.keys() & vb.keys()
            )
            if changed or not config_changed:
                ch.causes.append("data")
                ch.detail.append("record hashes or source versions differ")
            else:
                ch.detail.append("cross-checks fetched in one run only (enrichment follows rank)")
        if config_changed:
            ch.causes.append("config")
            ch.detail.append("; ".join(settings_detail) or "config sha differs")
        if model_changed:
            if _labels(a, comp) != _labels(b, comp):
                ch.causes.append("model")
                ch.detail.append(
                    f"evidence labels {dict(_labels(a, comp))} -> {dict(_labels(b, comp))}"
                )
            else:
                ch.detail.append("model changed, no label change (not causal)")
        changes.append(ch)
    # displacement: a changed row with no cause of its own crossed a row that has one
    with_cause = [c for c in changes if c.causes]
    for ch in changes:
        if not ch.changed or ch.causes or ch.rank_a is None or ch.rank_b is None:
            continue
        for other in with_cause:
            if _crossed(ch, other):
                ch.causes.append("displaced")
                ch.detail.append(f"displaced_by {other.composition} ({other.causes[0]})")
                break
    for ch in changes:
        if ch.changed and not ch.causes:
            ch.causes.append("unattributed")
            ch.detail.append("same data, config, and model; scorer code or tie-break changed")
    header = [
        f"config_sha: {a.run.config_sha} -> {b.run.config_sha}",
        f"policy_version: {a.run.policy_version} -> {b.run.policy_version}",
        f"model: {a.run.model_version} / {a.run.prompt_hash} -> "
        f"{b.run.model_version} / {b.run.prompt_hash}",
        f"source_versions: {a.run.source_versions} -> {b.run.source_versions}",
        "code_version: "
        + " -> ".join(
            str(
                next(
                    (d.detail.get("code_version") for d in x.decision_log if d.step == "start"),
                    "unknown",
                )
            )
            for x in (a, b)
        ),
    ]
    anchors = []
    anchors_b = {x.composition: x for x in b.anchors}
    for x in a.anchors:
        y = anchors_b.get(x.composition)
        anchors.append(
            f"{x.composition}: would rank {x.would_rank} of {x.out_of} -> "
            + (f"{y.would_rank} of {y.out_of}" if y else "absent")
        )
    return DiffReport(
        run_a=str(a.run.run_id),
        run_b=str(b.run.run_id),
        header=header,
        changes=[c for c in changes if c.changed],
        anchors=anchors,
        unchanged=sum(1 for c in changes if not c.changed),
    )


def to_markdown(report: DiffReport) -> str:
    lines = [f"# Diff: {report.run_a} -> {report.run_b}", ""]
    lines += [f"- {h}" for h in report.header]
    lines += [
        "",
        f"{len(report.changes)} composition(s) changed, {report.unchanged} unchanged.",
        "",
    ]
    if report.changes:
        lines.append("| composition | rank A | rank B | delta | causes | detail |")
        lines.append("|---|---|---|---|---|---|")
        for c in report.changes:
            ra = c.excluded_a or (c.rank_a if c.rank_a is not None else "absent")
            rb = c.excluded_b or (c.rank_b if c.rank_b is not None else "absent")
            causes = ", ".join(c.causes)
            detail = "; ".join(c.detail)
            lines.append(f"| {c.composition} | {ra} | {rb} | {c.delta} | {causes} | {detail} |")
    if report.anchors:
        lines += ["", "Anchors:"] + [f"- {a}" for a in report.anchors]
    return "\n".join(lines) + "\n"
