"""Synthetic households. Block groups supply counts. This module invents the ids."""

from __future__ import annotations

import random
from dataclasses import dataclass

from pyproj import Transformer
from shapely.geometry import Point

from census import BlockGroupCensus, CensusCounts, CountyHouseholds, SexAgeCount
from geometry import ZoneGeometry
from places import Place


STUDENT_MIN_AGE = 5
STUDENT_MAX_AGE = 17
WORKER_PROBABILITY_18_64 = 0.65
WORKER_PROBABILITY_65_PLUS = 0.10


@dataclass(frozen=True)
class Home:
    home_id: str
    cbg: str
    latitude: float
    longitude: float
    members: int


@dataclass(frozen=True)
class Person:
    person_id: str
    home_id: str
    home_cbg: str
    sex: int
    age: int
    role: str
    school_id: str | None
    work_id: str | None
    grocery_id: str | None


@dataclass(frozen=True)
class Town:
    people: tuple[Person, ...]
    homes: tuple[Home, ...]
    places: tuple[Place, ...]


def build_town(
    zone: ZoneGeometry,
    census: CensusCounts,
    places: list[Place],
    seed: int = 42,
) -> Town:
    """Fill each block group, then pin school, work, and grocery ids once."""
    rng = random.Random(seed)
    to_wgs84 = Transformer.from_crs(zone.metric_crs, "EPSG:4326", always_xy=True)
    metric_by_geoid = {
        str(row["geoid"]): row.geometry
        for _, row in zone.block_groups_meters.iterrows()
    }
    schools = [place for place in places if place.function == "school"]
    groceries = [place for place in places if place.function == "grocery"]
    workplaces = [place for place in places if place.function == "workplace"]
    school_points = [_metric_point(zone.metric_crs, place) for place in schools]
    grocery_points = [_metric_point(zone.metric_crs, place) for place in groceries]

    people: list[Person] = []
    homes: list[Home] = []
    next_person = 1
    next_home = 1
    for geoid, block in census.block_groups.items():
        polygon = metric_by_geoid.get(geoid)
        if polygon is None:
            raise ValueError(f"No meter polygon for block group {geoid}")
        remaining = block.population
        while remaining > 0:
            members = _household_members(block, census.households, remaining, rng)
            point = _point_inside(polygon, rng)
            longitude, latitude = to_wgs84.transform(point.x, point.y)
            home_id = f"H{next_home}"
            next_home += 1
            drafted = []
            for sex, age in members:
                role = _role(age, rng)
                drafted.append((sex, age, role))
            school_id = _nearest(point, schools, school_points) if any(role == "student" for *_, role in drafted) else None
            grocery_id = _nearest(point, groceries, grocery_points)
            for sex, age, role in drafted:
                work_id = rng.choice(workplaces).place_id if role == "worker" and workplaces else None
                people.append(Person(
                    person_id=str(next_person),
                    home_id=home_id,
                    home_cbg=geoid,
                    sex=0 if sex == "M" else 1,
                    age=age,
                    role=role,
                    school_id=school_id if role == "student" else None,
                    work_id=work_id,
                    grocery_id=grocery_id,
                ))
                next_person += 1
            homes.append(Home(home_id, geoid, float(latitude), float(longitude), len(drafted)))
            remaining -= len(drafted)
    return Town(tuple(people), tuple(homes), tuple(places))


def _household_members(
    block: BlockGroupCensus,
    county: CountyHouseholds,
    remaining: int,
    rng: random.Random,
) -> list[tuple[str, int]]:
    is_family = _is_family(county, rng)
    size = min(remaining, _sample_size(county, is_family, rng))
    size = max(1, size)
    child_slots = 0
    if is_family and size > 1 and _children_probability(county) > rng.random():
        child_slots = rng.randint(1, size - 1)
    adult_slots = size - child_slots
    members = [_sample_demographics(block.sex_age, 18, 95, rng) for _ in range(adult_slots)]
    members.extend(_sample_demographics(block.sex_age, 0, 17, rng) for _ in range(child_slots))
    return members


def _is_family(county: CountyHouseholds, rng: random.Random) -> bool:
    if county.total_households <= 0:
        return False
    return rng.random() < (county.family_households / county.total_households)


def _children_probability(county: CountyHouseholds) -> float:
    if county.total_family_households <= 0:
        return 0.0
    return county.with_children_under_18 / county.total_family_households


def _sample_size(county: CountyHouseholds, is_family: bool, rng: random.Random) -> int:
    counts = county.family_size_counts if is_family else county.nonfamily_size_counts
    sizes = [size for size, count in counts.items() if count > 0]
    if not sizes:
        return 2 if is_family else 1
    weights = [counts[size] for size in sizes]
    return int(rng.choices(sizes, weights=weights, k=1)[0])


def _sample_demographics(
    buckets: tuple[SexAgeCount, ...],
    min_age: int,
    max_age: int,
    rng: random.Random,
) -> tuple[str, int]:
    eligible = [
        bucket for bucket in buckets
        if bucket.count > 0 and bucket.max_age >= min_age and bucket.min_age <= max_age
    ]
    if not eligible:
        return rng.choice(("M", "F")), rng.randint(min_age, max_age)
    bucket = rng.choices(eligible, weights=[item.count for item in eligible], k=1)[0]
    low = max(min_age, bucket.min_age)
    high = min(max_age, bucket.max_age)
    return bucket.sex, rng.randint(low, high)


def _role(age: int, rng: random.Random) -> str:
    if STUDENT_MIN_AGE <= age <= STUDENT_MAX_AGE:
        return "student"
    if 18 <= age <= 64 and rng.random() < WORKER_PROBABILITY_18_64:
        return "worker"
    if age >= 65 and rng.random() < WORKER_PROBABILITY_65_PLUS:
        return "worker"
    return "home"


def _point_inside(polygon, rng: random.Random) -> Point:
    minx, miny, maxx, maxy = polygon.bounds
    for _ in range(1000):
        point = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
        if polygon.covers(point):
            return point
    fallback = polygon.representative_point()
    return Point(fallback.x, fallback.y)


def _metric_point(metric_crs: str, place: Place) -> Point:
    transformer = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)
    easting, northing = transformer.transform(place.longitude, place.latitude)
    return Point(easting, northing)


def _nearest(origin: Point, places: list[Place], points: list[Point]) -> str | None:
    if not places:
        return None
    chosen = min(zip(places, points), key=lambda item: origin.distance(item[1]))
    return chosen[0].place_id
