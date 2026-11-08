"""Default-disabled local selector with a hard process deadline and no inherited secrets."""

import json
import subprocess  # nosec B404
import sys
from pathlib import Path
from threading import BoundedSemaphore

from app.config import settings
from app.local_answer_transport import strict_json

_slots = BoundedSemaphore(1)


def configuration():
    return (
        settings.document_answers_enabled,
        settings.ollama_url,
        settings.document_answer_model,
        settings.document_answer_digest,
    )


def select_passages(question, language, sources):
    outcome = {"status": "unavailable", "invoked": False, "selection": None}
    enabled, endpoint, model, digest = configuration()
    if not enabled or not model or not digest or not _slots.acquire(blocking=False):
        return outcome
    try:
        references = [
            {key: item[key] for key in ("source", "start_line", "end_line", "text")}
            for item in sources
        ]
        body = json.dumps(
            {
                "endpoint": endpoint,
                "model": model,
                "digest": digest,
                "question": question,
                "language": language,
                "sources": references,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        if len(body) > 16384:
            return outcome
        # Fixed interpreter/module; question and evidence travel only on stdin.
        with subprocess.Popen(  # nosec B603
            [sys.executable, "-m", "app.local_answer_transport"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
            cwd=Path(__file__).resolve().parents[1],
            env={"PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"},
        ) as child:
            timed_out = False
            try:
                output, _ = child.communicate(input=body, timeout=12)
            except subprocess.TimeoutExpired:
                timed_out = True
                child.kill()
                output, _ = child.communicate()
            invoked = output.startswith(b"D\n")
            outcome["invoked"] = invoked
            if timed_out or child.returncode or len(output) > 65539:
                return outcome
            value = strict_json(output[2:] if invoked else output)
            if (
                not isinstance(value, dict)
                or set(value) != {"status", "invoked", "selection"}
                or value["invoked"] is not invoked
                or value["status"] not in {"selected", "unavailable"}
            ):
                return outcome
            return value
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        return outcome
    finally:
        _slots.release()
