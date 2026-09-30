from __future__ import annotations

import re
import string
from urllib.parse import urlsplit, urlunsplit

_UNRESERVED = set(string.ascii_letters + string.digits + "-._~")
_PCT = re.compile(r"%([0-9A-Fa-f]{2})")


def _normalise(component: str) -> str:
    """RFC 9309 §2.2.2 / RFC 3986: decode percent-encoded unreserved octets
    (so /pri%76ate/ compares equal to /private/) but keep reserved ones
    encoded (%2F must not become a path separator), case-normalised so
    %2f and %2F compare equal. Applied to rules and paths alike."""
    def repl(match: re.Match) -> str:
        char = chr(int(match.group(1), 16))
        return char if char in _UNRESERVED else "%" + match.group(1).upper()
    return _PCT.sub(repl, component)


class RobotsPolicy:
    """robots.txt policy with RFC 9309 rule resolution, implemented here
    rather than delegated to urllib.robotparser: older stdlib versions in
    our supported range (3.12+) resolve rules first-match-wins, which lets a
    broad `Allow: /` shadow a narrower `Disallow:`. Politeness must not
    depend on the interpreter version, so:

    - the most specific matching rule (longest pattern) wins;
    - ties go to Allow;
    - `*` wildcards and a trailing `$` anchor are honoured;
    - the most specific matching user-agent group applies, falling back to `*`;
    - no matching rule (or an empty Disallow) means allowed;
    - absent/4xx robots = allow all (web convention), 5xx = fetch nothing.
    """

    def __init__(self, robots_url: str, status: int | None, body: str | None):
        self.robots_url = robots_url
        self.status = status
        self.body = body
        self.sitemaps: list[str] = []
        self._deny_all = status is not None and 500 <= status < 600
        # agent token -> ordered list of (is_allow, pattern)
        self._groups: dict[str, list[tuple[bool, str]]] = {}
        if body and status is not None and status < 400:
            self._parse(body)

    def _parse(self, body: str) -> None:
        current_agents: list[str] = []
        collecting_agents = False
        for raw in body.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            key, _, value = line.partition(":")
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if not collecting_agents:
                    current_agents = []
                current_agents.append(value.lower())
                collecting_agents = True
            elif key in ("allow", "disallow"):
                collecting_agents = False
                for agent in current_agents:
                    self._groups.setdefault(agent, []).append((key == "allow", value))
            elif key == "sitemap":
                collecting_agents = False
                if value:
                    self.sitemaps.append(value)
            else:
                collecting_agents = False

    def allows(self, url: str, user_agent: str) -> bool:
        if self._deny_all:
            return False
        rules = self._rules_for(user_agent)
        if rules is None:
            return True
        parts = urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        path = _normalise(path)

        best_len = -1
        allowed = True
        for is_allow, pattern in rules:
            match_len = _match_specificity(pattern, path)
            if match_len is None:
                continue
            if match_len > best_len:
                best_len, allowed = match_len, is_allow
            elif match_len == best_len and is_allow:
                allowed = True  # RFC 9309: ties go to Allow
        return allowed

    def names(self, user_agent: str) -> bool:
        """Whether a group other than `*` speaks to this agent: a directive
        the site wrote for it, allow or disallow. False is "unstated"; the
        agent falls to `*` (item 145 BG, `ai-crawler-allowed-unstated`)."""
        ua = user_agent.lower()
        return any(agent != "*" and agent and agent in ua for agent in self._groups)

    def _rules_for(self, user_agent: str) -> list[tuple[bool, str]] | None:
        ua = user_agent.lower()
        specific = [agent for agent in self._groups
                    if agent != "*" and agent and agent in ua]
        if specific:
            return self._groups[max(specific, key=len)]
        return self._groups.get("*")


def _match_specificity(pattern: str, path: str) -> int | None:
    """Length of the pattern if it matches the path (RFC 9309 semantics:
    prefix match with `*` wildcards and optional trailing `$` anchor);
    None when it does not match. An empty pattern never matches, which makes
    a bare `Disallow:` mean allow-all as the RFC requires."""
    if not pattern:
        return None
    pattern = _normalise(pattern)
    anchored = pattern.endswith("$")
    core = pattern[:-1] if anchored else pattern
    regex = "^" + re.escape(core).replace(r"\*", ".*") + ("$" if anchored else "")
    return len(pattern) if re.match(regex, path) else None


def robots_url_for(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
