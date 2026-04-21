"""Geocoding via Nominatim (OpenStreetMap)."""
from __future__ import annotations

import requests
from django.conf import settings


class GeocodingError(Exception):
    pass


def geocode(query: str) -> dict:
    """Return {lat, lng, display_name} for the best match of query."""
    if not query or not query.strip():
        raise GeocodingError("Empty query")

    url = f"{settings.NOMINATIM_BASE_URL}/search"
    params = {"q": query, "format": "json", "limit": 1, "addressdetails": 1}
    headers = {"User-Agent": settings.USER_AGENT}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise GeocodingError(f"Geocoding request failed: {exc}") from exc

    data = resp.json()
    if not data:
        raise GeocodingError(f"No results for '{query}'")

    hit = data[0]
    return {
        "lat": float(hit["lat"]),
        "lng": float(hit["lon"]),
        "display_name": hit["display_name"],
    }


def autocomplete(query: str, limit: int = 5) -> list[dict]:
    """Return up to `limit` search suggestions."""
    if not query or not query.strip():
        return []

    url = f"{settings.NOMINATIM_BASE_URL}/search"
    params = {"q": query, "format": "json", "limit": limit, "addressdetails": 1}
    headers = {"User-Agent": settings.USER_AGENT}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return []

    return [
        {
            "lat": float(hit["lat"]),
            "lng": float(hit["lon"]),
            "display_name": hit["display_name"],
        }
        for hit in resp.json()
    ]
