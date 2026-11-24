#!/usr/bin/env python3
"""Deterministic synthetic PDF invoice fixtures for the MVP-01 "paper invoice" rehearsal (spec 078).

Standard library only, no timestamps, no host fonts and no external image: the bytes depend on nothing but this file
and, for the scan, the committed grayscale raster `invoice-scan.pgm.zlib`.

* P1  invoice-pdf.eml          one-page text PDF (Helvetica), invoice MVP01-2026-003
* P2  invoice-scan.eml         one-page image-only PDF, invoice MVP01-2026-004; the "Total" line is deliberately blurred
* P3  invoice-pdf-offline.eml  one-page text PDF, invoice MVP01-2026-005 (imported while the PDF worker is stopped)

The scan raster was produced once from the text rendering of the P2 lines at 20 pt (Poppler `pdftoppm -gray -r 100` in the
repository's own PDF worker image), then degraded by `degrade()` below (blur of the Total line and reduced contrast). Rebuilding the raster needs that image; verifying and assembling the PDFs does not.

    python3 paper_fixtures.py check    # recompute every fixture from committed inputs and compare with the manifest
    python3 paper_fixtures.py write    # rewrite the three .eml files from committed inputs (never touches the raster)
"""

import base64
import hashlib
import re
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
RASTER = HERE / "invoice-scan.pgm.zlib"
ISSUER = "Synthetic Rehearsal Vendor"

FIXTURES = {
    "invoice-pdf.eml": {
        "kind": "text",
        "number": "MVP01-2026-003",
        "message_id": "mvp01-paper-text-003",
        "date": "Mon, 23 Nov 2026 09:00:00 +0000",
        "issued": "2026-11-23",
        "due": "2027-01-08",
        "total": "312.80",
        "attachment": "invoice-MVP01-2026-003.pdf",
        "boundary": "===============7301000000000000003==",
    },
    "invoice-scan.eml": {
        "kind": "scan",
        "number": "MVP01-2026-004",
        "message_id": "mvp01-paper-scan-004",
        "date": "Mon, 23 Nov 2026 09:05:00 +0000",
        "issued": "2026-11-23",
        "due": "2027-01-08",
        "total": "178.90",
        "attachment": "scan-MVP01-2026-004.pdf",
        "boundary": "===============7301000000000000004==",
    },
    "invoice-pdf-offline.eml": {
        "kind": "text",
        "number": "MVP01-2026-005",
        "message_id": "mvp01-paper-offline-005",
        "date": "Mon, 23 Nov 2026 09:10:00 +0000",
        "issued": "2026-11-23",
        "due": "2027-01-08",
        "total": "64.20",
        "attachment": "invoice-MVP01-2026-005.pdf",
        "boundary": "===============7301000000000000005==",
    },
}


def lines(spec):
    return [
        f"Issuer: {ISSUER}",
        f"Invoice number: {spec['number']}",
        f"Invoice date: {spec['issued']}",
        f"Due date: {spec['due']}",
        f"Total: {spec['total']}",
        "Currency: EUR",
    ]


def assemble(objects, trailer_extra=b""):
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, content in enumerate(objects, 1):
        offsets.append(len(out))
        out.extend(f"{number} 0 obj\n".encode() + content + b"\nendobj\n")
    start = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        out.extend(f"{offset:010} 00000 n \n".encode())
    out.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R{trailer_extra.decode()} >>\nstartxref\n{start}\n%%EOF\n".encode())
    return bytes(out)


def escape(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_pdf(rows, size=14):
    commands = [f"BT /F1 {size} Tf {size * 1.6} TL 72 720 Td"]
    commands += [f"({escape(row)}) Tj T*" for row in rows]
    commands.append("ET")
    stream = "\n".join(commands).encode("latin1")
    return assemble(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        ]
    )


def hostile_pdf():
    """Agent-only (never offered to the owner, never written to disk by `write`): a valid one-page PDF carrying an
    OpenAction JavaScript, a page-level additional action and a URI link to a non-resolving host. The original view must
    run none of it and make no request to `example.invalid`."""
    stream = b"BT /F1 14 Tf 72 720 Td (Synthetic hostile-PDF test page) Tj ET"
    return assemble(
        [
            b"<< /Type /Catalog /Pages 2 0 R /OpenAction << /S /JavaScript /JS (app.alert\\('SCRIPT-RAN');) >> >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R /Annots [6 0 R] /AA << /O << /S /JavaScript /JS (app.alert\\('PAGE-SCRIPT-RAN');) >> >> >>",
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Annot /Subtype /Link /Rect [60 700 400 740] /Border [0 0 0] /A << /S /URI /URI (http://example.invalid/hostile) >> >>",
        ]
    )


def malformed_pdf():
    """Agent-only: starts like a PDF but is damaged (truncated object, no xref/trailer)."""
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 99 0 R /MediaBox [0 0 612\nstream\n" + bytes(range(32, 120)) * 4


def huge_page_pdf():
    """Agent-only: a valid one-page PDF whose page claims to be 100000 x 100000 points (canvas budget test)."""
    stream = b"BT /F1 14 Tf 72 720 Td (Synthetic oversized-page test) Tj ET"
    return assemble(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100000 100000] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        ]
    )


AGENT_ONLY = {
    "hostile": ("hostile-test.pdf", "099", "Mon, 23 Nov 2026 09:20:00 +0000"),
    "malformed": ("malformed-test.pdf", "098", "Mon, 23 Nov 2026 09:21:00 +0000"),
    "huge": ("huge-page-test.pdf", "097", "Mon, 23 Nov 2026 09:22:00 +0000"),
}


def agent_eml(kind):
    """Agent-only forwarded mails (never offered to the owner, never written to disk by `write`)."""
    pdf = {"hostile": hostile_pdf, "malformed": malformed_pdf, "huge": huge_page_pdf}[kind]()
    filename, number, date = AGENT_ONLY[kind]
    encoded = base64.encodebytes(pdf).decode().replace("\n", "\r\n")
    boundary = f"===============73010000000000000{number}=="
    head = (
        "From: billing@vendor.example.invalid\r\nTo: household@example.invalid\r\n"
        f"Subject: Synthetic {kind} PDF test\r\nDate: {date}\r\n"
        f"Message-ID: <mvp01-paper-{kind}-{number}@example.invalid>\r\nMIME-Version: 1.0\r\n"
        f'Content-Type: multipart/mixed; boundary="{boundary}"\r\n\r\n'
        f'--{boundary}\r\nContent-Type: text/plain; charset="utf-8"\r\nContent-Transfer-Encoding: 7bit\r\n\r\n'
        "Synthetic test for the original view. Agent only. No real data.\r\n\r\n"
        f"--{boundary}\r\nContent-Type: application/pdf\r\nContent-Transfer-Encoding: base64\r\n"
        f'Content-Disposition: attachment; filename="{filename}"\r\nMIME-Version: 1.0\r\n\r\n'
    )
    return (head + encoded + f"\r\n--{boundary}--\r\n").encode()


def hostile_eml():
    return agent_eml("hostile")


def read_raster():
    raw = zlib.decompress(RASTER.read_bytes())
    header = re.match(rb"P5\n([0-9]+) ([0-9]+)\n255\n", raw)
    width, height = map(int, header.groups())
    pixels = raw[header.end() :]
    assert len(pixels) == width * height
    return width, height, pixels


def scan_pdf():
    width, height, pixels = read_raster()
    image = zlib.compress(pixels, 9)
    commands = b"q 612 0 0 792 0 0 cm /Im1 Do Q"
    return assemble(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im1 5 0 R >> >> /Contents 4 0 R >>",
            f"<< /Length {len(commands)} >>\nstream\n".encode() + commands + b"\nendstream",
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length {len(image)} >>\nstream\n".encode()
            + image
            + b"\nendstream",
        ]
    )


def eml(name, pdf):
    spec = FIXTURES[name]
    encoded = base64.encodebytes(pdf).decode().replace("\n", "\r\n")
    head = (
        f"From: billing@vendor.example.invalid\r\nTo: household@example.invalid\r\n"
        f"Subject: Synthetic MVP-01 paper invoice {spec['number']}\r\nDate: {spec['date']}\r\n"
        f"Message-ID: <{spec['message_id']}@example.invalid>\r\nMIME-Version: 1.0\r\n"
        f'Content-Type: multipart/mixed; boundary="{spec["boundary"]}"\r\n\r\n'
        f"--{spec['boundary']}\r\nContent-Type: text/plain; charset=\"utf-8\"\r\nContent-Transfer-Encoding: 7bit\r\n\r\n"
        "Synthetic forwarded paper invoice for the MVP-01 rehearsal. No real data.\r\n\r\n"
        f"--{spec['boundary']}\r\nContent-Type: application/pdf\r\nContent-Transfer-Encoding: base64\r\n"
        f'Content-Disposition: attachment; filename="{spec["attachment"]}"\r\nMIME-Version: 1.0\r\n\r\n'
    )
    return (head + encoded + f"\r\n--{spec['boundary']}--\r\n").encode()


def build(name):
    spec = FIXTURES[name]
    pdf = text_pdf(lines(spec)) if spec["kind"] == "text" else scan_pdf()
    return pdf, eml(name, pdf)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest():
    result = {"invoice-scan.pgm.zlib": sha(RASTER.read_bytes())}
    for name in FIXTURES:
        pdf, mail = build(name)
        result[name] = sha(mail)
        result[FIXTURES[name]["attachment"]] = sha(pdf)
    return result


def degrade(width, height, pixels, total_rows):
    """Documented, deterministic degradation applied once to the clean Poppler raster (not run at check time)."""
    out = bytearray(pixels)
    for y in range(height):  # low contrast: map 0..255 onto 70..235
        for x in range(width):
            out[y * width + x] = 70 + out[y * width + x] * 165 // 255
    top, bottom = total_rows  # box blur (radius 3, three passes) over the Total line only
    for _ in range(3):
        copy = bytes(out)
        for y in range(top, bottom):
            for x in range(3, width - 3):
                row = y * width
                out[row + x] = sum(copy[row + x - 3 : row + x + 4]) // 7
    return bytes(out)


def main(argv):
    action = argv[1] if len(argv) > 1 else "check"
    if action == "write":
        for name in FIXTURES:
            (HERE / name).write_bytes(build(name)[1])
        print("wrote", ", ".join(FIXTURES))
    elif action == "manifest":
        for key, value in manifest().items():
            print(f"{value}  {key}")
    elif action == "check":
        for name in FIXTURES:
            assert (HERE / name).read_bytes() == build(name)[1], f"{name} differs from its generator"
        print("fixtures match their generator")
    else:
        raise SystemExit("usage: paper_fixtures.py check|write|manifest")


if __name__ == "__main__":
    main(sys.argv)
