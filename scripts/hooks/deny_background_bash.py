"""PreToolUse hook: a loop worker never backgrounds a Bash command.

DISCIPLINE rule 15 says the pinned suite runs in the foreground. Twice on
2026-08-23 (07:00 and 11:50) a round ran it with ``run_in_background=true``,
said "I'll wait for the completion notification", and ended its turn. In
``claude -p`` there is no notification and no later: the process ends with the
turn, the watcher scores NO-OP, the marker is orphaned and the tree is left
dirty with a half-verified fix. Prose did not hold; this does.

Claude Code calls it with the tool call as JSON on stdin. Exit 2 denies the
call and feeds stderr back to the model as the reason. Exit 0 lets it through.
Anything unexpected (no JSON, no Bash) is a pass - this hook must never be the
thing that stops a round for a reason of its own.
"""

from __future__ import annotations

import json
import sys

REASON = (
    "DENIED by .claude/settings.json (loop-kit hook): run_in_background is not "
    "available to a loop worker. You are running under `claude -p`; there is no "
    "completion notification and no later turn - a backgrounded command ends "
    "your turn, the watcher scores the run NO-OP, the marker is orphaned and "
    "the tree is left dirty (2026-08-23 07:00 and 11:50, both the pinned suite "
    "at ~77%). DISCIPLINE rule 15: run it in the foreground with "
    "timeout=600000; if it genuinely cannot finish in ten minutes, run it to a "
    "file (`> out.txt 2>&1`) in the foreground and tail the file in further "
    "foreground calls until the summary line appears."
)


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        return 0
    if not isinstance(data, dict):
        return 0
    if data.get("tool_name") != "Bash":
        return 0
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    if bool(tool_input.get("run_in_background")):
        sys.stderr.write(REASON + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
