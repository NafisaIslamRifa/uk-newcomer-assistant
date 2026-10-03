"""Live UK lookups used by the MCP tools. Plain Python, no MCP code here,
so each function can be tested on its own.

- postcodes.io            : postcode -> council, ward, region, coordinates (free, no key)
- OpenStreetMap Overpass  : places near a point (free, no key)
"""

from __future__ import annotations

import math
import re

import requests

HEADERS = {"User-Agent": "UKNest-AI-portfolio-project/0.1 (learning project)"}
POSTCODES_API = "https://api.postcodes.io/postcodes/"
OVERPASS_API = "https://overpass-api.de/api/interpreter"

# service type -> OpenStreetMap tags that describe it
SERVICE_TAGS: dict[str, list[tuple[str, str]]] = {
    "gp": [("amenity", "doctors"), ("healthcare", "doctor")],
    "pharmacy": [("amenity", "pharmacy")],
    "dentist": [("amenity", "dentist")],
    "hospital": [("amenity", "hospital")],
    "supermarket": [("shop", "supermarket")],
    "post_office": [("amenity", "post_office")],
    "bank": [("amenity", "bank")],
    "mobile_phone_shop": [("shop", "mobile_phone")],
    "library": [("amenity", "library")],
}

UK_POSTCODE = re.compile(r"^[A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2}$")


def normalise_postcode(postcode: str) -> str:
    pc = re.sub(r"\s+", "", postcode.upper())
    return f"{pc[:-3]} {pc[-3:]}" if len(pc) > 3 else pc


def lookup_postcode(postcode: str) -> dict:
    """Return council, ward, region and coordinates for a UK postcode."""
    pc = normalise_postcode(postcode)
    if not UK_POSTCODE.match(pc):
        return {"error": f"'{postcode}' does not look like a UK postcode (e.g. IG11 7QJ)."}

    try:
        resp = requests.get(POSTCODES_API + pc.replace(" ", ""), headers=HEADERS, timeout=10)
    except requests.RequestException as exc:
        return {"error": f"Postcode service unavailable: {exc}"}
    if resp.status_code == 404:
        return {"error": f"Postcode {pc} was not found. It may be new or mistyped."}
    if resp.status_code != 200:
        return {"error": f"Postcode service returned HTTP {resp.status_code}."}

    r = resp.json()["result"]
    return {
        "postcode": r["postcode"],
        "council": r.get("admin_district"),
        "ward": r.get("admin_ward"),
        "region": r.get("region"),
        "country": r.get("country"),
        "constituency": r.get("parliamentary_constituency"),
        "latitude": r.get("latitude"),
        "longitude": r.get("longitude"),
        "source": "postcodes.io (Office for National Statistics data)",
    }


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Straight-line distance in metres (haversine)."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(2 * r * math.asin(math.sqrt(a)))


def build_overpass_query(tags: list[tuple[str, str]], lat: float, lon: float, radius_m: int) -> str:
    parts = []
    for key, value in tags:
        for element in ("node", "way"):
            parts.append(f'{element}["{key}"="{value}"](around:{radius_m},{lat},{lon});')
    return f"[out:json][timeout:25];({''.join(parts)});out center tags;"


def find_nearby_services(postcode: str, service_type: str,
                         radius_m: int = 1500, limit: int = 8) -> dict:
    """Find services of a given type near a UK postcode, nearest first."""
    if service_type not in SERVICE_TAGS:
        return {"error": f"Unknown service type. Use one of: {', '.join(SERVICE_TAGS)}"}
    radius_m = max(200, min(radius_m, 5000))

    place = lookup_postcode(postcode)
    if "error" in place:
        return place
    lat, lon = place["latitude"], place["longitude"]

    query = build_overpass_query(SERVICE_TAGS[service_type], lat, lon, radius_m)
    try:
        resp = requests.post(OVERPASS_API, data={"data": query}, headers=HEADERS, timeout=40)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except (requests.RequestException, ValueError) as exc:
        return {"error": f"Map service (OpenStreetMap) unavailable, try again shortly: {exc}"}

    results, seen = [], set()
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        e_lat = el.get("lat") or el.get("center", {}).get("lat")
        e_lon = el.get("lon") or el.get("center", {}).get("lon")
        if not name or e_lat is None or name in seen:
            continue
        seen.add(name)
        address = ", ".join(filter(None, [
            " ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street")])),
            tags.get("addr:postcode"),
        ]))
        results.append({
            "name": name,
            "distance_m": _distance_m(lat, lon, e_lat, e_lon),
            "address": address or None,
            "opening_hours": tags.get("opening_hours"),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
            "map_link": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
        })

    results.sort(key=lambda x: x["distance_m"])
    return {
        "postcode": place["postcode"],
        "council": place["council"],
        "service_type": service_type,
        "radius_m": radius_m,
        "count": len(results[:limit]),
        "results": results[:limit],
        "source": "OpenStreetMap contributors (data may be incomplete; check before visiting)",
    }
