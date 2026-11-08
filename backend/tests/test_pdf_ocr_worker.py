"""Worker fault checks without launching unconfined native binaries."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "pdf_worker_under_test", Path(__file__).resolve().parents[2] / "pdf-worker/worker.py"
)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


@pytest.mark.parametrize("fault", ["none", "oversized", "malformed", "deadline"])
def test_ocr_raster_bounds_and_single_whole_request_deadline(monkeypatch, fault):
    deadlines = []

    def command(mode, original=b"", output_limit=worker.MAX_OUTPUT, *, deadline=None):
        deadlines.append(deadline)
        if mode == "info":
            return 0, b"Pages: 2\nEncrypted: no\n", b""
        if mode.startswith("render"):
            if fault == "deadline":
                raise worker.BoundedFailure("resource_limit")
            return (
                0,
                b"P5\n1601 1\n255\nx"
                if fault == "oversized"
                else b"bad"
                if fault == "malformed"
                else b"P5\n1 1\n255\nx",
                b"",
            )
        assert mode == "ocr"
        return 0, b"Synthetic\n", b""

    monkeypatch.setattr(worker, "command", command)
    row = worker.extract(b"%PDF-synthetic", "25.03.0", ocr=True)
    assert row["engine"] == "poppler-tesseract-v1"
    assert len(set(deadlines)) == 1 and deadlines[0] is not None
    assert row["status"] == ("ready" if fault == "none" else "resource_limit")
    if fault == "none":
        assert row["text"] == "Synthetic\nSynthetic" and len(row["page_spans"]) == 2
    else:
        assert row["text"] == "" and row["page_spans"] == []
