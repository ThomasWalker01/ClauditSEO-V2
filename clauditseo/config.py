"""Runtime configuration.

Settings come from environment variables. Provider credentials may also come
from the operator's own store, which the admin panel writes and which wins
over the environment — see `clauditseo.secrets` for why that direction and
not the other. Neither path puts a secret in the database or the repo: the
store is a separate file beside the database, and it is gitignored.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


#: The one prefix. A second lookup under the pre-rename name was carried for
#: one release so an existing install would not go dark on upgrade; it is
#: gone, and an operator still setting the old variable now sees the setting
#: as unconfigured rather than silently working. That is the intended
#: outcome: a name that half-works is harder to diagnose than one that does
#: not work at all.
PREFIX = "CLAUDITSEO_"

#: The pre-rename name of the API token, kept for one purpose only: noticing
#: that an install is still configured under it. It is never read as a value.
LEGACY_TOKEN_ENV = "AUDITDECK_TOKEN"


def stale_legacy_token() -> bool:
    """Is this install still carrying the API token under the old name?

    Closing the compatibility window made `settings().api_token` empty for
    such an install — and an empty token means *open local mode*, so a
    deployment that required a credential before the upgrade required none
    after it. The access control did not move; it vanished, silently, and the
    only notice was a CHANGELOG entry in a repository the operator updates by
    pulling.

    Detected rather than resolved. Honouring the old name would reopen the
    window this closed; failing open would keep the hole. Failing closed with
    the rename named is the third option, and the rename is the whole remedy
    — `CLAUDITSEO_TOKEN` is deliberately outside `secrets.MANAGED`, so the
    admin panel cannot set it and a shell is the only route.
    """
    return (bool(os.environ.get(LEGACY_TOKEN_ENV, "").strip())
            and not from_environment(PREFIX + "TOKEN"))


STALE_TOKEN_DETAIL = (
    "This install sets AUDITDECK_TOKEN, which is no longer read. Rename it to "
    "CLAUDITSEO_TOKEN and restart, or the API would otherwise be served with "
    "no authentication at all. Refusing rather than opening."
)


def from_environment(name: str) -> str:
    """What the environment supplies for a setting.

    Public because the admin panel has to answer "is this also set outside
    the app?", and answering it by reading `os.environ` alone would be wrong
    on the platform this mostly runs on: a key set with `setx` lives in the
    registry and never reaches an already-running process. That is exactly
    the key an operator cannot see and cannot explain, so the question has to
    be asked of the same sources the value is read from.
    """
    value = os.environ.get(name, "").strip()
    if value:
        return value
    # Windows: `setx` writes to the user registry, which processes started
    # before it never inherit. Fall back so keys work without a restart.
    # Tests set CLAUDITSEO_NO_ENV_FALLBACK=1 so the suite never reads the
    # developer's own keys — otherwise "this provider is unconfigured"
    # assertions pass or fail depending on whose machine runs them.
    if (os.name == "nt"
            and os.environ.get("CLAUDITSEO_NO_ENV_FALLBACK") != "1"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                try:
                    reg_value, _ = winreg.QueryValueEx(key, name)
                except OSError:
                    return ""
                if str(reg_value).strip():
                    return str(reg_value).strip()
        except OSError:
            pass
    return ""


def _env(name: str, default: str = "") -> str:
    # The operator's own store first. It has to outrank the environment: a
    # key set in the admin panel that loses to an invisible stale one would
    # show as configured and still fail every request, which is the exact
    # situation the panel exists to get out of. Only the managed credential
    # names can be in there — see clauditseo.secrets.MANAGED — so nothing
    # like the database path or the auth token is reachable this way.
    from clauditseo import secrets as secret_store
    stored = secret_store.load()
    value = stored.get(name, "").strip()
    if value:
        return value
    return from_environment(name) or default.strip()


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(
        default_factory=lambda: Path(_env("CLAUDITSEO_DB", str(ROOT / "data" / "clauditseo.db")))
    )
    port: int = field(default_factory=lambda: int(_env("CLAUDITSEO_PORT", "8020")))
    default_locale: str = field(default_factory=lambda: _env("CLAUDITSEO_LOCALE", "en-AU"))
    # Single-operator auth: set CLAUDITSEO_TOKEN to require Bearer auth on /api/*.
    api_token: str = field(default_factory=lambda: _env("CLAUDITSEO_TOKEN"))
    # 'anthropic' (default) or 'mock' — mock enables the analyst band and chat
    # without any key, spending nothing (useful for demos and tests).
    llm_provider: str = field(default_factory=lambda: _env("CLAUDITSEO_LLM_PROVIDER", "anthropic"))

    # Provider keys — all optional. Absence lowers confidence, never breaks a run.
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    pagespeed_api_key: str = field(default_factory=lambda: _env("CLAUDITSEO_PAGESPEED_KEY"))
    crux_api_key: str = field(default_factory=lambda: _env("CLAUDITSEO_CRUX_KEY"))
    # Places is billed per request, unlike the two above. It supplies the
    # public Business Profile record — never posts, Q&A, photos or attributes,
    # which need the owner-level API and a listing you control.
    places_api_key: str = field(default_factory=lambda: _env("CLAUDITSEO_PLACES_KEY"))
    moz_token: str = field(default_factory=lambda: _env("CLAUDITSEO_MOZ_TOKEN"))
    openpagerank_key: str = field(default_factory=lambda: _env("CLAUDITSEO_OPENPAGERANK_KEY"))
    dataforseo_login: str = field(default_factory=lambda: _env("CLAUDITSEO_DATAFORSEO_LOGIN"))
    dataforseo_password: str = field(default_factory=lambda: _env("CLAUDITSEO_DATAFORSEO_PASSWORD"))
    bing_webmaster_key: str = field(default_factory=lambda: _env("CLAUDITSEO_BING_KEY"))
    # Google Search Console / GA4 use a service-account JSON file path, not a raw key.
    google_service_account: str = field(default_factory=lambda: _env("CLAUDITSEO_GOOGLE_SA_FILE"))

    # LLM analyst budgets (tokens per run). T1 never invokes the analyst layer.
    # Model tiers. Work is routed by what the task actually needs: applying a
    # fixed checklist is not the same job as calling intent overlap, and
    # paying premium rates for the former is waste. Any tool's tier can be
    # overridden per run from the dashboard.
    llm_model: str = field(default_factory=lambda: _env("CLAUDITSEO_LLM_MODEL", "claude-sonnet-5"))
    llm_model_fast: str = field(
        default_factory=lambda: _env("CLAUDITSEO_LLM_MODEL_FAST",
                                     "claude-haiku-4-5-20251001"))
    llm_model_deep: str = field(
        default_factory=lambda: _env("CLAUDITSEO_LLM_MODEL_DEEP", "claude-opus-5"))

    def model_for_tier(self, tier: str) -> str:
        return {"fast": self.llm_model_fast,
                "deep": self.llm_model_deep}.get(tier, self.llm_model)
    llm_budget_t2: int = field(default_factory=lambda: int(_env("CLAUDITSEO_LLM_BUDGET_T2", "50000")))
    llm_budget_t3: int = field(default_factory=lambda: int(_env("CLAUDITSEO_LLM_BUDGET_T3", "200000")))
    # One on-demand page advisory. The bundle is resent on every tool round,
    # so this needs headroom for two or three rounds plus a long structured
    # answer — too tight and the loop stops before the model replies.
    llm_budget_page: int = field(default_factory=lambda: int(_env("CLAUDITSEO_LLM_BUDGET_PAGE", "60000")))
    # Optional dollar conversion for the cost log, operator-supplied so no
    # price is ever invented: "model:input/output,..." in $ per million tokens,
    # e.g. CLAUDITSEO_MODEL_PRICES="claude-sonnet-5:3.00/15.00"
    model_prices: dict = field(default_factory=lambda: _parse_prices(_env("CLAUDITSEO_MODEL_PRICES")))
    # Monthly spend guardrails, either unit. Zero means no cap. Warnings only —
    # nothing is refused, because a hard stop mid-sweep helps nobody.
    monthly_budget_tokens: int = field(
        default_factory=lambda: int(_env("CLAUDITSEO_MONTHLY_BUDGET_TOKENS", "0")))
    monthly_budget_usd: float = field(
        default_factory=lambda: float(_env("CLAUDITSEO_MONTHLY_BUDGET_USD", "0")))
    # IndexNow closes the fix loop with search engines: when a run verifies a
    # finding fixed, the affected URLs are submitted for recrawl. Free key,
    # generated at indexnow.org; the key file must be hosted at the site root.
    indexnow_key: str = field(default_factory=lambda: _env("CLAUDITSEO_INDEXNOW_KEY"))
    # Watched folder for Screaming Frog CLI exports. Files named
    # <host>.csv (e.g. www.acme.com.au.csv) are matched to the site with
    # that host, imported as evidence runs, and moved to done/ or failed/.
    # Empty means no watching — the manual upload always works.
    sf_import_dir: str = field(default_factory=lambda: _env("CLAUDITSEO_SF_IMPORT_DIR"))
    # Escape hatch for auditing staging/local targets whose host differs from
    # the site record's domain.
    allow_arbitrary_start_url: bool = field(
        default_factory=lambda: _env("CLAUDITSEO_ALLOW_ARBITRARY_START_URL") == "1")


def _parse_prices(raw: str) -> dict:
    prices: dict = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry or "/" not in entry:
            continue
        model, _, pair = entry.partition(":")
        try:
            input_price, output_price = (float(x) for x in pair.split("/", 1))
            prices[model.strip()] = (input_price, output_price)
        except ValueError:
            continue
    return prices


def settings() -> Settings:
    """Read settings fresh from the environment (cheap; keeps tests honest)."""
    return Settings()
