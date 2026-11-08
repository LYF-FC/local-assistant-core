"""Always-running gate: every selected job must pass; nonselected jobs are explicit skips."""

import json
import os

JOBS = ("backend", "frontend", "postgres", "containers")
REQUIRED = {
    "full": set(JOBS),
    "interface": {"frontend", "containers"},
    "documentation": set(),
}


def verify(results):
    scope = results.get("scope", {})
    if scope.get("result") != "success":
        raise ValueError("Scope/policy verification did not succeed")
    outputs = scope.get("outputs", {})
    mode = outputs.get("mode")
    if mode not in REQUIRED:
        raise ValueError("Unknown CI profile")
    for job in JOBS:
        selected = job in REQUIRED[mode]
        if outputs.get(job) != str(selected).lower():
            raise ValueError("Scope outputs do not match the declared profile")
        if results.get(job, {}).get("result") != ("success" if selected else "skipped"):
            raise ValueError("Selected check failed/missing or an unexpected check ran")
    return mode


if __name__ == "__main__":
    try:
        mode = verify(json.loads(os.environ.get("BUTLER_CI_RESULTS", "{}")))
    except (ValueError, TypeError, AttributeError):
        raise SystemExit(
            "CI gate refused: required scope/check evidence is incomplete"
        ) from None
    print(
        "CI gate passed for profile:",
        mode,
        "; skipped checks are not test-pass evidence",
    )
