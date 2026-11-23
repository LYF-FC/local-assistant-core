# Spec 077 pre-implementation analysis

Base `f88fd5c575cbdf252facbcd0b25cbca9319aac0b`.

| Finding | Treatment |
|---|---|
| The inbox already lists unconfirmed and failed filings with an "Open related document" link; the bare status text was the gap. | Shared plain-language reasons (R3). |
| The invoice-review screen hides the filing panel until loaded, and the panel did not read its status or know whether the exact request existed (a request form was offered for an existing request). | Panel reads its own filings when it appears; form withheld until known; hint in the invoice panel (R4). Invoice-review load behaviour untouched. |
| A connection-refused answer service already maps to `unavailable` (httpx errors are caught). | Confirmed live and by test; no backend change (R5). |
| `restart`/`restart --kill`/`rebuild` bring every service up, which would silently end a model outage. | Outage flag file re-applies the stop (R2). |
| A write-only outage ends terminal `failed` after three attempts (spec 069). | Characterised, stated as a limit and owner option; not changed (D4). |
| Answers need a reviewed source: a question before any reviewed document returns `no_sources`, not `unavailable`. | The checker and guide order the question after review. |
