import { useState } from "react";
import type { ChartPoint, ChartView } from "../view";

/** Band gap versus dielectric constant, Ashby-style, as plain SVG. Every number shown is
 * server text (gap_text, k_text, tick labels); the browser only places points. */
export default function GapKChart({ chart, audit }: { chart: ChartView; audit: boolean }) {
  const [hover, setHover] = useState<ChartPoint | null>(null);
  const W = 640;
  const H = 360;
  const pad = { left: 56, right: 16, top: 12, bottom: 44 };
  const xMax = Math.max(...chart.x_ticks.map((t) => t.value), 0) || 1;
  const yMax = Math.max(...chart.y_ticks.map((t) => t.value), 0) || 1;
  const x = (v: number) => pad.left + (v / xMax) * (W - pad.left - pad.right);
  const y = (v: number) => H - pad.bottom - (v / yMax) * (H - pad.top - pad.bottom);
  const order: ChartPoint["status"][] = ["excluded", "ranked", "shortlist", "anchor"];
  const points = [...chart.points].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status));

  if (chart.points.length === 0) {
    return (
      <div className="panel" data-testid="chart">
        <h3 style={{ marginTop: 0 }}>Band gap versus dielectric constant</h3>
        <p className="muted">
          No candidate in this run has both a band gap and a computed dielectric constant, so there is nothing to plot.
        </p>
        <Unplotted items={chart.unplotted} />
      </div>
    );
  }

  return (
    <div className="panel" data-testid="chart">
      <h3 style={{ marginTop: 0 }}>Band gap versus dielectric constant</h3>
      <p className="muted">
        Every scored candidate with both values. Filled: the shortlist. Hollow: ranked beyond top N. Faint: excluded. Diamond: the reference
        material. Hover a point for its values and sources. Values come from the run's records, never from this page.
      </p>
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="band gap versus dielectric constant" className="chart">
          {chart.x_ticks.map((t) => (
            <g key={`x${t.value}`}>
              <line x1={x(t.value)} x2={x(t.value)} y1={pad.top} y2={H - pad.bottom} className="grid" />
              <text x={x(t.value)} y={H - pad.bottom + 16} textAnchor="middle" className="tick">{t.text}</text>
            </g>
          ))}
          {chart.y_ticks.map((t) => (
            <g key={`y${t.value}`}>
              <line x1={pad.left} x2={W - pad.right} y1={y(t.value)} y2={y(t.value)} className="grid" />
              <text x={pad.left - 6} y={y(t.value) + 4} textAnchor="end" className="tick">{t.text}</text>
            </g>
          ))}
          <line x1={pad.left} x2={W - pad.right} y1={H - pad.bottom} y2={H - pad.bottom} className="axis" />
          <line x1={pad.left} x2={pad.left} y1={pad.top} y2={H - pad.bottom} className="axis" />
          <text x={(pad.left + W - pad.right) / 2} y={H - 6} textAnchor="middle" className="label">{chart.x_label}</text>
          <text x={12} y={(pad.top + H - pad.bottom) / 2} textAnchor="middle" className="label" transform={`rotate(-90 12 ${(pad.top + H - pad.bottom) / 2})`}>
            {chart.y_label}
          </text>
          {points.map((p) => {
            const cx = x(p.gap);
            const cy = y(p.k);
            const common = {
              className: `point ${p.status}`,
              onMouseEnter: () => setHover(p),
              onMouseLeave: () => setHover(null),
              onFocus: () => setHover(p),
              onBlur: () => setHover(null),
              tabIndex: 0,
              "data-composition": p.composition,
              "data-status": p.status,
            };
            return (
              <g key={`${p.status}-${p.composition}`}>
                {p.status === "anchor" ? (
                  <polygon points={`${cx},${cy - 7} ${cx + 7},${cy} ${cx},${cy + 7} ${cx - 7},${cy}`} {...common}>
                    <title>{`${p.composition}: ${p.gap_text}, k ${p.k_text}`}</title>
                  </polygon>
                ) : (
                  <circle cx={cx} cy={cy} r={p.status === "shortlist" ? 6 : 4} {...common}>
                    <title>{`${p.composition}: ${p.gap_text}, k ${p.k_text}`}</title>
                  </circle>
                )}
                {(p.status === "shortlist" || p.status === "anchor") && (
                  <text x={cx + 8} y={cy - 6} className="point-label">{p.composition}</text>
                )}
              </g>
            );
          })}
        </svg>
        <div className="chart-hover" aria-live="polite" data-testid="chart-hover">
          {hover ? (
            <>
              <strong>{hover.composition}</strong> ({hover.status}) · band gap {hover.gap_text} from {hover.gap_source} · k {hover.k_text} from{" "}
              {hover.k_source}
              {audit && hover.record_ids.length > 0 && <> · records {hover.record_ids.join(", ")}</>}
            </>
          ) : (
            <span className="muted">Hover a point.</span>
          )}
        </div>
      </div>
      <Unplotted items={chart.unplotted} />
    </div>
  );
}

function Unplotted({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <p className="muted" data-testid="chart-unplotted">
      Not plotted: {items.join("; ")}.
    </p>
  );
}
