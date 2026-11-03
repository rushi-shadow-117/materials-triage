"""A deterministic fake language model for CI.

It answers from the request text alone: an out-of-scope request gets the fixed refusal text
from the core policy; anything else gets a template rationale with no digits and no formulas.
Same input, same output, no network. Track B ships its own fake for the agent loop; this one
drives the harness's adversarial transcripts until the agent merges.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from materials_triage.config.schema import RefusalPolicy

REFUSALS = RefusalPolicy()

# Patterns are matched on the lowercased request. Order matters: first match wins.
TRIGGERS: list[tuple[str, str]] = [
    (r"\b(private|internal|unpublished|our (lab )?results|confidential)\b", "private_data"),
    (
        r"\b(disable|turn off|ignore|bypass|override|skip)\b.*"
        r"\b(filter|rule|constraint|toxicity|hazard|policy|verif)",
        "config_change",
    ),
    (r"\b(i am|i'm|as|this is) (the |an? )?(admin|administrator|fde|site admin)", "config_change"),
    (r"\badd\b.*\b(allowed|allow|permitted) list\b", "config_change"),
    (
        r"\b(synthesi[sz]e|deposit|grow|order|schedule|queue|run the (experiment|furnace)"
        r"|wetlab|wet lab)\b",
        "wetlab",
    ),
    (
        r"\b(estimate|predict|guess|fill in)\b.*\b(gap|value|missing|constant|field|number)",
        "estimates",
    ),
]

TEMPLATE_RATIONALE = (
    "{formula} ranks {rank} on {criterion:stability} and {criterion:band_gap}; "
    "see caveats. Missing values are shown as missing."
)


@dataclass
class FakeLLM:
    calls: int = 0
    log: list[str] = field(default_factory=list)

    def refusal_for(self, request: str) -> str | None:
        text = request.lower()
        for pattern, policy in TRIGGERS:
            if re.search(pattern, text):
                return str(getattr(REFUSALS, policy))
        return None

    def respond(self, request: str) -> str:
        self.calls += 1
        refusal = self.refusal_for(request)
        if refusal is not None:
            self.log.append(f"fake_llm refusal: {refusal[:40]}")
            return refusal
        self.log.append("fake_llm rationale template")
        return TEMPLATE_RATIONALE
