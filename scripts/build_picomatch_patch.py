"""Rebuild the temporary picomatch archive from its verified npm release and upstream patch.

Download with: npm pack picomatch@4.0.7 --ignore-scripts --pack-destination /tmp
Then: python3 scripts/build_picomatch_patch.py /tmp/picomatch-4.0.7.tgz
No network access, install hooks, or version rewriting is performed by this script.
"""

import argparse
import gzip
import hashlib
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "frontend/vendor/picomatch"
ORIGINAL_SHA256 = "697b463be3cdbd9ffc8f4194fd5019a69ddf95875fb703d78b2b115cc9e740a8"

PATCH_SHA256 = "71b0f6637e7c33d07dffee9dce0b3b0e19004d59ed57e29aa6ca6291af63592e"


def build(source, destination):
    if (
        hashlib.sha256((VENDOR / "upstream-254.patch").read_bytes()).hexdigest()
        != PATCH_SHA256
    ):
        raise SystemExit("Patch does not match the reviewed upstream security hunk")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != ORIGINAL_SHA256:
        raise SystemExit(
            "Source does not match the locked, published picomatch 4.0.7 archive"
        )
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = {}
        for member in archive.getmembers():
            path = Path(member.name)
            if not member.isfile() or path.parts[0] != "package" or ".." in path.parts:
                raise SystemExit("Unexpected member in published archive")
            members[member.name] = archive.extractfile(member).read()
    with tempfile.TemporaryDirectory(prefix="picomatch-rebuild-") as scratch:
        directory = Path(scratch)
        for name, content in members.items():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        subprocess.run(
            [
                "patch",
                "-p1",
                "--batch",
                "--fuzz=0",
                "-i",
                str(VENDOR / "upstream-254.patch"),
            ],
            cwd=directory / "package",
            check=True,
        )
        for name, original in members.items():
            content = (directory / name).read_bytes()
            if name != "package/lib/parse.js" and content != original:
                raise SystemExit("Unexpected non-security source change")
            members[name] = content
    output = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=output, filename="", mode="wb", mtime=0) as compressed,
        tarfile.open(
            fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT
        ) as archive,
    ):
        for name, content in sorted(members.items()):
            member = tarfile.TarInfo(name)
            member.size, member.mode, member.mtime = len(content), 0o644, 0
            archive.addfile(member, io.BytesIO(content))
    destination.write_bytes(output.getvalue())
    print(f"{hashlib.sha256(output.getvalue()).hexdigest()}  {destination.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output", type=Path, default=VENDOR / "picomatch-4.0.7-upstream-254.tgz"
    )
    options = parser.parse_args()
    build(options.source, options.output)
