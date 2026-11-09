"""Offline repository invariants. Not a substitute for a full secret scanner."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def check(root: Path = ROOT) -> list[str]:
    errors = []
    for path in (root / ".github/workflows").glob("*.yml"):
        text = path.read_text()
        if "pull_request_target" in text or "self-hosted" in text:
            errors.append(f"{path.name}: unsafe workflow trust boundary")
        for action in re.findall(r"uses:\s*(\S+)", text):
            if not re.fullmatch(r"[\w./-]+@[a-f0-9]{40}", action):
                errors.append(f"{path.name}: action must use a full SHA: {action}")
        document = yaml.safe_load(text)
        if document.get("permissions") != {"contents": "read"}:
            errors.append(f"{path.name}: default token must be read-only")
    compose = yaml.safe_load((root / "infra/core/compose.yml").read_text())
    if "ports" in compose["services"]["postgres"]:
        errors.append("database must not publish a host port")
    for port in compose["services"]["caddy"]["ports"]:
        if not port.startswith("127.0.0.1:"):
            errors.append("foundation entry must bind loopback")
    for service in ("api", "web", "migrate", "role_setup"):
        config = compose["services"][service]
        if not config.get("read_only") or "ALL" not in config.get("cap_drop", []):
            errors.append(f"{service}: read-only root and dropped capabilities required")
    for name, config in compose["services"].items():
        if name != "caddy" and "ingress" in config.get("networks", []):
            errors.append(f"{name}: only Caddy may use ingress")
    api_env = compose["services"]["api"]["environment"]
    if api_env.get("BUTLER_POSTGRES_USER") != "butler_runtime" or "BUTLER_RUNTIME_PASSWORD" not in api_env.get("BUTLER_POSTGRES_PASSWORD", ""):
        errors.append("API must use separate restricted runtime credentials")
    if compose["services"]["api"]["depends_on"].get("role_setup", {}).get("condition") != "service_completed_successfully":
        errors.append("API must wait for restricted-role setup")
    command = compose["services"]["api"].get("command", [])
    if "--forwarded-allow-ips" not in command or command[command.index("--forwarded-allow-ips") + 1] != "172.29.243.2":
        errors.append("API must trust only the fixed Caddy proxy address")
    proxy_networks = compose["services"]["caddy"]["networks"]
    if not isinstance(proxy_networks, dict) or proxy_networks.get("app", {}).get("ipv4_address") != "172.29.243.2":
        errors.append("Caddy must use the fixed trusted app-network address")
    if compose["networks"]["app"].get("ipam", {}).get("config") != [{"subnet": "172.29.243.0/28", "ip_range": "172.29.243.8/29"}]:
        errors.append("Proxy app network must use the isolated reviewed subnet")
    # Scan only source-controlled candidates; runtime environments are intentionally excluded.
    import subprocess
    paths = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=root, text=True).splitlines()
    secret_patterns = [r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", r"(?:sk-proj-|github_pat_)[A-Za-z0-9_-]{24,}"]
    for name in paths:
        path = root / name
        if not path.is_file():
            continue
        if name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            errors.append(f"{name}: real environment file in source")
        text = path.read_text(errors="replace")
        if any(re.search(pattern, text) for pattern in secret_patterns):
            errors.append(f"{name}: possible private credential")
    # A known static dashboard is documentation only while its output is exactly
    # reproducible from reviewed data and the trusted generator/template.
    from build_feature_overview import compare_outputs, expected_outputs
    try:
        _, outputs = expected_outputs(root)
        errors.extend(compare_outputs(root, outputs))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"Feature overview: {exc}")
    return errors


if __name__ == "__main__":
    failures = check()
    for failure in failures:
        print(failure)
    if failures:
        raise SystemExit(1)
    print("Repository policy checks passed")
