"""Regression guards for the Phase C governance package (spec 074).

These are **static regression guards, not a security sandbox.** They parse the package source and
fail on the obvious ways it could start generating or handling keys, reaching the network or a
database, or writing and deleting files, including keyword-based file modes, lower-level
descriptor writes, aliased or dynamic imports and attribute access. They cannot stop a determined
bypass (for example code assembled at run time in another module, native extensions or
monkeypatching), and they do not replace code review or the authorization boundary itself. No key
is created and nothing is executed beyond parsing source text.
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "app" / "recovery_governance"
FILES = sorted(PACKAGE.glob("*.py"))

FORBIDDEN_MODULES = {
    "secrets", "hmac", "hashlib", "cryptography", "nacl", "socket", "ssl", "http", "urllib",
    "httpx", "requests", "subprocess", "shutil", "sqlalchemy", "psycopg", "ftplib", "smtplib",
    "pickle", "marshal", "tempfile", "glob", "io", "pathlib", "builtins", "fileinput", "codecs",
    "importlib", "ctypes", "mmap", "multiprocessing", "asyncio", "signal", "atexit",
}  # fmt: skip
FORBIDDEN_NAMES = {
    # writing, truncating, creating, deleting, linking, permission changes
    "write", "writelines", "writev", "pwrite", "pwritev", "ftruncate", "truncate", "fdopen",
    "sendfile", "copy_file_range", "unlink", "remove", "removedirs", "rmdir", "rmtree", "rename",
    "renames", "replace", "chmod", "fchmod", "chown", "fchown", "mkdir", "makedirs", "mkfifo",
    "mknod", "symlink", "link", "write_text", "write_bytes", "touch", "utime", "setxattr",
    # process and code execution
    "system", "popen", "spawn", "fork", "exec", "execv", "eval", "__import__",
    # randomness (key generation)
    "urandom", "token_bytes", "token_hex", "token_urlsafe", "getrandom", "SystemRandom",
    # environment
    "environ", "environb", "getenv",
    # creating or write-opening flags
    "O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND", "O_EXCL", "O_TMPFILE",
}  # fmt: skip
ALLOWED_OPEN_FLAGS = {"O_RDONLY", "O_NOFOLLOW", "O_CLOEXEC", "O_DIRECTORY"}
KEY_OPERATION_NAMES = {"generate", "provision", "rotate", "store", "activate", "revoke", "escrow"}
READ_MODE_FORBIDDEN = set("wax+")


def _call_name(node):
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def _constant_strings(node):
    return [
        n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def violations(source):
    """Return the list of guard violations found in a module's source text."""
    found = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_MODULES or alias.name.startswith(
                    ("app.recovery_set", "app.config", "app.db", "app.models")
                ):
                    found.append(f"import {alias.name}")
                if alias.asname and alias.name.split(".")[0] == "os":
                    found.append("aliased os import")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if (
                root in FORBIDDEN_MODULES
                or module.startswith(("app.recovery_set", "app.config", "app.db", "app.models"))
                or root == "os"
            ):
                found.append(f"from {module} import")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            found.append(f"attribute {node.attr}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES | {"load_key", "KeyFile"}:
            found.append(f"name {node.id}")
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name == "compile" and isinstance(node.func, ast.Name):
                found.append("builtin compile")
            if name == "open":
                found += _open_violations(node)
            elif name in {"getattr", "setattr", "delattr", "vars", "globals", "locals"}:
                found += _dynamic_violations(node, name)
        elif isinstance(node, ast.ClassDef):
            bases = {getattr(b, "id", getattr(b, "attr", "")) for b in node.bases}
            if "Protocol" not in bases:
                for item in node.body:
                    if (
                        isinstance(item, ast.FunctionDef)
                        and item.name.lstrip("_") in KEY_OPERATION_NAMES
                    ):
                        found.append(f"key operation {item.name}")
        elif (
            isinstance(node, ast.FunctionDef)
            and node.name.lstrip("_") in KEY_OPERATION_NAMES
            and node in tree.body
        ):
            found.append(f"key operation {node.name}")
    return found


def _open_violations(node):
    found = []
    func = node.func
    is_os_open = (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
    )
    if isinstance(func, ast.Attribute) and not is_os_open:
        return ["attribute open"]  # io.open, Path.open, ...: the package has no use for them
    if is_os_open:
        if len(node.args) > 2 or any(kw.arg == "mode" for kw in node.keywords):
            found.append("os.open creation mode")
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            found.append("os.open literal flags")
        for attribute in [
            n for n in ast.walk(node) if isinstance(n, ast.Attribute) and n.attr.startswith("O_")
        ]:
            if attribute.attr not in ALLOWED_OPEN_FLAGS:
                found.append(f"open flag {attribute.attr}")
        for text in _constant_strings(node):
            if text.startswith("O_") and text not in ALLOWED_OPEN_FLAGS:
                found.append(f"open flag {text}")
        return found
    if any(kw.arg == "opener" for kw in node.keywords):
        found.append("open opener")
    mode_nodes = list(node.args[1:2]) + [kw.value for kw in node.keywords if kw.arg == "mode"]
    for mode in mode_nodes:
        if not (isinstance(mode, ast.Constant) and isinstance(mode.value, str)):
            found.append("open non-constant mode")
        elif set(mode.value) & READ_MODE_FORBIDDEN:
            found.append(f"open mode {mode.value}")
    return found


def _dynamic_violations(node, name):
    found = []
    if name in {"vars", "globals", "locals", "setattr", "delattr"}:
        found.append(f"dynamic {name}")
    elif len(node.args) < 2 or not (
        isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)
    ):
        found.append("dynamic getattr")
    else:
        target = node.args[1].value
        if target in FORBIDDEN_NAMES or (
            target.startswith("O_") and target not in ALLOWED_OPEN_FLAGS
        ):
            found.append(f"getattr {target}")
    return found


def test_package_exists_and_has_the_expected_modules():
    assert {p.name for p in FILES} >= {
        "__init__.py", "common.py", "hash_record.py", "retention.py", "capacity.py", "custody.py",
    }  # fmt: skip


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_the_package_source_has_no_guard_violations(path):
    assert violations(path.read_text()) == []


BYPASS_ATTEMPTS = {
    "keyword mode write": 'open("p", mode="w")',
    "positional write": 'open("p", "wb")',
    "append": 'open("p", "a")',
    "exclusive create": 'open("p", "x")',
    "read-write": 'open("p", "r+")',
    "keyword non-constant mode": 'open("p", mode=m)',
    "positional non-constant mode": 'open("p", m)',
    "opener": 'open("p", opener=f)',
    "attribute open with write mode": 'p.open("w")',
    "io.open": 'import io\nio.open("p", "w")',
    "attribute open any mode": "p.open()",
    "os.open write flag": 'import os\nos.open("p", os.O_WRONLY)',
    "os.open create flag": 'import os\nos.open("p", os.O_RDONLY | os.O_CREAT)',
    "os.open truncate": 'import os\nos.open("p", os.O_RDWR | os.O_TRUNC)',
    "os.open literal flags": 'import os\nos.open("p", 1)',
    "os.open creation mode": 'import os\nos.open("p", os.O_RDONLY, 0o600)',
    "os.open mode keyword": 'import os\nos.open("p", os.O_RDONLY, mode=0o600)',
    "from os import flags": "from os import O_WRONLY",
    "from os import open": "from os import open as o",
    "aliased os": "import os as o\no.write(1, b'')",
    "descriptor write": "import os\nos.write(1, b'x')",
    "vectored write": "import os\nos.writev(1, [b'x'])",
    "positional write call": "import os\nos.pwrite(1, b'x', 0)",
    "file object write": 'f.write("x")',
    "file object writelines": 'f.writelines(["x"])',
    "fdopen": 'import os\nos.fdopen(1, "w")',
    "truncate": "import os\nos.ftruncate(1, 0)",
    "sendfile": "import os\nos.sendfile(1, 2, 0, 1)",
    "dynamic getattr": "import os\ngetattr(os, name)",
    "getattr of write": 'import os\ngetattr(os, "write")',
    "getattr of write flag": 'import os\ngetattr(os, "O_WRONLY")',
    "dynamic builtins": "vars()[n]()",
    "setattr": 'setattr(os, "x", 1)',
    "dunder import": '__import__("os")',
    "importlib": "import importlib",
    "importlib from": "from importlib import import_module",
    "ctypes": "import ctypes",
    "mmap": "import mmap",
    "io module": "import io",
    "pathlib": "from pathlib import Path",
    "builtins": "import builtins",
    "eval": 'eval("1")',
    "exec": 'exec("x = 1")',
    "compile": 'compile("1", "f", "eval")',
    "unlink": "import os\nos.unlink('p')",
    "rmtree": "import shutil",
    "chmod": "import os\nos.chmod('p', 0)",
    "urandom": "import os\nos.urandom(32)",
    "secrets": "import secrets",
    "hmac": "import hmac",
    "hashlib": "import hashlib",
    "random key source": "from secrets import token_bytes",
    "network": "import socket",
    "database": "import sqlalchemy",
    "phase b tool": "from app.recovery_set import verify",
    "phase b tool dotted": "import app.recovery_set.key",
    "environment": 'import os\nos.environ["X"]',
    "getenv": 'import os\nos.getenv("X")',
    "key loader": "load_key(path)",
    "concrete generate": "class K:\n    def generate(self):\n        pass",
    "module-level provision": "def provision():\n    pass",
}


@pytest.mark.parametrize("name", sorted(BYPASS_ATTEMPTS))
def test_the_guard_detects_each_known_bypass_or_forbidden_construct(name):
    assert violations(BYPASS_ATTEMPTS[name]), name


READ_ONLY_PATTERNS = {
    "read open": 'open("p")',
    "explicit read mode": 'open("p", "r")',
    "keyword read mode": 'open("p", mode="rb")',
    "descriptor read with allowed flags": (
        "import os\n"
        'flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)\n'
        "d = os.open(path, flags)\nos.read(d, 1)\nos.close(d)"
    ),
    "interface-only protocol": (
        "from typing import Protocol\nclass P(Protocol):\n    def generate(self) -> None: ...\n"
    ),
}


@pytest.mark.parametrize("name", sorted(READ_ONLY_PATTERNS))
def test_the_guard_allows_the_read_only_patterns_the_package_uses(name):
    assert violations(READ_ONLY_PATTERNS[name]) == [], name


def test_the_phase_b_output_contract_is_untouched_by_this_package():
    from app.recovery_set import result

    assert not hasattr(result, "governance")
    assert "recovery_governance" not in Path(result.__file__).read_text()
