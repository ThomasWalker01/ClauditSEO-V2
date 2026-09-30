"""What started the server, recorded by the process being started.

Relay item 020. Two restarts replaced a running server and nothing on disk
could say what started the replacement; `data/server.log` holds 99 "Started
server process" lines and records only that a start happened.

The contract these tests hold is narrow and it is the whole point: **a field is
never blank in a way that could mean either "looked and found nothing" or "did
not look"**. That collapse is a defect this repository has already paid for on
the Cowork side, where an empty process query was read as "nothing is running".
"""

from __future__ import annotations

import json
import sys

from clauditseo import provenance


def test_a_record_names_the_process_and_its_parent(tmp_path):
    rec = provenance.start_record(tmp_path)

    for field in ("started_at", "pid", "exe", "argv", "ppid"):
        assert field in rec, f"the record does not name {field}: {rec}"
    assert isinstance(rec["pid"], int) and rec["pid"] > 0
    assert rec["exe"], "the executable is the field that tells a venv "
    "redirector from the interpreter it launches"


def test_the_parent_is_either_resolved_or_explained_never_blank(tmp_path):
    """The contract. A blank parent that might mean two different things is
    the defect; one of the two fields is always populated."""
    rec = provenance.start_record(tmp_path)

    assert (rec["parent"] is None) != (rec["parent_error"] is None), (
        "exactly one of parent / parent_error must be set — a record with "
        f"neither cannot be read: {rec}")


def test_an_unresolvable_parent_says_which_pid_and_why():
    """The case that actually happens: `restart-service.ps1` returns as soon
    as the server answers, so the shell that ran it can be gone before the
    server asks who its parent was.

    Split by platform because the reason differs and both are real. This
    asserted the pid unconditionally and passed on Windows while failing the
    Linux half of the gate — the same shape as rule 11's "a baseline taken
    against a different command is not a baseline", one axis over: a suite run
    on one platform is not the suite the gate runs.
    """
    parent, why = provenance._resolve_parent(999_999)

    assert parent is None
    assert why, "an unresolved parent must carry a reason, not a blank"
    if sys.platform == "win32":
        assert "999999" in why.replace(",", ""), (
            f"the reason must name the pid it failed on: {why!r}")
    else:
        # Not a lesser assertion: off Windows there is no `Win32_Process` to
        # query, so the honest reason is that the lookup is unavailable here —
        # and it must say so rather than reading as a parent that vanished.
        assert sys.platform in why and "Win32_Process" in why, (
            f"the reason must say the lookup is unavailable, and why: {why!r}")


def test_the_marker_is_read_through_a_byte_order_mark(tmp_path):
    """A regression, and it bit on the first real marker.

    `round-marker.ps1` writes with PowerShell 5.1's `Set-Content -Encoding
    utf8`, which emits a BOM. Read as plain utf-8 this raised "Unexpected
    UTF-8 BOM" and the marker — the one field that tells two restarts through
    the same script apart — was permanently unreadable.
    """
    run = tmp_path / ".claude" / "run"
    run.mkdir(parents=True)
    body = json.dumps({"kind": "round", "subject": "42", "phase": "verifying"})
    (run / "round.json").write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))

    marker, err = provenance._live_marker(tmp_path)

    assert err is None, f"a BOM must not make the marker unreadable: {err}"
    assert marker["kind"] == "round" and marker["subject"] == "42"


def test_no_marker_is_an_answer_and_not_an_error(tmp_path):
    """An absent marker is what an unattributed restart looks like, so it must
    not be reported as a failure to read one."""
    marker, err = provenance._live_marker(tmp_path)

    assert marker is None and err is None


def test_a_start_is_appended_and_an_unwritable_path_does_not_raise(tmp_path):
    """A server that refused to start because it could not write its own
    provenance would be a worse product than one that cannot say what started
    it."""
    data = tmp_path / "data"
    first = provenance.record_start(data, tmp_path)
    second = provenance.record_start(data, tmp_path)

    lines = (data / provenance.FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2, "each start appends; a start cannot overwrite one"
    assert json.loads(lines[0])["pid"] == first["pid"]
    assert "write_error" not in second

    # A path that cannot be created at all — a file where the directory goes.
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    rec = provenance.record_start(blocked / "data", tmp_path)
    assert "write_error" in rec, (
        "an unwritable record must be reported on the record itself")
