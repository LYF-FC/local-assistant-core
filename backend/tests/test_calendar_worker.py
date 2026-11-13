import pytest

from app import calendar_sync, calendar_worker
from app.config import settings


def configure(monkeypatch, **values):
    for key, value in {
        "env": "test",
        "postgres_user": "butler_runtime",
        "postgres_db": "butler_test_x",
        "calendar_synthetic_directory": "/tmp",
        **values,
    }.items():
        monkeypatch.setattr(settings, key, value)


@pytest.mark.parametrize(
    "override",
    [
        {"env": "production"},
        {"env": "staging"},
        {"postgres_user": "butler"},
        {"postgres_db": "butler"},
        {"calendar_synthetic_directory": None},
    ],
)
def test_the_worker_refuses_to_start_outside_the_restricted_test_setup(monkeypatch, override):
    configure(monkeypatch, **override)
    with pytest.raises(RuntimeError):
        calendar_worker.main(["--once"])


def test_a_pass_is_printed_and_errors_make_the_run_fail(monkeypatch, capsys):
    configure(monkeypatch)
    monkeypatch.setattr(calendar_sync, "run_pass", lambda: {"checked": 2, "ok": 2, "errors": 0})
    calendar_worker.main(["--once"])
    assert "Synthetic calendar pass: checked=2, ok=2, errors=0" in capsys.readouterr().out
    monkeypatch.setattr(calendar_sync, "run_pass", lambda: {"checked": 1, "errors": 1})
    with pytest.raises(SystemExit) as caught:
        calendar_worker.main(["--once"])
    assert caught.value.code == 1


def test_one_of_once_or_loop_is_required():
    with pytest.raises(SystemExit):
        calendar_worker.main([])
