"""Geocoding with Photon (primary) and Nominatim (fallback).

Photon (https://photon.komoot.io) is chosen as the primary because:
- No auth required, generous rate limits
- Built for autocomplete
- More reliable from cloud provider IPs than Nominatim's public server
Nominatim is kept as a fallback for single-result lookups.
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class GeocodingError(Exception):
    pass


ALLOWED_COUNTRIES = {"United States", "Canada", "Mexico"}
PHOTON_URL = "https://photon.komoot.io/api/"


def _photon_search(query: str, limit: int) -> list[dict]:
    """Search via Photon; filter to US/CA/MX. Returns [] on network error."""
    try:
        resp = requests.get(
            PHOTON_URL,
            params={"q": query, "limit": limit * 3, "lang": "en"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Photon error: %s", exc)
        return []

    results: list[dict] = []
    for feat in data.get("features", []):
        props = feat.get("properties", {}) or {}
        if props.get("country") not in ALLOWED_COUNTRIES:
            continue

        coords = feat.get("geometry", {}).get("coordinates") or []
        if len(coords) < 2:
            continue

        parts: list[str] = []
        for key in ("name", "city", "county", "state", "country"):
            val = props.get(key)
            if val and val not in parts:
                parts.append(str(val))
        display_name = ", ".join(parts) or props.get("name", query)

        results.append({
            "lat": float(coords[1]),
            "lng": float(coords[0]),
            "display_name": display_name,
        })
        if len(results) >= limit:
            break
    return results


def _nominatim_search(query: str, limit: int) -> list[dict]:
    """Fallback via Nominatim. Returns [] on any error."""
    url = f"{settings.NOMINATIM_BASE_URL}/search"
    params = {
        "q": query,
        "format": "json",
        "limit": limit,
        "addressdetails": 1,
        "countrycodes": "us,ca,mx",
    }
    headers = {"User-Agent": settings.USER_AGENT}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Nominatim error: %s", exc)
        return []

    return [
        {
            "lat": float(hit["lat"]),
            "lng": float(hit["lon"]),
            "display_name": hit["display_name"],
        }
        for hit in data
    ]


def autocomplete(query: str, limit: int = 6) -> list[dict]:
    """Return up to `limit` search suggestions (US/CA/MX only)."""
    q = (query or "").strip()
    if not q:
        return []
    results = _photon_search(q, limit)
    if not results:
        results = _nominatim_search(q, limit)
    return results


def geocode(query: str) -> dict:
    """Return the best {lat, lng, display_name} match for query."""
    q = (query or "").strip()
    if not q:
        raise GeocodingError("Empty query")
    results = _photon_search(q, limit=1)
    if not results:
        results = _nominatim_search(q, limit=1)
    if not results:
        raise GeocodingError(f"No results for '{query}'")
    return results[0]
