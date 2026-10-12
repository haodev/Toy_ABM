import pytest

from census import (
    CHILD_PARTS,
    HOUSEHOLD_CODES,
    POPULATION_CODE,
    SEX_AGE_BUCKETS,
    parse_block_group_response,
    parse_household_response,
)


WANTED = ["240230006001"]


def _header(*extra: str) -> list[str]:
    return ["NAME", POPULATION_CODE, *[code for code, *_ in SEX_AGE_BUCKETS], *extra]


def _block_row(population: str, tract: str, block_group: str, **overrides: str) -> list[str]:
    values = {code: "0" for code, *_ in SEX_AGE_BUCKETS}
    values[POPULATION_CODE] = population
    values.update(overrides)
    header = _header("state", "county", "tract", "block group")
    base = {
        "NAME": "block group",
        "state": "24",
        "county": "023",
        "tract": tract,
        "block group": block_group,
        **values,
    }
    return [base[column] for column in header]


def test_keeps_wanted_geoid_and_drops_the_rest_of_the_county():
    header = _header("state", "county", "tract", "block group")
    table = [
        header,
        _block_row("12", "000600", "1", **{SEX_AGE_BUCKETS[0][0]: "5"}),
        _block_row("99", "000900", "2"),
    ]
    parsed = parse_block_group_response(table, WANTED)
    assert list(parsed) == WANTED
    block = parsed["240230006001"]
    assert block.population == 12
    assert block.sex_age[0].count == 5
    assert block.sex_age[0].sex == "M"
    assert (block.sex_age[0].min_age, block.sex_age[0].max_age) == (0, 4)


def test_missing_kept_block_group_is_an_error():
    header = _header("state", "county", "tract", "block group")
    table = [header, _block_row("12", "000900", "2")]
    with pytest.raises(ValueError, match="240230006001"):
        parse_block_group_response(table, WANTED)


def test_negative_population_is_an_error():
    header = _header("state", "county", "tract", "block group")
    table = [header, _block_row("-666666666", "000600", "1")]
    with pytest.raises(ValueError, match="sentinel"):
        parse_block_group_response(table, WANTED)


def test_child_lines_are_summed():
    header = ["NAME", *HOUSEHOLD_CODES.values(), "state", "county"]
    row = {code: "0" for code in HOUSEHOLD_CODES.values()}
    row[HOUSEHOLD_CODES["total_households"]] = "100"
    row[HOUSEHOLD_CODES["family_households"]] = "70"
    row[HOUSEHOLD_CODES["nonfamily_households"]] = "30"
    row[HOUSEHOLD_CODES["total_family_households"]] = "70"
    row[HOUSEHOLD_CODES["married_with_children"]] = "10"
    row[HOUSEHOLD_CODES["single_father_with_children"]] = "3"
    row[HOUSEHOLD_CODES["single_mother_with_children"]] = "2"
    row["NAME"] = "Garrett County"
    row["state"] = "24"
    row["county"] = "023"
    households = parse_household_response([header, [row[column] for column in header]])
    assert households.with_children_under_18 == 15
    assert set(CHILD_PARTS) == {
        "married_with_children",
        "single_father_with_children",
        "single_mother_with_children",
    }
    assert households.family_size_counts[2] == 0
    assert households.nonfamily_size_counts[1] == 0
