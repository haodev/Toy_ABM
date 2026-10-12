import geopandas as gpd
from shapely.geometry import Polygon

from geometry import ZoneGeometry
from places import Place, _inside, classify_tags


def _zone() -> ZoneGeometry:
    box = Polygon([
        (-79.42, 39.40),
        (-79.40, 39.40),
        (-79.40, 39.42),
        (-79.42, 39.42),
        (-79.42, 39.40),
    ])
    wgs = gpd.GeoDataFrame({"geoid": ["240230006001"]}, geometry=[box], crs="EPSG:4326")
    zcta = gpd.GeoDataFrame({"zcta": ["21550"]}, geometry=[box], crs="EPSG:4326")
    return ZoneGeometry(
        zcta="21550",
        metric_crs="EPSG:32617",
        zcta_wgs84=zcta,
        block_groups_wgs84=wgs,
        zcta_meters=zcta.to_crs("EPSG:32617"),
        block_groups_meters=wgs.to_crs("EPSG:32617"),
    )


def test_tag_table():
    assert classify_tags({"amenity": "school"}) == "school"
    assert classify_tags({"shop": "supermarket"}) == "grocery"
    assert classify_tags({"shop": "convenience"}) == "grocery"
    assert classify_tags({"amenity": "pharmacy", "name": "Walgreens"}) == "pharmacy"
    assert classify_tags({"amenity": "hospital"}) == "clinic"
    assert classify_tags({"shop": "clothes"}) == "workplace"
    assert classify_tags({"office": "yes"}) == "workplace"
    assert classify_tags({"amenity": "restaurant"}) is None


def test_point_inside_zcta_uses_meter_polygon():
    zone = _zone()
    assert _inside(zone, 39.41, -79.41)
    assert not _inside(zone, 39.50, -79.50)


def test_place_ids_are_not_coordinates():
    place = Place("P1", "Walgreens", 39.41, -79.41, "pharmacy", "240230006001")
    assert place.place_id == "P1"
    assert place.function == "pharmacy"
