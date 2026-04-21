"""Routing via OSRM public server. Returns distance (miles), duration (hrs), geometry."""
from __future__ import annotations

import requests
from django.conf import settings


class RoutingError(Exception):
    pass


METERS_PER_MILE = 1609.344


def route(coordinates: list[tuple[float, float]]) -> dict:
    """
    coordinates: list of (lng, lat) pairs (OSRM ordering).
    Returns {miles, duration_hrs, geometry (GeoJSON LineString)}.
    """
    if len(coordinates) < 2:
        raise RoutingError("Need at least two coordinates")

    coord_str = ";".join(f"{lng},{lat}" for lng, lat in coordinates)
    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{coord_str}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "annotations": "distance,duration",
    }

    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RoutingError(f"Routing request failed: {exc}") from exc

    data = resp.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"OSRM error: {data.get('code', 'unknown')}")

    best = data["routes"][0]
    legs = best.get("legs", [])
    leg_miles = [leg["distance"] / METERS_PER_MILE for leg in legs]

    return {
        "miles": best["distance"] / METERS_PER_MILE,
        "duration_hrs": best["duration"] / 3600.0,
        "geometry": best["geometry"],
        "leg_miles": leg_miles,
    }
