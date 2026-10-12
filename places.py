"""OpenStreetMap places inside the ZCTA, tagged for the toy clock."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point
from shapely.ops import unary_union

from geometry import ZoneGeometry


OAKLAND_CENTER = (39.41, -79.41)
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
CACHE_DIR = Path(__file__).resolve().parent / "data" / "osm"

# First match wins. Grocery is checked before the generic shop rule.
_AMENITY_FUNCTIONS = {
    "school": "school",
    "pharmacy": "pharmacy",
    "clinic": "clinic",
    "hospital": "clinic",
}
_GROCERY_SHOPS = {"supermarket", "convenience"}


@dataclass(frozen=True)
class Place:
    place_id: str
    name: str
    latitude: float
    longitude: float
    function: str
    cbg: str | None
    placeholder: bool = False


def load_places(zone: ZoneGeometry, cache_dir: Path = CACHE_DIR) -> list[Place]:
    """Download OSM points inside the ZCTA and number them P1, P2, ..."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"overpass_{zone.zcta}.json"
    payload = _cached_overpass(path, zone.zcta_wgs84.total_bounds)
    raw = [_element_place(element) for element in payload.get("elements", [])]
    inside = [place for place in raw if place is not None and _inside(zone, place[1], place[2])]
    tagged = [
        (name, lat, lon, function, False)
        for name, lat, lon, function in inside
        if function is not None
    ]
    tagged.extend(_placeholders(tagged))
    tagged.sort(key=lambda item: (item[3], item[0], item[1], item[2]))
    return [
        Place(
            place_id=f"P{index}",
            name=name,
            latitude=lat,
            longitude=lon,
            function=function,
            cbg=_containing_cbg(zone, lon, lat),
            placeholder=placeholder,
        )
        for index, (name, lat, lon, function, placeholder) in enumerate(tagged, start=1)
    ]


def classify_tags(tags: dict) -> str | None:
    """Map one OSM tag set onto school, grocery, pharmacy, clinic, or workplace."""
    amenity = _tag(tags, "amenity")
    shop = _tag(tags, "shop")
    office = _tag(tags, "office")
    if amenity in _AMENITY_FUNCTIONS:
        return _AMENITY_FUNCTIONS[amenity]
    if shop in _GROCERY_SHOPS:
        return "grocery"
    if shop or office:
        return "workplace"
    return None


def _placeholders(places: list[tuple]) -> list[tuple]:
    present = {function for *_, function, _placeholder in places}
    added = []
    latitude, longitude = OAKLAND_CENTER
    if "school" not in present:
        added.append(("Placeholder school (no OSM school in 21550)", latitude, longitude, "school", True))
    if "grocery" not in present:
        added.append(("Placeholder grocery (no OSM grocery in 21550)", latitude, longitude, "grocery", True))
    return added


def _element_place(element: dict) -> tuple[str, float, float, str | None] | None:
    tags = element.get("tags") or {}
    function = classify_tags(tags)
    if function is None:
        return None
    lat = element.get("lat")
    lon = element.get("lon")
    center = element.get("center") or {}
    if lat is None or lon is None:
        lat = center.get("lat")
        lon = center.get("lon")
    if lat is None or lon is None:
        return None
    name = _tag(tags, "name") or function
    return name, float(lat), float(lon), function


def _inside(zone: ZoneGeometry, latitude: float, longitude: float) -> bool:
    point = _to_metric(zone.metric_crs, longitude, latitude)
    outline = unary_union(list(zone.zcta_meters.geometry))
    return bool(outline.covers(point))


def _containing_cbg(zone: ZoneGeometry, longitude: float, latitude: float) -> str | None:
    point = Point(longitude, latitude)
    for _, row in zone.block_groups_wgs84.iterrows():
        if row.geometry.covers(point):
            return str(row["geoid"])
    return None


def _to_metric(metric_crs: str, longitude: float, latitude: float) -> Point:
    transformer = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)
    easting, northing = transformer.transform(longitude, latitude)
    return Point(easting, northing)


def _tag(tags: dict, key: str) -> str | None:
    value = tags.get(key)
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _cached_overpass(path: Path, bounds) -> dict:
    if path.exists() and path.stat().st_size > 0:
        return json.loads(path.read_text(encoding="utf-8"))
    west, south, east, north = bounds
    bbox = f"{south},{west},{north},{east}"
    query = f"""
[out:json][timeout:90];
(
  node["amenity"~"^(school|pharmacy|clinic|hospital)$"]({bbox});
  way["amenity"~"^(school|pharmacy|clinic|hospital)$"]({bbox});
  node["shop"]({bbox});
  way["shop"]({bbox});
  node["office"]({bbox});
  way["office"]({bbox});
);
out center;
"""
    encoded = urllib.parse.urlencode({"data": query}).encode("utf-8")
    request = urllib.request.Request(
        OVERPASS_URL,
        data=encoded,
        headers={"User-Agent": "delineo-toy-abm"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
    parsed = json.loads(payload)
    path.write_bytes(payload)
    return parsed
