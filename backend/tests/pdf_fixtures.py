"""Hand-built synthetic PDFs; no external records, media or generator dependency."""


def pdf(pages=("Synthetic invoice 100.00",), *, encrypted=False, compressed=False, font_size=12):
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    font_id = 3 + 2 * len(pages)
    children = []
    for text in pages:
        page_id, stream_id = len(objects) + 1, len(objects) + 2
        children.append(f"{page_id} 0 R")
        commands = [f"BT /F1 {font_size} Tf {font_size * 1.2} TL 72 720 Td"]
        for line in text.split("\n"):
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({escaped}) Tj T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin1")
        if compressed:
            import zlib

            stream = zlib.compress(stream)
        objects.extend(
            [
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {stream_id} 0 R >>".encode(),
                f"<< /Length {len(stream)} {'/Filter /FlateDecode' if compressed else ''} >>\nstream\n".encode()
                + stream
                + b"\nendstream",
            ]
        )
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(children)}] /Count {len(pages)} >>".encode()
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    encryption = b""
    if encrypted:
        objects.append(
            b"<< /Filter /Standard /V 1 /R 2 /Length 40 /O <"
            + b"00" * 32
            + b"> /U <"
            + b"00" * 32
            + b"> /P -4 >>"
        )
        encryption = f" /Encrypt {len(objects)} 0 R /ID [<{'00' * 16}><{'00' * 16}>]".encode()
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, content in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + content + b"\nendobj\n")
    start = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R".encode()
        + encryption
        + f" >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    return bytes(output)


def scanned_pdf(pages=1, *, blank=False, mixed=False):
    """Image-only synthetic originals; text-layer extraction must return no text."""
    import re
    import zlib
    from pathlib import Path

    raster = zlib.decompress(
        (Path(__file__).parent / "fixtures/synthetic-ocr-page.pgm.zlib").read_bytes()
    )
    header = re.match(rb"P5\n([0-9]+) ([0-9]+)\n255\n", raster)
    width, height = map(int, header.groups())
    pixels = raster[header.end() :]
    assert len(pixels) == width * height
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    children = []
    for page in range(pages):
        page_id, content_id, image_id = len(objects) + 1, len(objects) + 2, len(objects) + 3
        children.append(f"{page_id} 0 R")
        image = zlib.compress(b"\xff" * len(pixels) if blank or mixed and page > 0 else pixels)
        commands = b"q 612 0 0 792 0 0 cm /Im1 Do Q"
        objects.extend(
            [
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im1 {image_id} 0 R >> >> /Contents {content_id} 0 R >>".encode(),
                f"<< /Length {len(commands)} >>\nstream\n".encode() + commands + b"\nendstream",
                f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length {len(image)} >>\nstream\n".encode()
                + image
                + b"\nendstream",
            ]
        )
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(children)}] /Count {pages} >>".encode()
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, content in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + content + b"\nendobj\n")
    start = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    return bytes(output)
