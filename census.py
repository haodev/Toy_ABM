"""ACS 5-year counts for the block groups inside ZCTA 21550.

Garrett County is too small for ACS 1-year tables. This module calls the
5-year API only and does not use the Algorithms Census client.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from geometry import ZoneGeometry


ACS5_URL = "https://api.census.gov/data/2023/acs/acs5"
GARRETT_STATE = "24"
GARRETT_COUNTY = "023"
POPULATION_CODE = "B01003_001E"

# Same age cuts as Algorithms/server/cbg_demographics.py. B01001_026E is the
# female total, so it is not a bucket.
_MALE_AGES = (
    (3, 0, 4), (4, 5, 9), (5, 10, 14), (6, 15, 17), (7, 18, 19), (8, 20, 20),
    (9, 21, 21), (10, 22, 24), (11, 25, 29), (12, 30, 34), (13, 35, 39),
    (14, 40, 44), (15, 45, 49), (16, 50, 54), (17, 55, 59), (18, 60, 61),
    (19, 62, 64), (20, 65, 66), (21, 67, 69), (22, 70, 74), (23, 75, 79),
    (24, 80, 84), (25, 85, 100),
)
_FEMALE_AGES = (
    (27, 0, 4), (28, 5, 9), (29, 10, 14), (30, 15, 17), (31, 18, 19),
    (32, 20, 20), (33, 21, 21), (34, 22, 24), (35, 25, 29), (36, 30, 34),
    (37, 35, 39), (38, 40, 44), (39, 45, 49), (40, 50, 54), (41, 55, 59),
    (42, 60, 61), (43, 62, 64), (44, 65, 66), (45, 67, 69), (46, 70, 74),
    (47, 75, 79), (48, 80, 84), (49, 85, 100),
)
SEX_AGE_BUCKETS = tuple(
    (f"B01001_{number:03d}E", sex, low, high)
    for sex, rows in (("M", _MALE_AGES), ("F", _FEMALE_AGES))
    for number, low, high in rows
)

# B11001, B11016, and B11003. Codes match CensusDataPuller.variables_detailed.
HOUSEHOLD_CODES = {
    "total_households": "B11001_001E",
    "family_households": "B11001_002E",
    "nonfamily_households": "B11001_007E",
    "total_family_households": "B11003_001E",
    "married_with_children": "B11003_003E",
    "single_father_with_children": "B11003_010E",
    "single_mother_with_children": "B11003_016E",
    "size_2": "B11016_003E",
    "size_3": "B11016_004E",
    "size_4": "B11016_005E",
    "size_5": "B11016_006E",
    "size_6": "B11016_007E",
    "size_7_plus": "B11016_008E",
    "nonfamily_size_1": "B11016_010E",
    "nonfamily_size_2": "B11016_011E",
    "nonfamily_size_3": "B11016_012E",
    "nonfamily_size_4": "B11016_013E",
    "nonfamily_size_5": "B11016_014E",
    "nonfamily_size_6": "B11016_015E",
    "nonfamily_size_7_plus": "B11016_016E",
}
CHILD_PARTS = (
    "married_with_children",
    "single_father_with_children",
    "single_mother_with_children",
)

CACHE_DIR = Path(__file__).resolve().parent / "data" / "census"


@dataclass(frozen=True)
class SexAgeCount:
    sex: str
    min_age: int
    max_age: int
    count: int


@dataclass(frozen=True)
class BlockGroupCensus:
    geoid: str
    population: int
    sex_age: tuple[SexAgeCount, ...]


@dataclass(frozen=True)
class CountyHouseholds:
    total_households: int
    family_households: int
    nonfamily_households: int
    total_family_households: int
    with_children_under_18: int
    family_size_counts: dict[int, int]
    nonfamily_size_counts: dict[int, int]


@dataclass(frozen=True)
class CensusCounts:
    block_groups: dict[str, BlockGroupCensus]
    households: CountyHouseholds


def load_census(
    zone: ZoneGeometry,
    cache_dir: Path = CACHE_DIR,
    api_key: str | None = None,
) -> CensusCounts:
    """Attach ACS population, age, sex, and county household shape to a zone."""
    wanted = list(zone.geoids)
    _require_garrett(wanted)
    cache_dir.mkdir(parents=True, exist_ok=True)
    block_table = _cached_table(
        cache_dir / "acs5_2023_bg_24023.json",
        _block_group_params(api_key),
    )
    county_table = _cached_table(
        cache_dir / "acs5_2023_county_24023.json",
        _county_params(api_key),
    )
    return CensusCounts(
        block_groups=parse_block_group_response(block_table, wanted),
        households=parse_household_response(county_table),
    )


def parse_block_group_response(table: list, wanted: list[str]) -> dict[str, BlockGroupCensus]:
    """Keep wanted GEOIDs and drop the rest of the county."""
    header, rows = _split_table(table)
    index = {name: position for position, name in enumerate(header)}
    _require_columns(index, [POPULATION_CODE, "state", "county", "tract", "block group"])
    _require_columns(index, [code for code, *_ in SEX_AGE_BUCKETS])

    found: dict[str, BlockGroupCensus] = {}
    for row in rows:
        geoid = _geoid(
            row[index["state"]],
            row[index["county"]],
            row[index["tract"]],
            row[index["block group"]],
        )
        if geoid not in wanted:
            continue
        population = _count(row[index[POPULATION_CODE]], f"{geoid} {POPULATION_CODE}")
        buckets = tuple(
            SexAgeCount(sex, low, high, _count(row[index[code]], f"{geoid} {code}"))
            for code, sex, low, high in SEX_AGE_BUCKETS
        )
        found[geoid] = BlockGroupCensus(geoid, population, buckets)

    missing = [geoid for geoid in wanted if geoid not in found]
    if missing:
        raise ValueError(f"ACS 5-year has no block group row for {missing}")
    return {geoid: found[geoid] for geoid in wanted}


def parse_household_response(table: list) -> CountyHouseholds:
    """Read the Garrett County household row and sum the three child lines."""
    header, rows = _split_table(table)
    index = {name: position for position, name in enumerate(header)}
    _require_columns(index, ["state", "county", *HOUSEHOLD_CODES.values()])
    match = [
        row for row in rows
        if str(row[index["state"]]).zfill(2) == GARRETT_STATE
        and str(row[index["county"]]).zfill(3) == GARRETT_COUNTY
    ]
    if len(match) != 1:
        raise ValueError(f"Expected one Garrett County household row, found {len(match)}")
    row = match[0]
    values = {
        name: _count(row[index[code]], code)
        for name, code in HOUSEHOLD_CODES.items()
    }
    return CountyHouseholds(
        total_households=values["total_households"],
        family_households=values["family_households"],
        nonfamily_households=values["nonfamily_households"],
        total_family_households=values["total_family_households"],
        with_children_under_18=sum(values[name] for name in CHILD_PARTS),
        family_size_counts={
            2: values["size_2"],
            3: values["size_3"],
            4: values["size_4"],
            5: values["size_5"],
            6: values["size_6"],
            7: values["size_7_plus"],
        },
        nonfamily_size_counts={
            1: values["nonfamily_size_1"],
            2: values["nonfamily_size_2"],
            3: values["nonfamily_size_3"],
            4: values["nonfamily_size_4"],
            5: values["nonfamily_size_5"],
            6: values["nonfamily_size_6"],
            7: values["nonfamily_size_7_plus"],
        },
    )


def _block_group_params(api_key: str | None) -> dict[str, str]:
    codes = [POPULATION_CODE, *[code for code, *_ in SEX_AGE_BUCKETS]]
    return _params("block group:*", f"state:{GARRETT_STATE} county:{GARRETT_COUNTY}", codes, api_key)


def _county_params(api_key: str | None) -> dict[str, str]:
    return _params(
        f"county:{GARRETT_COUNTY}",
        f"state:{GARRETT_STATE}",
        list(HOUSEHOLD_CODES.values()),
        api_key,
    )


def _params(for_clause: str, in_clause: str, codes: list[str], api_key: str | None) -> dict[str, str]:
    if len(codes) + 1 > 50:
        raise ValueError(f"Census get list is over 50 variables: {len(codes) + 1}")
    params = {
        "get": "NAME," + ",".join(codes),
        "for": for_clause,
        "in": in_clause,
    }
    key = api_key if api_key is not None else os.environ.get("CENSUS_API_KEY", "")
    if key:
        params["key"] = key
    return params


def _cached_table(path: Path, params: dict[str, str]) -> list:
    if path.exists() and path.stat().st_size > 0:
        return json.loads(path.read_text(encoding="utf-8"))
    if "key" not in params:
        raise RuntimeError(
            "CENSUS_API_KEY is not set and the ACS cache is empty. "
            f"Expected cache file: {path}"
        )
    url = ACS5_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "delineo-toy-abm"})
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
    table = json.loads(payload)
    if not isinstance(table, list) or not table or isinstance(table[0], dict):
        raise RuntimeError(f"ACS returned an error instead of a table: {str(table)[:300]}")
    path.write_text(json.dumps(table), encoding="utf-8")
    return table


def _split_table(table: list) -> tuple[list, list]:
    if not table or not isinstance(table[0], list):
        raise ValueError("ACS table must be a header row plus data rows")
    return table[0], table[1:]


def _require_columns(index: dict[str, int], names: list[str]) -> None:
    missing = [name for name in names if name not in index]
    if missing:
        raise ValueError(f"ACS table is missing columns: {missing}")


def _geoid(state: object, county: object, tract: object, block_group: object) -> str:
    return (
        str(state).zfill(2)
        + str(county).zfill(3)
        + str(tract).zfill(6)
        + str(block_group).zfill(1)
    )


def _count(value: object, field: str) -> int:
    if value is None:
        raise ValueError(f"Census value missing for {field}")
    text = str(value).strip()
    if text == "" or text.lower() == "null":
        raise ValueError(f"Census value missing for {field}")
    try:
        number = int(text)
    except ValueError as exc:
        raise ValueError(f"Census value for {field} is not an integer: {value}") from exc
    if number < 0:
        raise ValueError(f"Census sentinel for {field}: {value}")
    return number


def _require_garrett(geoids: list[str]) -> None:
    foreign = [geoid for geoid in geoids if not geoid.startswith(GARRETT_STATE + GARRETT_COUNTY)]
    if foreign:
        raise ValueError(f"Toy census expects Garrett County block groups, got {foreign}")
