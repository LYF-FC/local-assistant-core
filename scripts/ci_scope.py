"""Conservative PR CI selection. Scheduled/manual runs remain full; PRs and main pushes use exact Git comparisons."""

import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
JOBS = ("backend", "frontend", "postgres", "containers")
ROOT_DOCS = {
    "README.md",
    "CHANGELOG.md",
    "CONTEXT.md",
    "ROADMAP.md",
    "ARCHITECTURE.md",
    "DECISIONS.md",
    "OPERATIONS.md",
    "SETUP.md",
    "SPEC_KIT.md",
}
FRONTEND_FILES = {
    "frontend/index.html",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig.json",
    "frontend/tsconfig.app.json",
    "frontend/tsconfig.node.json",
    "frontend/vite.config.ts",
    "frontend/playwright.config.ts",
    "frontend/playwright.local.config.ts",
    "frontend/Dockerfile",
    "frontend/nginx.conf",
}
UI_SUFFIXES = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".css",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".json",
}


def selection(mode, reason, changed_count):
    enabled = (
        JOBS
        if mode == "full"
        else ("frontend", "containers")
        if mode == "interface"
        else ()
    )
    return {
        "mode": mode,
        "reason": reason,
        "changed_count": changed_count,
        **{job: job in enabled for job in JOBS},
    }


def classify(paths):
    paths = list(paths)
    if not paths:
        return selection("full", "No reliable changed-path set", 0)
    interface = False
    for path in paths:
        parts = path.split("/")
        if path.startswith("/") or any(p in {"", ".", ".."} for p in parts):
            return selection("full", "Unrecognized path", len(paths))
        if path in ROOT_DOCS or (
            path.startswith(("docs/", "specs/")) and path.endswith(".md")
        ):
            continue
        if path in FRONTEND_FILES or (
            path.startswith(("frontend/src/", "frontend/e2e/"))
            and PurePosixPath(path).suffix in UI_SUFFIXES
        ):
            interface = True
            continue
        # Backend, migrations, authorization, dependencies, infrastructure, CI,
        # governance and unknown/new paths all deliberately take the full route.
        return selection(
            "full", "Runtime, configuration or unrecognized path", len(paths)
        )
    return selection(
        "interface" if interface else "documentation",
        "Only interface/documentation paths"
        if interface
        else "Only documentation paths",
        len(paths),
    )


def determine(event, base, head, *, root=ROOT):
    if event not in {"pull_request", "push"}:
        return selection(
            "full", "Scheduled, manual or unrecognized events require full coverage", 0
        )
    if not all(
        re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", x or "") for x in (base, head)
    ):
        return selection("full", "Comparison identifiers unavailable", 0)
    try:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                "--no-renames",
                "-z",
                f"{base}{'...' if event == 'pull_request' else '..'}{head}",
                "--",
            ],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return selection("full", "Comparison unavailable", 0)
    return classify(os.fsdecode(path) for path in result.stdout.split(b"\0") if path)


def main():
    result = determine(
        os.environ.get("BUTLER_CI_EVENT", ""),
        os.environ.get("BUTLER_CI_BASE_SHA", ""),
        os.environ.get("BUTLER_CI_HEAD_SHA", ""),
    )
    print(json.dumps(result, sort_keys=True))
    if target := os.environ.get("GITHUB_OUTPUT"):
        with Path(target).open("a") as output:
            output.writelines(f"{job}={str(result[job]).lower()}\n" for job in JOBS)
            output.write(f"mode={result['mode']}\n")
    if target := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(target).open("a") as summary:
            summary.write("## Butler CI scope\n\n")
            summary.write(f"Mode: **{result['mode']}**. {result['reason']}.\n\n")
            summary.write(
                f"Changed paths: {result['changed_count']}. Repository policy checks always run.\n\n"
            )
            summary.writelines(
                f"- {job}: {'selected' if result[job] else 'not selected (not test-pass evidence)'}\n"
                for job in JOBS
            )


if __name__ == "__main__":
    main()
