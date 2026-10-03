"""Unit tests for the MCP tool logic. No network: HTTP calls are faked.

Run: pytest -q
"""

from unittest.mock import MagicMock, patch

from mcp_server import local_services as ls

POSTCODE_JSON = {"result": {
    "postcode": "IG11 7QJ", "admin_district": "Barking and Dagenham",
    "admin_ward": "Abbey", "region": "London", "country": "England",
    "parliamentary_constituency": "Barking", "latitude": 51.5362, "longitude": 0.0817,
}}


def fake_response(status=200, payload=None):
    r = MagicMock(status_code=status)
    r.json.return_value = payload or {}
    r.raise_for_status.return_value = None
    return r


def test_normalise_postcode():
    assert ls.normalise_postcode("ig117qj") == "IG11 7QJ"
    assert ls.normalise_postcode(" sw1a  1aa ") == "SW1A 1AA"


def test_invalid_postcode_rejected_without_network():
    with patch.object(ls.requests, "get") as get:
        assert "error" in ls.lookup_postcode("hello")
        get.assert_not_called()


def test_lookup_postcode_returns_council():
    with patch.object(ls.requests, "get", return_value=fake_response(200, POSTCODE_JSON)):
        out = ls.lookup_postcode("ig11 7qj")
    assert out["council"] == "Barking and Dagenham"
    assert out["region"] == "London"


def test_unknown_postcode():
    with patch.object(ls.requests, "get", return_value=fake_response(404)):
        assert "not found" in ls.lookup_postcode("ZZ99 9ZZ")["error"]


def test_nearby_services_sorted_and_deduplicated():
    overpass = {"elements": [
        {"type": "node", "id": 1, "lat": 51.55, "lon": 0.09, "tags": {"name": "Far Pharmacy"}},
        {"type": "way", "id": 2, "center": {"lat": 51.5363, "lon": 0.0818},
         "tags": {"name": "Near Pharmacy", "opening_hours": "Mo-Sa 09:00-18:00"}},
        {"type": "node", "id": 3, "lat": 51.5364, "lon": 0.0819, "tags": {"name": "Near Pharmacy"}},
        {"type": "node", "id": 4, "lat": 51.54, "lon": 0.08, "tags": {}},  # no name: skipped
    ]}
    with patch.object(ls.requests, "get", return_value=fake_response(200, POSTCODE_JSON)), \
         patch.object(ls.requests, "post", return_value=fake_response(200, overpass)):
        out = ls.find_nearby_services("IG11 7QJ", "pharmacy")
    names = [r["name"] for r in out["results"]]
    assert names == ["Near Pharmacy", "Far Pharmacy"]
    assert out["results"][0]["distance_m"] < out["results"][1]["distance_m"]


def test_unknown_service_type():
    assert "error" in ls.find_nearby_services("IG11 7QJ", "casino")


def test_overpass_query_contains_all_tags():
    q = ls.build_overpass_query(ls.SERVICE_TAGS["gp"], 51.5, 0.08, 1000)
    assert '"amenity"="doctors"' in q and '"healthcare"="doctor"' in q
    assert "around:1000,51.5,0.08" in q
