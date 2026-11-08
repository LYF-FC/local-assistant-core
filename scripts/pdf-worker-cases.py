"""Generate synthetic parser acceptance cases; pipe only to an isolated test worker."""

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend/tests"))
from pdf_fixtures import pdf

cases = [
    ("one", pdf(), "ready", "Synthetic invoice 100.00", 1),
    (
        "pages",
        pdf(("Synthetic first", "Second café")),
        "ready",
        "Synthetic first\nSecond café",
        2,
    ),
    ("blank", pdf(("",)), "no_text", "", 1),
    ("mixed", pdf(("Synthetic", "")), "ready", "Synthetic\n", 2),
    ("encrypted", pdf(encrypted=True), "encrypted", "", 0),
    ("invalid", b"%PDF-invalid\n", "invalid", "", 0),
    ("page-limit", pdf(tuple("Synthetic" for _ in range(13))), "resource_limit", "", 0),
    (
        "text-limit",
        pdf(tuple("\n".join(["x" * 80] * 40) for _ in range(11)), compressed=True),
        "resource_limit",
        "",
        0,
    ),
    (
        "output-limit",
        pdf(
            tuple("\n".join(["x" * 100] * 200) for _ in range(10)),
            compressed=True,
            font_size=1,
        ),
        "resource_limit",
        "",
        0,
    ),
]
print(
    json.dumps(
        [
            {
                "name": name,
                "original": base64.b64encode(raw).decode(),
                "status": status,
                "text": text,
                "pages": pages,
            }
            for name, raw, status, text, pages in cases
        ]
    )
)
