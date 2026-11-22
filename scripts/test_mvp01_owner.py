"""Safeguard tests for scripts/mvp01-owner.sh (spec 076) with a fake `docker`; no Docker, network or data.

The script is copied into a temporary repository-shaped directory so the real `.local` state is never
touched. The fake docker records every call, answers the few queries the script makes and fails the test if
any removal-style call appears outside the exact, confirmed reset.
"""

import json
import os
import shutil
import socket
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = "local-assistant-core-mvp01-owner"
SHIM = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_DOCKER_LOG"], "a") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
a = sys.argv[1:]
if a[:1] == ["info"]:
    sys.exit(0)
if a[:2] == ["network", "ls"]:
    print("\\n".join(n["Id"] for n in json.loads(os.environ.get("FAKE_NETWORKS", "[]"))))
elif a[:2] == ["network", "inspect"]:
    print(os.environ.get("FAKE_NETWORKS", "[]"))
elif a[:2] == ["volume", "ls"]:
    print(os.environ.get("FAKE_VOLUMES", ""))
elif a[:1] == ["ps"]:
    print(os.environ.get("FAKE_CONTAINERS", ""))
elif a[:1] == ["compose"]:
    if "up" in a and os.environ.get("FAKE_UP_FAILS") == "1":
        sys.exit(1)
    if "ps" in a and "-q" in a:
        print(os.environ.get("FAKE_RUNNING", ""))
sys.exit(0)
"""
REMOVAL = ("prune", " rm ", "rmi", " kill", " stop", "volume rm", "network rm", "system ")


class OwnerScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "scripts" / "mvp01-owner-fixtures").mkdir(parents=True)
        shutil.copy(REPO / "scripts" / "mvp01-owner.sh", self.tmp / "scripts")
        shutil.copy(REPO / "scripts" / "mvp01-owner-fixtures" / "invoice.eml", self.tmp / "scripts" / "mvp01-owner-fixtures")
        (self.tmp / "bin").mkdir()
        docker = self.tmp / "bin" / "docker"
        docker.write_text(SHIM)
        docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
        # An isolated throwaway repository: the script only reads its revision; the real repository is never used.
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "synthetic"], cwd=self.tmp, check=True, capture_output=True)
        self.log = self.tmp / "docker.log"
        self.log.write_text("")
        self.state = self.tmp / ".local" / "mvp01-owner"

    def require_free_ports(self):
        # Preflight checks the real loopback ports before the (faked) Docker networks; a running rehearsal on this
        # host legitimately holds them, so those cases are skipped rather than disturbed.
        for port in (18081, 18444):
            with socket.socket() as probe:
                probe.settimeout(1)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    self.skipTest(f"loopback port {port} is in use on this host")

    def run_script(self, *args, extra=None, stdin=subprocess.DEVNULL):
        env = {
            "PATH": f"{self.tmp / 'bin'}:{os.environ['PATH']}",
            "HOME": str(self.tmp),
            "FAKE_DOCKER_LOG": str(self.log),
            **(extra or {}),
        }
        return subprocess.run(
            ["bash", str(self.tmp / "scripts" / "mvp01-owner.sh"), *args],
            capture_output=True, text=True, env=env, stdin=stdin, timeout=60, check=False,
        )

    def calls(self):
        return self.log.read_text().splitlines()

    def assert_nothing_removed(self):
        for call in self.calls():
            self.assertFalse(any(word in f" {call} " for word in REMOVAL), call)

    def config(self, **changes):
        self.state.mkdir(parents=True, mode=0o700)
        values = {
            "BUTLER_ENV": "test", "BUTLER_POSTGRES_DB": "butler_test_mvp01_owner", "BUTLER_POSTGRES_USER": "butler",
            "BUTLER_POSTGRES_PASSWORD": "a" * 64, "BUTLER_RUNTIME_PASSWORD": "b" * 64, "BUTLER_HTTP_PORT": "18081",
            "BUTLER_HTTPS_PORT": "18444", "BUTLER_AUTH_ORIGIN": "https://localhost:18444",
            "BUTLER_SPEECH_ENABLED": "false", "BUTLER_MVP01_MARKER": "synthetic-rehearsal-0123456789abcdef",
        }
        values.update(changes)
        env = self.state / "mvp01-owner.env"
        env.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
        env.chmod(0o600)

    def network(self, name, subnet, project=None):
        return json.dumps([{"Id": "n1", "Name": name, "Labels": {"com.docker.compose.project": project} if project else {}, "IPAM": {"Config": [{"Subnet": subnet}]}}])

    def test_subnet_collision_is_refused_naming_the_environment_and_stopping_nothing(self):
        self.require_free_ports()
        result = self.run_script("start", extra={"FAKE_NETWORKS": self.network("butler-poc_app", "172.29.243.0/28", "butler-poc")})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("butler-poc_app", result.stderr)
        self.assertIn("butler-poc", result.stderr)
        self.assertIn("Nothing was stopped or removed", result.stderr)
        self.assertIn("WITHOUT -v", result.stderr)
        self.assertIn("docker compose -p butler-poc down", result.stderr)
        self.assert_nothing_removed()
        self.assertFalse(any(" up " in f" {c} " for c in self.calls()))

    def test_overlapping_larger_foreign_network_is_also_refused(self):
        self.require_free_ports()
        result = self.run_script("start", extra={"FAKE_NETWORKS": self.network("vpn", "172.29.0.0/16")})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("vpn", result.stderr)

    def test_unrelated_subnet_passes_preflight_and_reaches_the_build(self):
        self.require_free_ports()
        result = self.run_script("start", extra={"FAKE_NETWORKS": self.network("other", "172.29.244.0/28", "other"), "FAKE_UP_FAILS": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any("compose" in c and " up -d --build" in c for c in self.calls()), self.calls())
        self.assertTrue(any(f"-p {PROJECT}" in c for c in self.calls() if "compose" in c))
        self.assert_nothing_removed()

    def test_busy_loopback_port_is_refused(self):
        sock = socket.socket()
        try:
            sock.bind(("127.0.0.1", 18081))
        except OSError:
            self.skipTest("loopback port 18081 is already in use on this host")
        sock.listen(1)
        try:
            result = self.run_script("start")
        finally:
            sock.close()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("18081", result.stderr)
        self.assertIn("nothing was stopped", result.stderr)
        self.assert_nothing_removed()

    def test_existing_volumes_without_generated_config_are_not_adopted(self):
        result = self.run_script("start", extra={"FAKE_VOLUMES": f"{PROJECT}_postgres_data"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reset", result.stderr)
        self.assertFalse((self.state / "mvp01-owner.env").exists())

    def test_generated_config_has_private_mode_distinct_secrets_and_exact_names(self):
        self.run_script("start", extra={"FAKE_UP_FAILS": "1"})
        env = self.state / "mvp01-owner.env"
        self.assertEqual(stat.S_IMODE(env.stat().st_mode), 0o600)
        values = dict(line.split("=", 1) for line in env.read_text().splitlines())
        self.assertEqual(values["BUTLER_POSTGRES_DB"], "butler_test_mvp01_owner")
        self.assertEqual(values["BUTLER_AUTH_ORIGIN"], "https://localhost:18444")
        self.assertNotEqual(values["BUTLER_POSTGRES_PASSWORD"], values["BUTLER_RUNTIME_PASSWORD"])
        self.assertGreaterEqual(len(values["BUTLER_POSTGRES_PASSWORD"]), 32)
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o700)

    def test_tampered_config_is_refused(self):
        for key, value in (("BUTLER_POSTGRES_DB", "butler"), ("BUTLER_HTTPS_PORT", "8443"), ("BUTLER_ENV", "development"), ("BUTLER_MVP01_MARKER", "x")):
            with self.subTest(key=key):
                shutil.rmtree(self.state, ignore_errors=True)
                self.config(**{key: value})
                result = self.run_script("stop")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(" down" in c for c in self.calls()))

    def test_reset_without_config_or_confirmation_deletes_nothing(self):
        result = self.run_script("reset")
        self.assertNotEqual(result.returncode, 0)
        self.config()
        for extra in ({}, {"BUTLER_MVP01_RESET_CONFIRM": "local-assistant-core-dev"}, {"BUTLER_MVP01_RESET_CONFIRM": PROJECT + "-x"}):
            result = self.run_script("reset", extra=extra)
            self.assertNotEqual(result.returncode, 0, extra)
            self.assertTrue(self.state.exists())
        self.assertFalse(any(" down" in c for c in self.calls()))
        self.assert_nothing_removed()

    def test_reset_refuses_a_volume_outside_the_project_prefix(self):
        self.config()
        result = self.run_script("reset", extra={"FAKE_VOLUMES": "someone_else_data", "BUTLER_MVP01_RESET_CONFIRM": PROJECT})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not prefixed", result.stderr)
        self.assertFalse(any(" down" in c for c in self.calls()))

    def test_confirmed_reset_removes_only_the_named_project_and_its_local_state(self):
        self.config()
        result = self.run_script("reset", extra={"FAKE_VOLUMES": f"{PROJECT}_postgres_data\n{PROJECT}_synthetic_filing", "BUTLER_MVP01_RESET_CONFIRM": PROJECT})
        self.assertEqual(result.returncode, 0, result.stderr)
        downs = [c for c in self.calls() if " down" in c]
        self.assertEqual(len(downs), 1)
        self.assertIn(f"-p {PROJECT}", downs[0])
        self.assertIn("down -v --remove-orphans", downs[0])
        for call in self.calls():
            self.assertFalse(any(word in f" {call} " for word in ("prune", "rmi", "volume rm", "network rm", "system ")), call)
        self.assertFalse(self.state.exists())

    def test_start_refusal_for_orphaned_volumes_is_recoverable_by_a_confirmed_reset(self):
        volumes = f"{PROJECT}_postgres_data\n{PROJECT}_synthetic_filing"
        refused = self.run_script("start", extra={"FAKE_VOLUMES": volumes})
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("reset", refused.stderr)
        self.assertIn("ANOTHER checkout", refused.stderr)
        self.assertFalse(self.state.joinpath("mvp01-owner.env").exists())
        # The exact recovery the message promises: reset works without the generated config...
        wrong = self.run_script("reset", extra={"FAKE_VOLUMES": volumes, "BUTLER_MVP01_RESET_CONFIRM": "nope"})
        self.assertNotEqual(wrong.returncode, 0)
        self.assertFalse(any(" down" in c for c in self.calls()))
        done = self.run_script("reset", extra={"FAKE_VOLUMES": volumes, "BUTLER_MVP01_RESET_CONFIRM": PROJECT})
        self.assertEqual(done.returncode, 0, done.stderr)
        downs = [c for c in self.calls() if " down" in c]
        self.assertEqual(len(downs), 1)
        # ...and only for the exact project, scoped by name, with no other removal-style call.
        self.assertIn(f"-p {PROJECT}", downs[0])
        self.assertIn("down -v --remove-orphans", downs[0])
        self.assertIn("--env-file /dev/null", downs[0])
        for call in self.calls():
            self.assertFalse(any(word in f" {call} " for word in ("prune", "rmi", "volume rm", "network rm", "system ")), call)
        self.assertFalse(self.state.exists())

    def test_reset_without_config_refuses_foreign_volumes_and_empty_environments(self):
        empty = self.run_script("reset", extra={"BUTLER_MVP01_RESET_CONFIRM": PROJECT})
        self.assertNotEqual(empty.returncode, 0)
        self.assertIn("nothing to reset", empty.stderr)
        foreign = self.run_script("reset", extra={"FAKE_VOLUMES": "butler-poc_postgres_data", "BUTLER_MVP01_RESET_CONFIRM": PROJECT})
        self.assertNotEqual(foreign.returncode, 0)
        self.assertIn("not prefixed", foreign.stderr)
        self.assertFalse(any(" down" in c for c in self.calls()))

    def ledger_controls(self):
        return [c for c in self.calls() if "synthetic_ledger control" in c]

    def test_outage_on_composes_only_existing_controls_and_off_removes_them(self):
        self.config()
        on = self.run_script("outage", "on", extra={"FAKE_RUNNING": "caddy"})
        self.assertEqual(on.returncode, 0, on.stderr)
        self.assertTrue((self.state / "outage.on").exists())
        self.assertEqual(len(self.ledger_controls()), 2)
        self.assertTrue(any("lookup-unavailable on" in c for c in self.ledger_controls()))
        self.assertTrue(any("timeout-before-effect on" in c for c in self.ledger_controls()))
        self.assertTrue(any(" stop synthetic_answer_model" in c for c in self.calls()))
        self.assertIn("SIMULATED", on.stdout)
        off = self.run_script("outage", "off", extra={"FAKE_RUNNING": "caddy"})
        self.assertEqual(off.returncode, 0, off.stderr)
        self.assertFalse((self.state / "outage.on").exists())
        self.assertTrue(any("lookup-unavailable off" in c for c in self.ledger_controls()))
        self.assertTrue(any(" start synthetic_answer_model" in c for c in self.calls()))
        self.assert_nothing_removed_except_the_model_stop()

    def assert_nothing_removed_except_the_model_stop(self):
        for call in self.calls():
            if " stop synthetic_answer_model" in call:
                continue
            self.assertFalse(any(word in f" {call} " for word in REMOVAL), call)

    def test_outage_needs_a_running_stack_and_a_valid_argument(self):
        self.config()
        self.assertNotEqual(self.run_script("outage", "on").returncode, 0)  # not running
        self.assertFalse((self.state / "outage.on").exists())
        bad = self.run_script("outage", "sideways", extra={"FAKE_RUNNING": "caddy"})
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(self.ledger_controls(), [])

    def test_a_restart_keeps_the_answer_model_stopped_while_the_outage_flag_is_set(self):
        self.config()
        self.state.joinpath("outage.on").write_text("")
        curl = self.tmp / "bin" / "curl"  # the TLS check itself is covered live; here only the sequencing matters
        curl.write_text("#!/bin/sh\nexit 0\n")
        curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
        result = self.run_script("restart", "--kill", extra={"FAKE_RUNNING": "caddy"})
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        last_up = max(i for i, c in enumerate(calls) if " up -d" in c)
        self.assertTrue(any(" stop synthetic_answer_model" in c for c in calls[last_up:]), calls)
        self.assertIn("outage is still ON", result.stdout)

    def test_second_fixture_checksum_is_published_and_matches_the_file(self):
        import hashlib

        data = (REPO / "scripts" / "mvp01-owner-fixtures" / "invoice-002.eml").read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        text = (REPO / "scripts" / "mvp01-owner.sh").read_text()
        self.assertIn(f'EXPECTED_SHA2="{digest}"', text)
        self.assertIn(b"Message-ID: <mvp01-outage-002@example.invalid>", data)
        self.assertIn(b"invoice-MVP01-2026-002.txt", data)

    def test_scenario_and_usage_reject_unknown_input(self):
        self.assertEqual(self.run_script().returncode, 2)
        self.assertEqual(self.run_script("explode").returncode, 2)
        self.config()
        result = self.run_script("scenario", "wipe-everything", extra={"FAKE_RUNNING": "abc"})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("exec" in c for c in self.calls()))


if __name__ == "__main__":
    unittest.main()
