"""Load the 21550 map: one ZCTA polygon and the Maryland block groups that touch it.

The national ZCTA shapefile is about 500 MB. This module asks Census TIGERweb
for the single 21550 polygon instead. Maryland block groups are the 9 MB state
file ``tl_2024_24_bg.zip``.

Intersection is computed in longitude/latitude, where "overlaps" does not
depend on a projection. The kept shapes are then projected to the local UTM
zone so later distances are in meters.
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry


ZCTA = "21550"
MARYLAND_FIPS = "24"
TIGER_YEAR = 2024

BLOCK_GROUP_URL = (
    f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}/BG/"
    f"tl_{TIGER_YEAR}_{MARYLAND_FIPS}_bg.zip"
)
ZCTA_QUERY_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1/query"
    "?where=ZCTA5%3D%27{zcta}%27"
    "&outFields=ZCTA5,GEOID,NAME"
    "&returnGeometry=true"
    "&outSR=4326"
    "&f=geojson"
)

CACHE_DIR = Path(__file__).resolve().parent / "data" / "tiger"
WGS84 = "EPSG:4326"


@dataclass(frozen=True)
class ZoneGeometry:
    """Block groups that intersect the ZCTA, in degrees and in meters."""

    zcta: str
    metric_crs: str
    zcta_wgs84: gpd.GeoDataFrame
    block_groups_wgs84: gpd.GeoDataFrame
    zcta_meters: gpd.GeoDataFrame
    block_groups_meters: gpd.GeoDataFrame

    @property
    def geoids(self) -> list[str]:
        return self.block_groups_wgs84["geoid"].tolist()


def load_zone(
    zcta: str = ZCTA,
    state_fips: str = MARYLAND_FIPS,
    cache_dir: Path = CACHE_DIR,
) -> ZoneGeometry:
    """Download, clip to the ZCTA, and project the surviving block groups."""
    zcta_wgs84 = load_zcta(zcta, cache_dir)
    block_groups = load_state_block_groups(state_fips, cache_dir)
    kept = select_intersecting_block_groups(block_groups, zcta_wgs84)
    if kept.empty:
        raise ValueError(f"No {state_fips} block groups intersect ZCTA {zcta}")

    metric_crs = _metric_crs(kept)
    return ZoneGeometry(
        zcta=zcta,
        metric_crs=metric_crs,
        zcta_wgs84=zcta_wgs84,
        block_groups_wgs84=kept,
        zcta_meters=kept_to_crs(zcta_wgs84, metric_crs),
        block_groups_meters=kept_to_crs(kept, metric_crs),
    )


def load_zcta(zcta: str, cache_dir: Path = CACHE_DIR) -> gpd.GeoDataFrame:
    """Fetch one ZCTA polygon from TIGERweb and cache the GeoJSON."""
    path = cache_dir / f"zcta_{zcta}.geojson"
    url = ZCTA_QUERY_URL.format(zcta=zcta)
    _download(url, path)
    frame = gpd.read_file(path)
    if frame.crs is None:
        frame = frame.set_crs(WGS84)
    else:
        frame = frame.to_crs(WGS84)
    if frame.empty:
        raise ValueError(f"TIGERweb returned no polygon for ZCTA {zcta}")
    frame["geoid"] = zcta
    return frame


def load_state_block_groups(
    state_fips: str = MARYLAND_FIPS,
    cache_dir: Path = CACHE_DIR,
) -> gpd.GeoDataFrame:
    """Download one state's TIGER block-group shapefile."""
    if state_fips != MARYLAND_FIPS:
        url = (
            f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}/BG/"
            f"tl_{TIGER_YEAR}_{state_fips}_bg.zip"
        )
    else:
        url = BLOCK_GROUP_URL
    path = cache_dir / Path(url).name
    _download(url, path)

    frame = gpd.read_file(path)
    if frame.crs is None:
        frame = frame.set_crs(WGS84)
    else:
        frame = frame.to_crs(WGS84)

    geoid_column = _geoid_column(frame)
    frame["geoid"] = (
        frame[geoid_column]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(12)
    )
    return frame


def select_intersecting_block_groups(
    block_groups: gpd.GeoDataFrame,
    zcta: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Keep block groups whose polygon overlaps the ZCTA.

    A bounding-box pass runs first so the exact overlap test only sees
    nearby rows. The result is sorted by GEOID.
    """
    if block_groups.crs != zcta.crs:
        block_groups = block_groups.to_crs(zcta.crs)

    zone = _union(zcta)
    minx, miny, maxx, maxy = zone.bounds
    nearby = block_groups.cx[minx:maxx, miny:maxy]
    if nearby.empty:
        nearby = block_groups

    overlapping = nearby[nearby.geometry.intersects(zone)].copy()
    overlapping = overlapping.sort_values("geoid").reset_index(drop=True)
    return overlapping


def kept_to_crs(frame: gpd.GeoDataFrame, crs: str) -> gpd.GeoDataFrame:
    return frame.to_crs(crs)


def _metric_crs(block_groups: gpd.GeoDataFrame) -> str:
    """Local UTM zone, in meters. Web Mercator is the fallback."""
    try:
        estimated = block_groups.estimate_utm_crs()
        if estimated is not None:
            return str(estimated)
    except Exception:
        pass
    return "EPSG:3857"


def _union(frame: gpd.GeoDataFrame) -> BaseGeometry:
    geometries = frame.geometry
    if hasattr(geometries, "union_all"):
        return geometries.union_all()
    return geometries.unary_union


def _geoid_column(frame: gpd.GeoDataFrame) -> str:
    for name in ("GEOID", "GEOID20", "GEOID10"):
        if name in frame.columns:
            return name
    raise ValueError(
        "Block-group shapefile has no GEOID column. "
        f"Columns: {list(frame.columns)}"
    )


def _download(url: str, path: Path) -> Path:
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "delineo-toy-abm"})
    with urllib.request.urlopen(request, timeout=180) as response:
        temporary.write_bytes(response.read())
    if path.suffix == ".geojson":
        head = temporary.read_text(encoding="utf-8")[:300]
        if '"error"' in head and '"features"' not in head:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"TIGERweb refused the ZCTA query: {head}")
    temporary.replace(path)
    return path


if __name__ == "__main__":
    zone = load_zone()
    print(f"ZCTA {zone.zcta}")
    print(f"metric CRS: {zone.metric_crs}")
    print(f"block groups: {len(zone.geoids)}")
    for geoid in zone.geoids:
        print(geoid)
