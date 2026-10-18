"""What started this server process, recorded by the process itself.

Two restarts replaced a running server and nobody could say what had started
the replacement — pid `10720` at 2026-08-16 21:58:01 and pid `4720` at
2026-08-17 07:55:24. `OPERATOR_ACTIONS.md` records both and states the limit
outright: "it is the one question the loop cannot answer for itself."

`data/server.log` holds 99 `Started server process` lines and two shutdown
markers, which is the shape of the problem: it records *that* a start happened
and never *what* started it, and 97 terminations left no trace because the
process was killed rather than asked to stop.

**Written at start, by the process being started.** A poller looking afterwards
finds the parent already exited — `restart-service.ps1` returns as soon as the
server answers, and the shell that ran it may be gone seconds later. The parent
is resolvable from exactly one vantage point and for a short time, and this is
it.

**A blank field is forbidden.** Either `parent` holds a resolved record or
`parent_error` says why it could not be resolved, never both null. That
distinction is the 08:32 defect on the Cowork side, where an empty result set
was read as "nothing is running" — the difference between looking and finding
nothing, and not having looked.

**The live marker is what tells the routes apart.** A restart from a round's
step 5 and one run by hand both go through `restart-service.ps1` and the same
scheduled task, so the process tree is identical and cannot distinguish them.
The marker can: a round holds `kind: round` while it restarts, a relay item
holds `kind: relay`, and a restart nobody initiated holds nothing at all.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

#: One JSON object per line, appended. Never rewritten, so a start cannot be
#: edited out of the record by a later one.
FILENAME = "server-starts.jsonl"

_PS_QUERY = (
    "$p = Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\" "
    "-ErrorAction SilentlyContinue; "
    "if ($p) {{ @{{ name = $p.Name; exe = $p.ExecutablePath; "
    "cmdline = $p.CommandLine; created = $p.CreationDate.ToString('o') }} "
    "| ConvertTo-Json -Compress }}"
)


def _resolve_parent(ppid: int) -> tuple[dict | None, str | None]:
    """The parent process, or the reason it could not be read.

    Shells out because `psutil` is not a dependency here and the Windows APIs
    that return another process's command line are not reachable from the
    standard library. It runs once, at start-up.
    """
    if sys.platform != "win32":
        return None, f"not resolvable on {sys.platform}: needs Win32_Process"
    # Resolved, not handed over as a bare name — the rule
    # `test_no_program_is_handed_to_subprocess_by_bare_name` enforces, and it
    # caught this line. A bare name resolves through PATH, which is not the
    # same PATH under a scheduled task as in a shell, and "usually the right
    # one" is not what a provenance record may be built on.
    powershell = shutil.which("powershell")
    if not powershell:
        return None, "powershell not found on PATH, so the parent was not read"
    try:
        out = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", _PS_QUERY.format(pid=ppid)],
            capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    body = (out.stdout or "").strip()
    if not body:
        # The common and important case: the parent exited between it starting
        # this process and this process asking. Said explicitly, because a
        # blank parent that might mean "never looked" is the defect above.
        return None, (f"no Win32_Process row for pid {ppid} — the parent had "
                      f"already exited (powershell rc={out.returncode})")
    try:
        return json.loads(body), None
    except json.JSONDecodeError as exc:
        return None, f"unparseable Win32_Process reply: {exc}"


def _live_marker(root: Path) -> tuple[dict | None, str | None]:
    """The round marker as it stood at this start, or why it could not be read.

    Absent is an answer and not an error: it means no round, plan, relay item
    or feature was underway, which is exactly what an unattributed restart
    looks like.
    """
    path = root / ".claude" / "run" / "round.json"
    if not path.is_file():
        return None, None
    try:
        # `utf-8-sig`, because PowerShell 5.1's `Set-Content -Encoding utf8`
        # writes a BOM and `round-marker.ps1` is what writes this file. Plain
        # utf-8 raised "Unexpected UTF-8 BOM" on the very first real marker.
        # Caught only because an unreadable marker reports why instead of
        # reading as absent — had this returned a blank, the one field that
        # tells two restarts apart would have been permanently empty and
        # nothing would have said so.
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def start_record(root: Path) -> dict:
    """Everything knowable about this start, from inside it."""
    ppid = os.getppid()
    parent, parent_error = _resolve_parent(ppid)
    marker, marker_error = _live_marker(root)
    return {
        "started_at": datetime.now().astimezone().isoformat(),
        "pid": os.getpid(),
        # `sys.executable`, which in a venv reports the venv's path by design
        # and NOT the binary actually running — measured: this process reports
        # `.venv\Scripts\pythonw.exe` while `Win32_Process.ExecutablePath` for
        # the same pid says `C:\Python314\pythonw.exe`.
        #
        # Recorded anyway because it names the environment, but the field that
        # tells a venv redirector from the interpreter it launches is the WMI
        # `exe` on the parent record below. That distinction is what showed a
        # parent and child sharing one command line to be a redirector pair
        # rather than the supervisor or reloader they resemble.
        "exe": sys.executable,
        "argv": list(sys.argv),
        "ppid": ppid,
        "parent": parent,
        "parent_error": parent_error,
        # What the loop was doing at this instant, which is the only thing
        # that tells two restarts through the same script apart.
        "marker": marker,
        "marker_error": marker_error,
    }


def record_start(data_dir: Path, root: Path) -> dict:
    """Append this start to the record. Never raises into the server."""
    rec = start_record(root)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with (data_dir / FILENAME).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError as exc:                                   # noqa: BLE001
        # A server that refuses to start because it could not write its own
        # provenance would be a worse product than one that cannot say what
        # started it.
        rec["write_error"] = f"{type(exc).__name__}: {exc}"
    return rec
