"""Google data providers.

- PageSpeedLab: PageSpeed Insights v5 (API key, generous free quota) — lab
  Lighthouse metrics, confidence medium.
- CruxField: Chrome UX Report API (API key) — real-user field data,
  confidence high.
- SearchConsole: needs service-account OAuth (RS256 signing). To keep
  runtime dependencies at zero-crypto, it reports unavailable unless the
  optional `google-auth` package is importable AND a service-account file is
  configured. Absence = not-assessed, never a broken run.
"""

from __future__ import annotations

from typing import Any

import httpx

from clauditseo.config import Settings

from .base import NotConfigured, SourcedValue

TIMEOUT = 45.0


class PageSpeedLab:
    name = "pagespeed"
    confidence = "medium"  # lab data

    def __init__(self, cfg: Settings):
        self._key = cfg.pagespeed_api_key

    def available(self) -> bool:
        return bool(self._key)

    def metrics(self, url: str) -> dict[str, SourcedValue]:
        if not self.available():
            raise NotConfigured(self.name)
        resp = httpx.get(
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
            params={"url": url, "key": self._key, "strategy": "mobile"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        audits = (resp.json().get("lighthouseResult") or {}).get("audits", {})
        out: dict[str, SourcedValue] = {}
        for metric, audit_id in (("lcp_ms", "largest-contentful-paint"),
                                 ("cls", "cumulative-layout-shift"),
                                 ("tbt_ms", "total-blocking-time")):
            audit = audits.get(audit_id) or {}
            if audit.get("numericValue") is not None:
                out[metric] = SourcedValue(value=audit["numericValue"],
                                           source=self.name, confidence=self.confidence)
        return out


class CruxField:
    name = "crux"
    confidence = "high"  # field data

    def __init__(self, cfg: Settings):
        self._key = cfg.crux_api_key

    def available(self) -> bool:
        return bool(self._key)

    def metrics(self, url: str) -> dict[str, SourcedValue]:
        if not self.available():
            raise NotConfigured(self.name)
        resp = httpx.post(
            f"https://chromeuxreport.googleapis.com/v1/records:queryRecord?key={self._key}",
            json={"url": url},
            timeout=TIMEOUT,
        )
        if resp.status_code == 404:
            return {}  # no field data for this URL — honest absence
        resp.raise_for_status()
        record = (resp.json().get("record") or {}).get("metrics", {})
        out: dict[str, SourcedValue] = {}
        for metric, key in (("lcp_ms", "largest_contentful_paint"),
                            ("cls", "cumulative_layout_shift"),
                            ("inp_ms", "interaction_to_next_paint")):
            p75 = ((record.get(key) or {}).get("percentiles") or {}).get("p75")
            if p75 is not None:
                out[metric] = SourcedValue(value=float(p75), source=self.name,
                                           confidence=self.confidence)
        return out


class CruxHistory:
    """25 weeks of field-data trend from the CrUX History API.

    Same key as the point-in-time CrUX read, different endpoint. A single p75
    says where the page is; the series says whether it is getting worse, which
    is the question a render-path fix plan actually turns on.
    """

    name = "crux-history"
    confidence = "high"

    def __init__(self, cfg: Settings):
        self._key = cfg.crux_api_key

    def available(self) -> bool:
        return bool(self._key)

    def series(self, url: str) -> dict[str, list]:
        if not self.available():
            raise NotConfigured(self.name)
        resp = httpx.post(
            "https://chromeuxreport.googleapis.com/v1/records:queryHistoryRecord"
            f"?key={self._key}",
            json={"url": url}, timeout=TIMEOUT)
        if resp.status_code == 404:
            return {}          # no field history for this URL — honest absence
        resp.raise_for_status()
        record = (resp.json().get("record") or {}).get("metrics", {})
        out: dict[str, list] = {}
        for metric, key in (("lcp_ms", "largest_contentful_paint"),
                            ("cls", "cumulative_layout_shift"),
                            ("inp_ms", "interaction_to_next_paint")):
            points = ((record.get(key) or {}).get("percentilesTimeseries")
                      or {}).get("p75s")
            if points:
                out[metric] = [float(p) if p is not None else None
                               for p in points]
        return out


class SearchConsole:
    name = "search-console"
    confidence = "high"

    def __init__(self, cfg: Settings):
        self._sa_file = cfg.google_service_account
        try:
            import google.auth  # noqa: F401
            self._auth_possible = True
        except ImportError:
            self._auth_possible = False

    def available(self) -> bool:
        return bool(self._sa_file) and self._auth_possible

    def search_analytics(self, site_url: str, days: int = 28) -> dict[str, Any]:
        if not self.available():
            raise NotConfigured(
                "Search Console needs CLAUDITSEO_GOOGLE_SA_FILE and the optional "
                "google-auth package (pip install clauditseo[google]).")
        from datetime import date, timedelta

        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            self._sa_file,
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
        creds.refresh(Request())
        end = date.today()
        start = end - timedelta(days=days)
        resp = httpx.post(
            f"https://searchconsole.googleapis.com/webmasters/v3/sites/{httpx.QueryParams({'u': site_url})['u']}/searchAnalytics/query",
            json={"startDate": start.isoformat(), "endDate": end.isoformat(),
                  "dimensions": ["query"], "rowLimit": 100},
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def _token(self) -> str:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            self._sa_file,
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
        creds.refresh(Request())
        return creds.token

    def _query(self, property_id: str, body: dict) -> list[dict]:
        from urllib.parse import quote
        resp = httpx.post(
            "https://searchconsole.googleapis.com/webmasters/v3/sites/"
            f"{quote(property_id, safe='')}/searchAnalytics/query",
            json=body, headers={"Authorization": f"Bearer {self._token()}"},
            timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("rows", [])

    def page_decay(self, domain: str, window_days: int = 28) -> dict:
        """Per-page clicks and impressions, current window against the one
        before it. This is the difference between staleness and decay: dates
        say when a page changed, this says whether it stopped earning.

        Tries the domain property first, then the URL-prefix property —
        which one exists depends on how the site was verified, and that is
        not knowable from here.
        """
        if not self.available():
            raise NotConfigured(self.name)
        from datetime import date, timedelta
        from urllib.parse import urlsplit

        host = urlsplit(domain if "//" in domain else f"//{domain}").netloc
        bare = host[4:] if host.startswith("www.") else host
        end = date.today() - timedelta(days=2)      # GSC data lags ~2 days
        mid = end - timedelta(days=window_days)
        start = mid - timedelta(days=window_days)

        def window(prop: str, a, b) -> dict[str, dict]:
            rows = self._query(prop, {
                "startDate": a.isoformat(), "endDate": b.isoformat(),
                "dimensions": ["page"], "rowLimit": 500})
            return {r["keys"][0]: {"clicks": r["clicks"],
                                   "impressions": r["impressions"]}
                    for r in rows}

        last_error: Exception | None = None
        for prop in (f"sc-domain:{bare}", f"https://{host}/"):
            try:
                current = window(prop, mid + timedelta(days=1), end)
                previous = window(prop, start, mid)
                return {"property": prop, "window_days": window_days,
                        "current": current, "previous": previous}
            except Exception as exc:                # noqa: BLE001 - try the other form
                last_error = exc
        raise last_error  # type: ignore[misc]


#: The `match` values a Places result may be used under (item 167). Every
#: consumer compares against this set rather than one string, so a listing the
#: operator confirmed is used exactly where a website-matched one is.
CONFIRMED = frozenset({"confirmed by website", "confirmed by operator"})


class PlacesProfile:
    """Public Business Profile facts from the Places API.

    Covers the half of a local audit that a crawl cannot reach: the name,
    address, phone, categories, hours, rating and review count as Google
    actually holds them. It is the public view, so it never sees posts, Q&A,
    photos, attributes or verification status — those need the owner-level
    Business Profile API and a listing you control.

    The match is verified before anything is returned. Places is a text search
    and will happily hand back a plausible neighbour: auditing the wrong
    business is worse than auditing none, so a result whose website does not
    resolve to the site under audit comes back unconfirmed rather than used.
    """

    name = "places"
    confidence = "high"          # Google's own record of the listing
    ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
    FIELDS = ("places.id,places.displayName,places.formattedAddress,"
              "places.nationalPhoneNumber,places.internationalPhoneNumber,"
              "places.websiteUri,places.rating,places.userRatingCount,"
              "places.primaryTypeDisplayName,places.types,"
              "places.regularOpeningHours,places.googleMapsUri,"
              "places.businessStatus")

    def __init__(self, cfg: Settings):
        self._key = cfg.places_api_key

    def available(self) -> bool:
        return bool(self._key)

    @staticmethod
    def _host(url: str) -> str:
        from urllib.parse import urlsplit
        host = urlsplit(url if "//" in url else f"//{url}").netloc.lower()
        return host[4:] if host.startswith("www.") else host

    def lookup(self, query: str, expect_domain: str = "",
               confirmed_place_id: str = "") -> dict:
        """Search for one listing. Returns {} when nothing matched, and a
        result carrying `match: unconfirmed` when neither the operator nor the
        listing's website ties it to the site being audited.

        `confirmed_place_id` is the listing the operator confirmed on the site
        record (item 167). It is checked first: the operator's pick is the
        answer for the listings a website match cannot reach — no website on
        the listing, a Facebook page or booking platform in the field, or a
        multi-location business whose every listing names one domain. When it
        is not among the candidates nothing is cleared; the result says so in
        `confirmed_place_id_not_returned`, which is the sign the listing moved
        or closed, and falls back to the website check.

        Every candidate is returned in `candidates`, so the operator confirms a
        specific listing rather than whichever one was on screen."""
        if not self.available():
            raise NotConfigured(self.name)
        resp = httpx.post(
            self.ENDPOINT,
            headers={"X-Goog-Api-Key": self._key, "X-Goog-FieldMask": self.FIELDS},
            json={"textQuery": query, "maxResultCount": 3},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        places = resp.json().get("places") or []
        if not places:
            return {}

        wanted = self._host(expect_domain) if expect_domain else ""
        chosen, match = places[0], "unconfirmed"
        picked = next((p for p in places if confirmed_place_id
                       and p.get("id") == confirmed_place_id), None)
        if picked is not None:
            chosen, match = picked, "confirmed by operator"
        elif wanted:
            for place in places:
                if self._host(place.get("websiteUri") or "") == wanted:
                    chosen, match = place, "confirmed by website"
                    break
        hours = (chosen.get("regularOpeningHours") or {}).get("weekdayDescriptions")
        return {
            "match": match,
            "candidates_returned": len(places),
            "candidates": [{"place_id": p.get("id"),
                            "name": (p.get("displayName") or {}).get("text"),
                            "address": p.get("formattedAddress"),
                            "phone": p.get("nationalPhoneNumber"),
                            "website": p.get("websiteUri")} for p in places],
            "confirmed_place_id_not_returned": (
                confirmed_place_id if confirmed_place_id and picked is None else None),
            "place_id": chosen.get("id"),
            "name": (chosen.get("displayName") or {}).get("text"),
            "address": chosen.get("formattedAddress"),
            "phone": chosen.get("nationalPhoneNumber"),
            "phone_international": chosen.get("internationalPhoneNumber"),
            "website": chosen.get("websiteUri"),
            "primary_category": (chosen.get("primaryTypeDisplayName") or {}).get("text"),
            "categories": chosen.get("types"),
            "hours": hours,
            "rating": chosen.get("rating"),
            "review_count": chosen.get("userRatingCount"),
            "status": chosen.get("businessStatus"),
            "maps_url": chosen.get("googleMapsUri"),
        }
