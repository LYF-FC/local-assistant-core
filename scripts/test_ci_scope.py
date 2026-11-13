"""Policy and actual Git rename/comparison coverage; no network or application data."""

import copy
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_feature_overview as overview
import check_repository
import ci_gate
import ci_scope
import yaml


class ScopeTests(unittest.TestCase):
    def assert_jobs(self, result, enabled):
        self.assertEqual({job for job in ci_scope.JOBS if result[job]}, set(enabled))

    def test_documentation_has_only_always_running_policy_checks(self):
        self.assert_jobs(
            ci_scope.classify(
                ["README.md", "docs/SCOPE.md", "specs/048-document-library/plan.md"]
            ),
            [],
        )

    @staticmethod
    def overview_fixture():
        register = (
            "| CORE-01 | Identity: explicit scoped identities | MVP | partial; spec001 | Full contract open |\n"
            "| CORE-02 | Memory: sourced confirmed facts | MVP | planned | Acceptance not evidenced |\n"
            "| MVP-01 | Daily loop: complete everyday acceptance | MVP | planned | Acceptance not evidenced |"
        )
        critique = "Retain this outcome while specifying current authority, provenance, review, correction and the independent acceptance boundary before activation."
        review = "\n".join(f"| {identifier} | Keep | {critique} |" for identifier in ("CORE-01", "CORE-02", "MVP-01"))
        manifest = {
            "schema_version": 1,
            "snapshot": {"date": "2026-11-09", "main_sha": "a" * 40, "merged_through_pr": 1, "register_rows_sha256": overview.fingerprint(register)},
            "stages": {"MVP": "MVP"},
            "first_stage": {identifier: "MVP" for identifier in ("CORE-01", "CORE-02", "MVP-01")},
            "named_ids": ["CORE-01", "CORE-02"],
            "capabilities": [{"title": "Synthetic baseline", "description": "Synthetic engineering", "path": "docs/VALIDATION.md", "baseline": True}],
            "open_batches": [],
        }
        return register, review, manifest

    def test_only_verified_static_dashboard_paths_are_documentation(self):
        self.assert_jobs(ci_scope.classify([*ci_scope.GENERATED_DOCS, "docs/FEATURE_REVIEW.md"]), [])
        for path in ("docs/other.html", "docs/FEATURE_PROGRESS_other.json", "scripts/build_feature_overview.py", "scripts/feature_dashboard_template.html", "scripts/check_repository.py"):
            with self.subTest(path=path):
                self.assert_jobs(ci_scope.classify([path]), ci_scope.JOBS)

    def test_every_scope_reference_needs_exactly_one_critical_review(self):
        register, review, manifest = self.overview_fixture()
        for invalid in ("\n".join(review.splitlines()[:-1]), review + "\n" + review.splitlines()[0]):
            with self.subTest(review=invalid), self.assertRaises(ValueError):
                overview.build_data(register, invalid, manifest)

    def test_unsupported_completion_claim_and_stale_snapshot_fail_closed(self):
        register, review, manifest = self.overview_fixture()
        unsupported = register.replace("partial; spec001", "complete; spec001")
        changed = copy.deepcopy(manifest)
        changed["snapshot"]["register_rows_sha256"] = overview.fingerprint(unsupported)
        with self.assertRaisesRegex(ValueError, "Unrecognized status"):
            overview.build_data(unsupported, review, changed)
        changed["snapshot"]["register_rows_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            overview.build_data(register, review, changed)

    def test_stage_and_original_feature_cohort_cannot_silently_omit_ids(self):
        register, review, manifest = self.overview_fixture()
        missing_stage = copy.deepcopy(manifest)
        del missing_stage["first_stage"]["MVP-01"]
        duplicate_named = copy.deepcopy(manifest)
        duplicate_named["named_ids"] = ["CORE-01", "CORE-01"]
        for invalid in (missing_stage, duplicate_named):
            with self.subTest(metadata=invalid), self.assertRaises(ValueError):
                overview.build_data(register, review, invalid)

    def test_source_text_is_escaped_data_not_dashboard_script(self):
        data = overview.build_data(*self.overview_fixture())
        self.assertEqual(overview.counters([f for f in data["features"] if f["named"]]), {"total": 2, "partial": 1, "planned": 1, "complete": 0})
        payload = "</script><script>untrusted-source-is-not-authority</script>"
        data["features"][0]["requirement"] = payload
        rendered = overview.render_html(data, '<script type="application/json">__DATA__</script>')
        self.assertNotIn(payload, rendered)
        self.assertIn("\\u003c/script\\u003e", rendered)

    def test_generated_dashboard_tampering_is_rejected_without_execution(self):
        _, outputs = overview.expected_outputs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in outputs.items():
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(text)
            self.assertEqual(overview.compare_outputs(root, outputs), [])
            target = root / "docs/FEATURE_DASHBOARD.html"
            target.write_text(target.read_text() + "<script>unreviewed-rendering-code</script>")
            failures = overview.compare_outputs(root, outputs)
            self.assertEqual(len(failures), 1)
            self.assertIn("tampered", failures[0])

    def test_interface_keeps_build_client_and_full_browser_container_coverage(self):
        for path in [
            "frontend/src/api.ts",
            "frontend/src/DocumentsPanel.tsx",
            "frontend/src/styles.css",
            "frontend/src/image.svg",
            "frontend/e2e/documents.spec.ts",
            *sorted(ci_scope.FRONTEND_FILES),
        ]:
            with self.subTest(path=path):
                self.assert_jobs(
                    ci_scope.classify([path, "ROADMAP.md"]), ["frontend", "containers"]
                )

    def test_critical_and_unknown_changes_fail_closed_to_all_jobs(self):
        for path in [
            "backend/app/identity.py",
            "backend/app/documents.py",
            "backend/app/models.py",
            "backend/tests/conftest.py",
            "backend/alembic/versions/0022_document_library.py",
            "backend/uv.lock",
            ".github/workflows/ci.yml",
            "infra/core/Caddyfile",
            "scripts/browser-fixtures.py",
            "scripts/ci_scope.py",
            "Makefile",
            "AGENTS.md",
            ".specify/memory/constitution.md",
            "new-module/file.py",
            "docs/image.svg",
            "docs/../backend/app/auth_routes.py",
            "/README.md",
            "docs//README.md",
        ]:
            with self.subTest(path=path):
                self.assert_jobs(ci_scope.classify(["README.md", path]), ci_scope.JOBS)

    def test_empty_path_set_cannot_skip_jobs(self):
        self.assert_jobs(ci_scope.classify([]), ci_scope.JOBS)

    def test_scheduled_manual_and_unknown_events_are_full(self):
        for event in [
            "schedule",
            "workflow_dispatch",
            "",
            "pull_request_target",
            "unexpected",
        ]:
            with (
                self.subTest(event=event),
                patch.object(ci_scope.subprocess, "run") as run,
            ):
                self.assert_jobs(ci_scope.determine(event, "", ""), ci_scope.JOBS)
                run.assert_not_called()

    def test_bad_identifiers_do_not_become_command_arguments(self):
        with patch.object(ci_scope.subprocess, "run") as run:
            for value in ["", "--output=/tmp/x", "$(false)", "main", "a" * 39]:
                self.assert_jobs(
                    ci_scope.determine("pull_request", value, "a" * 40), ci_scope.JOBS
                )
            run.assert_not_called()

    def test_comparison_failure_runs_every_job(self):
        with patch.object(
            ci_scope.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, ["git"]),
        ):
            self.assert_jobs(
                ci_scope.determine("pull_request", "a" * 40, "b" * 40), ci_scope.JOBS
            )

    def test_real_git_diff_includes_deleted_source_when_renamed_to_docs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(
                    ["git", *args], cwd=root, text=True
                ).strip()

            git("init", "-q")
            git("config", "user.name", "Synthetic CI policy")
            git("config", "user.email", "synthetic@example.invalid")
            (root / "backend").mkdir()
            (root / "backend/source.py").write_text("Synthetic unchanged content\n")
            git("add", ".")
            git("commit", "-qm", "Synthetic baseline")
            base = git("rev-parse", "HEAD")
            (root / "docs").mkdir()
            git("mv", "backend/source.py", "docs/source.md")
            git("commit", "-qm", "Synthetic rename")
            self.assert_jobs(
                ci_scope.determine(
                    "pull_request", base, git("rev-parse", "HEAD"), root=root
                ),
                ci_scope.JOBS,
            )
            (root / "README.md").write_text("Synthetic documentation\n")
            git("add", ".")
            base = git("rev-parse", "HEAD")
            git("commit", "-qm", "Synthetic docs")
            self.assert_jobs(
                ci_scope.determine(
                    "pull_request", base, git("rev-parse", "HEAD"), root=root
                ),
                [],
            )
            self.assert_jobs(
                ci_scope.determine("push", base, git("rev-parse", "HEAD"), root=root),
                [],
            )

    def test_output_never_calls_unselected_jobs_passed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "outputs"
            summary = Path(directory) / "summary"
            with (
                patch.dict(
                    os.environ,
                    {
                        "BUTLER_CI_EVENT": "pull_request",
                        "BUTLER_CI_BASE_SHA": "a" * 40,
                        "BUTLER_CI_HEAD_SHA": "b" * 40,
                        "GITHUB_OUTPUT": str(output),
                        "GITHUB_STEP_SUMMARY": str(summary),
                    },
                ),
                patch.object(
                    ci_scope, "determine", return_value=ci_scope.classify(["README.md"])
                ),
            ):
                ci_scope.main()
            self.assertIn("postgres=false", output.read_text())
            self.assertIn("not test-pass evidence", summary.read_text())


class GateTests(unittest.TestCase):
    def results(self, mode):
        required = ci_gate.REQUIRED[mode]
        return {
            "scope": {
                "result": "success",
                "outputs": {
                    "mode": mode,
                    **{job: str(job in required).lower() for job in ci_gate.JOBS},
                },
            },
            **{
                job: {"result": "success" if job in required else "skipped"}
                for job in ci_gate.JOBS
            },
        }

    def test_each_explicit_profile_has_the_expected_gate(self):
        for mode in ci_gate.REQUIRED:
            self.assertEqual(ci_gate.verify(self.results(mode)), mode)

    def test_failed_missing_cancelled_and_inconsistent_evidence_is_refused(self):
        for mode in ci_gate.REQUIRED:
            for job in ["scope", *ci_gate.JOBS]:
                for result in ["failure", "cancelled", "timed_out", "missing"]:
                    with self.subTest(mode=mode, job=job, result=result):
                        value = self.results(mode)
                        if result == "missing":
                            del value[job]
                        else:
                            value[job]["result"] = result
                        with self.assertRaises(ValueError):
                            ci_gate.verify(value)
            value = self.results(mode)
            value["scope"]["outputs"]["postgres"] = "unexpected"
            with self.assertRaises(ValueError):
                ci_gate.verify(value)
        for value in [{}, {"scope": {"result": "success", "outputs": {}}}]:
            with self.assertRaises(ValueError):
                ci_gate.verify(value)

    def test_workflow_wires_conditions_and_always_running_gate_without_event_path_skips(
        self,
    ):
        workflow = yaml.safe_load(
            (ci_scope.ROOT / ".github/workflows/ci.yml").read_text()
        )
        events = workflow.get("on", workflow.get(True))
        for event in ["push", "pull_request"]:
            config = events[event]
            self.assertFalse(config and ("paths" in config or "paths-ignore" in config))
        jobs = workflow["jobs"]
        self.assertNotIn("if", jobs["scope"])
        self.assertEqual(set(jobs["ci"]["needs"]), {"scope", *ci_gate.JOBS})
        self.assertEqual(jobs["ci"]["if"], "${{ always() }}")
        for job in ci_gate.JOBS:
            self.assertEqual(jobs[job]["needs"], "scope")
            self.assertEqual(
                jobs[job]["if"], "${{ needs.scope.outputs." + job + " == 'true' }}"
            )
            self.assertNotIn("continue-on-error", jobs[job])
        for job in jobs.values():
            self.assertNotIn("continue-on-error", job)
            for step in job.get("steps", []):
                self.assertNotIn("continue-on-error", step)
        self.assertEqual(jobs["postgres"]["timeout-minutes"], 20)
        self.assertTrue(
            any(
                "test-db-restore.sh" in step.get("run", "")
                for step in jobs["postgres"]["steps"]
            )
        )


class EconomyTests(unittest.TestCase):
    def test_dependency_groups_keep_weekly_minor_patch_review_without_ignoring_updates(
        self,
    ):
        config = yaml.safe_load((ci_scope.ROOT / ".github/dependabot.yml").read_text())
        self.assertEqual(len(config["updates"]), 5)
        for update in config["updates"]:
            self.assertEqual(update["schedule"], {"interval": "weekly"})
            self.assertNotIn("ignore", update)
            self.assertNotIn("allow", update)
            groups = update["groups"]
            self.assertEqual(len(groups), 1)
            group = next(iter(groups.values()))
            self.assertEqual(group["patterns"], ["*"])
            self.assertEqual(set(group["update-types"]), {"minor", "patch"})
            self.assertNotIn("applies-to", group)

    def test_dependency_cache_and_screenshot_retention_are_bounded(self):
        workflow = yaml.safe_load(
            (ci_scope.ROOT / ".github/workflows/ci.yml").read_text()
        )
        for name in ["frontend", "containers"]:
            step = next(
                step
                for step in workflow["jobs"][name]["steps"]
                if step.get("uses", "").startswith("actions/setup-node@")
            )
            self.assertEqual(step["with"]["cache"], "npm")
            self.assertEqual(
                step["with"]["cache-dependency-path"], "frontend/package-lock.json"
            )
        artifact = next(
            step
            for step in workflow["jobs"]["containers"]["steps"]
            if step.get("uses", "").startswith("actions/upload-artifact@")
        )
        self.assertEqual(artifact["with"]["retention-days"], 1)


class MasterTests(unittest.TestCase):
    SHA = "a" * 40

    def tree(self, master=None, sha=None, register=None, roadmap="[ok](PROJECT_MASTER.md)"):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        (root / "docs").mkdir()
        gates = " ".join(f"MVP-0{n}" for n in range(1, 6))
        master = master if master is not None else f"revision `{self.SHA}` {gates} CORE-01 [register](docs/FEATURE_REGISTER.md)"
        (root / "PROJECT_MASTER.md").write_text(master)
        (root / "ROADMAP.md").write_text(roadmap)
        rows = register or "".join(f"| {i} | x |\n" for i in ("CORE-01", *gates.split()))
        (root / "docs/FEATURE_REGISTER.md").write_text(rows)
        (root / "docs/FEATURE_PROGRESS.json").write_text('{"snapshot": {"main_sha": "%s"}}' % (sha or self.SHA))
        return root

    def test_consistent_master_passes(self):
        self.assertEqual(check_repository.check_master(self.tree()), [])

    def test_master_is_documentation_only_for_ci_selection(self):
        self.assertEqual({j for j in ci_scope.JOBS if ci_scope.classify(["PROJECT_MASTER.md"])[j]}, set())

    def test_missing_master_snapshot_mismatch_unknown_id_unmapped_gate_and_broken_link_fail(self):
        gates = " ".join(f"MVP-0{n}" for n in range(1, 6))
        missing = self.tree()
        (missing / "PROJECT_MASTER.md").unlink()
        self.assertIn("missing", check_repository.check_master(missing)[0])
        self.assertTrue(any("snapshot" in e for e in check_repository.check_master(self.tree(sha="b" * 40))))
        unknown = self.tree(master=f"revision `{self.SHA}` {gates} CORE-99")
        self.assertTrue(any("CORE-99" in e for e in check_repository.check_master(unknown)))
        unmapped = self.tree(master=f"revision `{self.SHA}` MVP-01 MVP-02 MVP-03 MVP-04")
        self.assertTrue(any("MVP-05" in e for e in check_repository.check_master(unmapped)))
        broken = self.tree(roadmap="[x](docs/NOPE.md)")
        self.assertTrue(any("broken relative link" in e for e in check_repository.check_master(broken)))


if __name__ == "__main__":
    unittest.main()
