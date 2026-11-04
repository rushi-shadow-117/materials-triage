import type { ReactNode } from "react";
import { SCREEN_HELP, helpFor } from "../help";

/** A collapsible "How to use this screen" panel; the text lives in help.ts. */
export function ScreenHelp({ screen }: { screen: keyof typeof SCREEN_HELP }) {
  const entry = SCREEN_HELP[screen];
  if (!entry) return null;
  return (
    <details className="panel help" data-testid="screen-help">
      <summary>How to use this screen</summary>
      <p>{entry.text}</p>
      <small className="muted">From {entry.source}.</small>
    </details>
  );
}

/** A plain-language tooltip on a criterion, flag, caveat, exclusion rule, or evidence tier.
 * Shown as the title and to assistive technology; the wrapped text is unchanged. */
export function Tip({
  kind,
  id,
  children,
}: {
  kind: "criterion" | "flag" | "caveat" | "exclusion" | "tier";
  id: string;
  children: ReactNode;
}) {
  const entry = helpFor(kind, id);
  if (!entry) return <>{children}</>;
  return (
    <abbr className="tip" title={entry.text} aria-label={`${id}: ${entry.text}`} data-help={kind}>
      {children}
    </abbr>
  );
}
