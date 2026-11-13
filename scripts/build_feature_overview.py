"""Offline, deterministic projection of approved scope and separately labelled critique."""

import argparse
import hashlib
import html
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/LYF-FC/local-assistant-core"
ID = r"[A-Z]+-[A-Z]?\d+"
NAMED = r"(?:CORE|ORG|DOC|HOME|CARE|OPS|EDU|WORK|FIN|CREATIVE)-\d+"
VERDICTS = ("Keep", "Generalize", "Consolidate", "Validate", "Challenge")
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
OUTPUTS = ("docs/FEATURE_OVERVIEW.md", "docs/FEATURE_DASHBOARD.html")


def register_rows(text):
    return [line for line in text.splitlines() if re.match(rf"^\| {ID} \|", line)]


def fingerprint(text):
    return hashlib.sha256(("\n".join(register_rows(text)) + "\n").encode()).hexdigest()


def unique(rows, key):
    result = {}
    for row in rows:
        identifier = row[key]
        if identifier in result:
            raise ValueError(f"Duplicate feature/review ID: {identifier}")
        result[identifier] = row
    return result


def parse_register(text):
    records = []
    for line in register_rows(text):
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 5:
            raise ValueError("Malformed register row")
        identifier, requirement, milestone, evidence, remaining = cells
        if evidence.startswith("partial"):
            status = "partial"
        elif evidence.startswith("planned"):
            status = "planned"
        else:
            raise ValueError(f"Unrecognized status; acceptance needs explicit review: {identifier}")
        records.append(
            {
                "id": identifier,
                "title": requirement.split(":", 1)[0],
                "requirement": requirement,
                "milestone": milestone,
                "evidence": evidence,
                "remaining": remaining,
                "status": status,
                "domain": identifier.split("-")[0],
            }
        )
    if not records:
        raise ValueError("Empty feature register")
    return unique(records, "id")


def parse_reviews(text):
    records = []
    for line in register_rows(text):
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 3 or cells[1] not in VERDICTS or len(cells[2].split()) < 12:
            raise ValueError("Malformed or placeholder critical review")
        records.append({"id": cells[0], "verdict": cells[1], "critique": cells[2]})
    return unique(records, "id")


def json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate metadata key: {key}")
        result[key] = value
    return result


def build_data(register, review, manifest):
    required = {
        "schema_version",
        "snapshot",
        "stages",
        "first_stage",
        "named_ids",
        "capabilities",
        "open_batches",
    }
    if set(manifest) != required or manifest["schema_version"] != 1:
        raise ValueError("Unknown progress metadata schema")
    snapshot = manifest["snapshot"]
    if not re.fullmatch(r"[a-f0-9]{40}", snapshot["main_sha"]):
        raise ValueError("Invalid verified snapshot SHA")
    date.fromisoformat(snapshot["date"])
    if snapshot["register_rows_sha256"] != fingerprint(register):
        raise ValueError("Snapshot/register fingerprint mismatch; reconcile merged evidence")
    features, reviews = parse_register(register), parse_reviews(review)
    if set(features) != set(reviews) or set(features) != set(manifest["first_stage"]):
        raise ValueError("Register, review and stage IDs must match exactly")
    named = manifest["named_ids"]
    expected_named = {identifier for identifier in features if re.fullmatch(NAMED, identifier)}
    if len(named) != len(set(named)) or set(named) != expected_named:
        raise ValueError("Named cohort differs from retained product features")
    if not manifest["stages"] or any(
        stage not in manifest["stages"] for stage in manifest["first_stage"].values()
    ):
        raise ValueError("Unknown first-stage assignment")
    capabilities = manifest["capabilities"]
    if not capabilities or sum(item["baseline"] is True for item in capabilities) != 1:
        raise ValueError("Exactly one imported baseline is required")
    for item in capabilities:
        if not re.fullmatch(r"(?:pull/\d+|docs/[A-Za-z0-9_/-]+\.md)", item["path"]):
            raise ValueError("Capability evidence must be a repository path or public PR")
    pending = {}
    for batch in manifest["open_batches"]:
        if (
            not isinstance(batch["pr"], int)
            or batch["pr"] < 1
            or not set(batch["ids"]) <= set(features)
        ):
            raise ValueError("Invalid open-batch metadata")
        for identifier in batch["ids"]:
            pending[identifier] = (
                f"Open PR #{batch['pr']}: {batch['note']} — excluded from merged totals."
            )
    for identifier, item in features.items():
        item.update(
            named=identifier in named,
            stage=manifest["first_stage"][identifier],
            review=reviews[identifier],
            pending=pending.get(identifier, ""),
        )
    return {
        "base": snapshot["main_sha"],
        "snapshot": snapshot,
        "date": snapshot["date"],
        "features": list(features.values()),
        "phases": manifest["stages"],
        "capabilities": [
            [item["title"], item["description"], item["path"]] for item in capabilities
        ],
        "repo": REPOSITORY,
        "batches": sum(not item["baseline"] for item in capabilities),
    }


def counters(items):
    counts = Counter(item["status"] for item in items)
    return {
        "total": len(items),
        "partial": counts["partial"],
        "planned": counts["planned"],
        "complete": counts["complete"],
    }


def snapshot_date(data):
    day = date.fromisoformat(data["date"])
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def render_markdown(data):
    all_items = data["features"]
    named = [f for f in all_items if f["named"]]
    supporting = [f for f in all_items if not f["named"]]
    mvp = [f for f in named if f["stage"] == "MVP"]
    n, a = counters(named), counters(all_items)
    lines = [
        "# Feature overview",
        "",
        f"Snapshot: **{snapshot_date(data)}**, verified merged main [`{data['base'][:7]}`]({REPOSITORY}/commit/{data['base']}) through PR #{data['snapshot']['merged_through_pr']}. This view does not query CI or certify exact-main/host/provider acceptance.",
        "",
        "[Critical review of every feature](FEATURE_REVIEW.md) · [Interactive dashboard — download HTML](FEATURE_DASHBOARD.html) · [Source metadata](FEATURE_PROGRESS.json)",
        "",
        "GitHub renders this Markdown summary. It displays HTML as source: download the dashboard and open the saved `.html` in a browser. No Pages hosting, external dependencies, network requests or browser storage are activated.",
        "",
        "## At a glance",
        "",
        "| Catalog | Full retained contract accepted | Working foundation, partial | Planned / not evidenced | Total |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, items in (
        ("Original named product features", named),
        ("Of those, first-stage MVP", mvp),
        ("Additional supporting references", supporting),
        ("Complete retained register", all_items),
    ):
        c = counters(items)
        lines.append(
            f"| {label} | **{c['complete']}** | **{c['partial']}** | **{c['planned']}** | **{c['total']}** |"
        )
    lines += [
        "",
        f"**{n['partial']} of {n['total']} have working foundations; {n['complete']} full retained feature contracts are accepted.** This is not a percentage of effort or production readiness. A bounded MVP can be accepted before all later expansions of a broad feature finish; its own user-journey gates must actually pass. Planned/not evidenced does not prove no code exists. The additional supporting references overlap product outcomes, not extra independent deliverables.",
        "",
        f"Across all {a['total']} references: {a['partial']} partial and {a['planned']} planned/not evidenced. Review verdicts describe recommendations and never change delivery status or approved scope.",
        "",
        "## Existing version plan",
        "",
        "A feature is counted once at its first stage; later expansions remain retained. FIN-06 starts with basic MVP capture and expands later. FIN-12/15 start with manual research in v0.7 before advanced finance. Installation, research and release gates span stages. These historical stages are not dates or new promises.",
        "",
        "| First stage | Named features | Full retained contract accepted | Partial | Planned / not evidenced |",
        "|---|---:|---:|---:|---:|",
    ]
    for stage, label in data["phases"].items():
        group = [f for f in named if f["stage"] == stage]
        if group:
            c = counters(group)
            lines.append(
                f"| {label} | {c['total']} | {c['complete']} | {c['partial']} | {c['planned']} |"
            )
    lines += [
        "| v1.0 · Supported service | — | — | — | Cross-scope reliability/capacity/maintenance/recovery gates; no new named allocation. |",
        "| v1.1+ · Measured scale | — | — | — | Workers/standby only when measurements justify them. |",
        "| v1.2 | — | — | — | No separate scope allocated; do not invent assignments. |",
        "",
        "## Delivered building blocks",
        "",
        f"{data['batches']} public feature batches have merged after the imported engineering foundation. Documentation PRs are not feature deliveries; building blocks are not added to the original-feature denominator.",
        "",
        "| Evidence | Working engineering subset |",
        "|---|---|",
    ]
    for title, description, path in data["capabilities"]:
        link = f"{REPOSITORY}/{path}" if path.startswith("pull/") else "VALIDATION.md"
        lines.append(f"| [{title}]({link}) | {description} |")
    lines += [
        "",
        "## All original named features",
        "",
        "Statuses come from the [register](FEATURE_REGISTER.md). Review recommendations link to the [individual assessments](FEATURE_REVIEW.md), while [dependencies](FEATURE_DEPENDENCIES.md), [roadmap](../ROADMAP.md) and [MVP acceptance](MVP_ACCEPTANCE.md) retain their authority.",
        "",
    ]
    for stage, label in data["phases"].items():
        group = [f for f in named if f["stage"] == stage]
        if not group:
            continue
        lines += [
            f"### {label}",
            "",
            "| ID | Feature | Merged status | Review recommendation | Remaining acceptance |",
            "|---|---|---|---|---|",
        ]
        for f in group:
            status = (
                "Working foundation · partial"
                if f["status"] == "partial"
                else "Planned / not evidenced"
            )
            lines.append(
                f"| {f['id']} | {f['title']} | {status} | [{f['review']['verdict']}](FEATURE_REVIEW.md#{f['domain'].lower()}) | {f['remaining']} |"
            )
        lines.append("")
    s = counters(supporting)
    lines += [
        "## All supporting references",
        "",
        "These overlap product features and remain fully retained, including INSTALL and RND extensions.",
        "",
        "<details>",
        f"<summary>Show all {s['total']} supporting requirements ({s['partial']} partial, {s['planned']} planned)</summary>",
        "",
        "| ID | Requirement | First stage / gate | Merged status | Review |",
        "|---|---|---|---|---|",
    ]
    for f in supporting:
        lines.append(
            f"| {f['id']} | {f['title']} | {data['phases'][f['stage']]} — {f['milestone']} | {f['status']} | [{f['review']['verdict']}](FEATURE_REVIEW.md#{f['domain'].lower()}) |"
        )
    lines += [
        "",
        "</details>",
        "",
        "## Counting and maintenance contract",
        "",
        "PROJECT_MASTER.md owns stage and gate status, acceptance status and priorities; this overview is a derived view and adds no facts of its own. The register owns retained requirements/evidence; FEATURE_PROGRESS.json is a hand-curated input, not a generated file: it records the verified snapshot (main revision, last merged PR, CI run, register-row fingerprint), first-stage mappings and merged-capability list, and its snapshot revision must equal the revision recorded in PROJECT_MASTER.md; FEATURE_REVIEW.md owns separately labelled recommendations. All IDs must match, and every reference has exactly one review. No review candidate is automatically added to scope.",
        "",
        "After a verified feature merge or approved scope/status/milestone change, reconcile PROJECT_MASTER.md, the register/roadmap and metadata, including the register-row fingerprint. Run `python3 scripts/build_feature_overview.py` and review generated counters, links and first-stage assignments. `--check` verifies reproducibility without writes; `--export-dir PATH` additionally exports standalone HTML/Markdown/JSON outside the repository when requested. Repository policy rejects stale/tampered output, missing/duplicate IDs or unknown completion claims. No CI/network query is performed by generation. Record hosted CI evidence in PR metadata; do not push source solely to add CI proof or refresh a snapshot after a documentation-only merge.",
        "",
        "Changing the generator, template or CI policy remains full CI. Only the exact validated dashboard/metadata paths can join Markdown in documentation-only selection; other new HTML/JSON is unknown/full. Never use green open PRs as merged evidence or turn full retained-scope completion into a prerequisite for every earlier bounded MVP. Private history/profile values remain outside Git.",
        "",
    ]
    return "\n".join(lines)


def render_html(data, template):
    all_items = data["features"]
    named = [f for f in all_items if f["named"]]
    mvp = [f for f in named if f["stage"] == "MVP"]
    values = {
        "__DATA__": json.dumps(data, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026"),
        "__BASE_SHA__": data["base"],
        "__BASE_SHORT__": data["base"][:7],
        "__SNAPSHOT_DATE__": snapshot_date(data),
        "__SNAPSHOT_LABEL__": f"{snapshot_date(data)} · {data['base'][:7]}",
        "__BATCH_COUNT__": data["batches"],
        "__LAST_PR__": data["snapshot"]["merged_through_pr"],
        "__SUPPORT_TOTAL__": len(all_items) - len(named),
        "__REVIEW_COUNT__": len(all_items),
        "__REVIEW_SUMMARY__": ", ".join(
            f"{count} {verdict}"
            for verdict, count in Counter(f["review"]["verdict"] for f in all_items).items()
        ),
    }
    for prefix, items in (("NAMED", named), ("MVP", mvp), ("ALL", all_items)):
        for key, value in counters(items).items():
            values[f"__{prefix}_{key.upper()}__"] = value
    if template.count("__DATA__") != 1:
        raise ValueError("Exactly one escaped data payload is required")

    def substitute(match):
        key = match.group()
        if key not in values:
            raise ValueError(f"Unknown dashboard token: {key}")
        return values[key] if key == "__DATA__" else html.escape(str(values[key]))

    return re.sub(r"__[A-Z_]+__", substitute, template)


def expected_outputs(root=ROOT):
    manifest = json.loads(
        (root / "docs/FEATURE_PROGRESS.json").read_text(), object_pairs_hook=json_pairs
    )
    data = build_data(
        (root / "docs/FEATURE_REGISTER.md").read_text(),
        (root / "docs/FEATURE_REVIEW.md").read_text(),
        manifest,
    )
    template = (root / "scripts/feature_dashboard_template.html").read_text()
    return data, {OUTPUTS[0]: render_markdown(data), OUTPUTS[1]: render_html(data, template)}


def compare_outputs(root, outputs):
    return [
        f"{name}: generated output is missing/stale/tampered; run build_feature_overview.py"
        for name, content in outputs.items()
        if not (root / name).is_file() or (root / name).read_text() != content
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--export-dir", type=Path)
    args = parser.parse_args()
    try:
        data, outputs = expected_outputs()
        if args.check:
            errors = compare_outputs(ROOT, outputs)
            if errors:
                raise ValueError("; ".join(errors))
        else:
            for name, content in outputs.items():
                (ROOT / name).write_text(content)
        if args.export_dir:
            if args.check:
                raise ValueError("Export is a write operation; do not combine with --check")
            args.export_dir.mkdir(parents=True, exist_ok=True)
            (args.export_dir / "Butler-Feature-Dashboard.html").write_text(outputs[OUTPUTS[1]])
            exported = re.sub(
                r"\]\(([^)]+)\)",
                lambda m: (
                    m.group()
                    if "://" in m.group(1)
                    else f"]({REPOSITORY}/blob/main/{m.group(1)[3:] if m.group(1).startswith('../') else 'docs/' + m.group(1)})"
                ),
                outputs[OUTPUTS[0]],
            )
            (args.export_dir / "Butler-Feature-Overview.md").write_text(exported)
            (args.export_dir / "Butler-Feature-Overview.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            )
        print(
            f"Feature overview verified: {len(data['features'])} references; {sum(f['named'] for f in data['features'])} named; {len(data['features'])} individual reviews"
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Feature overview: {exc}\n")


if __name__ == "__main__":
    main()
