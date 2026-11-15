"""Authorization-boundary guards for the Phase C governance package (spec 074).

These tests fail if the package ever gains key generation, key handling, network or database
access, writes or deletions, or a dependency on the Phase B tool. They are static checks only:
no key is created and nothing is executed beyond parsing source files.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "app" / "recovery_governance"
FILES = sorted(PACKAGE.glob("*.py"))
FORBIDDEN_IMPORTS = {
    "secrets", "hmac", "cryptography", "nacl", "socket", "ssl", "http", "urllib", "httpx",
    "requests", "subprocess", "shutil", "sqlalchemy", "psycopg", "ftplib", "smtplib", "pickle",
    "tempfile", "glob",
}  # fmt: skip
FORBIDDEN_CALLS = {
    "urandom", "token_bytes", "token_hex", "unlink", "remove", "rmdir", "rmtree", "rename",
    "replace", "truncate", "chmod", "chown", "mkdir", "makedirs", "symlink", "link", "write_text",
    "write_bytes", "system", "popen", "exec", "eval",
}  # fmt: skip
KEY_OPERATION_NAMES = {"generate", "provision", "rotate", "store", "activate", "revoke", "escrow"}


def trees():
    return [(path, ast.parse(path.read_text())) for path in FILES]


def test_package_exists_and_has_the_expected_modules():
    assert {p.name for p in FILES} >= {
        "__init__.py", "common.py", "hash_record.py", "retention.py", "capacity.py", "custody.py",
    }  # fmt: skip


def test_no_forbidden_imports_and_no_dependency_on_the_phase_b_tool():
    for path, tree in trees():
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert name.split(".")[0] not in FORBIDDEN_IMPORTS, (path.name, name)
                assert not name.startswith("app.recovery_set"), (path.name, name)
                assert not name.startswith(("app.config", "app.db", "app.models")), (
                    path.name,
                    name,
                )


def test_no_write_delete_exec_or_random_calls_and_no_write_modes():
    for path, tree in trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                assert name not in FORBIDDEN_CALLS, (path.name, name)
                if name in {"open"}:
                    modes = [a.value for a in node.args[1:2] if isinstance(a, ast.Constant)]
                    assert all(isinstance(m, str) and not set(m) & set("wax+") for m in modes)
            if isinstance(node, ast.Attribute) and node.attr in {"O_WRONLY", "O_RDWR", "O_CREAT"}:
                raise AssertionError((path.name, node.attr))


def test_no_concrete_key_operation_is_defined_anywhere():
    for path, tree in trees():
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            bases = {getattr(b, "id", getattr(b, "attr", "")) for b in cls.bases}
            if "Protocol" in bases:
                continue
            for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
                assert fn.name.lstrip("_") not in KEY_OPERATION_NAMES, (path.name, fn.name)
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
            assert fn.name.lstrip("_") not in KEY_OPERATION_NAMES, (path.name, fn.name)


def test_the_package_never_reads_key_material_or_environment():
    for path, tree in trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"environ", "environb", "getenv"}, path.name
            if isinstance(node, ast.Name):
                assert node.id not in {"environ", "getenv", "load_key", "KeyFile"}, path.name
        text = path.read_text()
        assert "recovery-key" not in text and "load_key" not in text, path.name


def test_the_phase_b_output_contract_is_untouched_by_this_package():
    from app.recovery_set import result

    assert (
        not hasattr(result, "governance")
        and "recovery_governance" not in Path(result.__file__).read_text()
    )
