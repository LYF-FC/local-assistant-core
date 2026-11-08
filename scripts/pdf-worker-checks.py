"""Run inside a disposable network-free parser container with synthetic JSON stdin."""

import base64
import json
import sys

sys.path.insert(0, "/opt")
import worker

code, probe, _ = worker.command("probe", output_limit=1024)
assert code == 0 and probe == b"confined\n"
code, memory, _ = worker.command("probe_memory", output_limit=1024)
assert code == 0 and memory == b"bounded\n"
code, _, _ = worker.command("probe_cpu", output_limit=1024)
assert code < 0
try:
    worker.command("probe_output", output_limit=1024)
except worker.BoundedFailure:
    pass
else:
    raise AssertionError("Unbounded parser output was accepted")
code, _, version = worker.command("version", output_limit=1024)
assert code == 0
matches = worker.re.findall(rb"pdftotext version ([0-9.]+)", version)
assert len(matches) == 1
cases = json.loads(sys.stdin.buffer.read(1024 * 1024))
assert isinstance(cases, list) and 1 <= len(cases) <= 10
for case in cases:
    raw = base64.b64decode(case["original"], validate=True)
    assert len(raw) <= 131072
    result = worker.extract(raw, matches[0].decode())
    assert result["status"] == case["status"], (case["name"], result["status"])
    if case["status"] == "ready":
        assert result["text"] == case["text"]
        assert result["pages"] == case["pages"]
        assert result["page_spans"][-1]["end_line"] == len(result["text"].split("\n"))
print("Synthetic PDF states and actual syscall/CPU/memory/output confinement passed")
