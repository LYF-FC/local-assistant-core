"""Exercise first-run orchestration without a daemon, network, models or host trust."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_first_run_exports_and_verifies_custom_public_ca_without_model_probe(tmp_path):
    root = Path(__file__).resolve().parents[2]
    checkout = tmp_path / "synthetic-checkout"
    scripts = checkout / "scripts"
    scripts.mkdir(parents=True)
    for name in ("first-run.sh", "export-dev-ca.sh"):
        shutil.copyfile(root / "scripts" / name, scripts / name)
    config = (
        "BUTLER_POSTGRES_PASSWORD=synthetic-migration-only\n"
        "BUTLER_RUNTIME_PASSWORD=synthetic-runtime-only\n"
        "BUTLER_HTTP_PORT=8080\nBUTLER_HTTPS_PORT=8443\n"
    )
    (checkout / ".env").write_text(config)
    binaries = tmp_path / "synthetic-bin"
    binaries.mkdir()
    log = tmp_path / "synthetic-calls.jsonl"
    public_ca = tmp_path / "public CA with spaces" / "root.crt"
    mock = (
        f"#!{sys.executable}\n"
        + """import json, os, sys
from pathlib import Path
command, args = Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ["BUTLER_SETUP_CALL_LOG"], "a") as stream:
    stream.write(json.dumps({"command": command, "args": args}) + "\\n")
if command == "docker" and "cp" in args:
    Path(args[-1]).write_text("Synthetic public certificate only")
if command == "curl" and "--cacert" in args:
    assert Path(args[args.index("--cacert") + 1]).is_file()
if command == "curl" and any("11434" in arg for arg in args):
    sys.exit(99)
if command == "openssl":
    print("Synthetic public subject / SHA256 fingerprint")
"""
    )
    for name in ("docker", "curl", "openssl"):
        path = binaries / name
        path.write_text(mock)
        path.chmod(0o700)
    environment = dict(
        os.environ,
        PATH=str(binaries) + os.pathsep + os.environ["PATH"],
        BUTLER_LOCAL_CA_FILE=str(public_ca),
        BUTLER_SETUP_CALL_LOG=str(log),
        COMPOSE_PROJECT_NAME="butler-synthetic-helper-test",
    )
    result = subprocess.run(
        ["bash", str(scripts / "first-run.sh")],
        cwd=checkout,
        env=environment,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (checkout / ".env").read_text() == config
    assert public_ca.read_text() == "Synthetic public certificate only"
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    copies = [call for call in calls if call["command"] == "docker" and "cp" in call["args"]]
    assert len(copies) == 1 and copies[0]["args"][-1] == str(public_ca)
    tls = [call for call in calls if call["command"] == "curl" and "--cacert" in call["args"]]
    assert len(tls) == 1
    assert tls[0]["args"][tls[0]["args"].index("--cacert") + 1] == str(public_ca)
    assert all("11434" not in str(call) for call in calls)
    assert "manual private Discovery" in result.stdout
    assert "not production-ready" in result.stdout
    assert "synthetic-migration-only" not in result.stdout + result.stderr
