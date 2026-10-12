import geopandas as gpd
from shapely.geometry import Point, Polygon

from census import (
    BlockGroupCensus,
    CensusCounts,
    CountyHouseholds,
    SexAgeCount,
)
from geometry import ZoneGeometry
from places import Place
from population import build_town


def _box_zone() -> ZoneGeometry:
    box = Polygon([
        (-79.42, 39.40),
        (-79.40, 39.40),
        (-79.40, 39.42),
        (-79.42, 39.42),
        (-79.42, 39.40),
    ])
    block = gpd.GeoDataFrame({"geoid": ["240230006001"]}, geometry=[box], crs="EPSG:4326")
    zcta = gpd.GeoDataFrame({"zcta": ["21550"]}, geometry=[box], crs="EPSG:4326")
    return ZoneGeometry(
        zcta="21550",
        metric_crs="EPSG:32617",
        zcta_wgs84=zcta,
        block_groups_wgs84=block,
        zcta_meters=zcta.to_crs("EPSG:32617"),
        block_groups_meters=block.to_crs("EPSG:32617"),
    )


def _census(population: int) -> CensusCounts:
    buckets = []
    for sex in ("M", "F"):
        buckets.append(SexAgeCount(sex, 5, 9, 50))
        buckets.append(SexAgeCount(sex, 40, 44, 50))
    return CensusCounts(
        block_groups={
            "240230006001": BlockGroupCensus("240230006001", population, tuple(buckets)),
        },
        households=CountyHouseholds(
            total_households=10,
            family_households=6,
            nonfamily_households=4,
            total_family_households=6,
            with_children_under_18=3,
            family_size_counts={2: 2, 3: 2, 4: 2, 5: 0, 6: 0, 7: 0},
            nonfamily_size_counts={1: 4, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0},
        ),
    )


def _places() -> list[Place]:
    return [
        Place("P1", "School", 39.411, -79.411, "school", "240230006001"),
        Place("P2", "Market", 39.412, -79.409, "grocery", "240230006001"),
        Place("P3", "Shop", 39.409, -79.412, "workplace", "240230006001"),
    ]


def test_fills_the_block_group_and_pins_ids_once():
    town = build_town(_box_zone(), _census(8), _places(), seed=1)
    assert len(town.people) == 8
    assert sum(home.members for home in town.homes) == 8
    polygon = _box_zone().block_groups_wgs84.geometry.iloc[0]
    for home in town.homes:
        assert polygon.covers(Point(home.longitude, home.latitude))
    for person in town.people:
        assert person.home_cbg == "240230006001"
        assert person.grocery_id == "P2"
        if person.role == "student":
            assert 5 <= person.age <= 17
            assert person.school_id == "P1"
            assert person.work_id is None
        if person.role == "worker":
            assert person.work_id == "P3"
            assert person.school_id is None
