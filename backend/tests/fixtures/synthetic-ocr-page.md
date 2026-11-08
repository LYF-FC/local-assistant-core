# Synthetic OCR raster

The compressed grayscale PGM contains only these deliberately generated lines: `Synthetic invoice`, `Facture facture`, `Factura total`, `TOTAL 123.45`. It was rendered from the stdlib `pdf_fixtures.pdf` Helvetica fixture at 24 points using Poppler grayscale, long side 1600 pixels. No external image or record is used. It has no text layer or metadata. Tests embed its pixels into image-only PDFs; expected OCR content is checked against these synthetic source lines.

Uncompressed PGM SHA-256: `c4bf2c9542db1d8c9417717f30b12db07606cd16cdcd6f7a7585d1bf5919dba1`.
