import random
from datetime import datetime

from export import people_at, to_papdata
from model import TUESDAY, choose_location, run_clock
from places import Place
from population import Home, Person, Town


def _person(person_id: str, role: str) -> Person:
    return Person(
        person_id=person_id,
        home_id="H1",
        home_cbg="240230006001",
        sex=0,
        age=10 if role == "student" else 40,
        role=role,
        school_id="Pschool" if role == "student" else None,
        work_id="Pwork" if role == "worker" else None,
        grocery_id="Pgrocery",
    )


def _town(people: list[Person]) -> Town:
    homes = (Home("H1", "240230006001", 39.41, -79.41, len(people)),)
    places = (
        Place("Pschool", "School", 39.41, -79.41, "school", "240230006001"),
        Place("Pwork", "Shop", 39.41, -79.41, "workplace", "240230006001"),
        Place("Pgrocery", "Market", 39.41, -79.41, "grocery", "240230006001"),
    )
    return Town(tuple(people), homes, places)


def test_tuesday_morning_and_evening_and_saturday_grocery():
    people = [_person("1", "student"), _person("2", "worker"), _person("3", "home")]
    patterns = run_clock(_town(people), start=TUESDAY, hours=20, seed=1)

    assert people_at(patterns, 600, "1") == ("place", "Pschool")
    assert people_at(patterns, 600, "2") == ("place", "Pwork")
    assert people_at(patterns, 600, "3") == ("home", "H1")

    assert people_at(patterns, 1200, "1") == ("home", "H1")
    assert people_at(patterns, 1200, "2") == ("home", "H1")

    crowd = [_person(str(index), "home") for index in range(80)]
    saturday = run_clock(_town(crowd), start=TUESDAY, hours=4 * 24 + 11, seed=1)
    at_grocery = sum(
        1 for person in crowd if people_at(saturday, 6420, person.person_id)[0] == "place"
    )
    assert 0 < at_grocery < len(crowd)

    at_rule = 0
    for index in range(200):
        person = _person(str(index), "home")
        kind, _location = choose_location(person, datetime(2024, 1, 6, 11), random.Random(index))
        if kind == "place":
            at_rule += 1
    assert 0 < at_rule < 200


def test_papdata_shape():
    town = _town([_person("1", "student")])
    payload = to_papdata(town)
    assert payload["people"]["1"]["sex"] == 0
    assert payload["people"]["1"]["home"] == "H1"
    assert payload["homes"]["H1"]["cbg"] == "240230006001"
    assert payload["places"]["Pschool"]["top_category"] == "school"
    assert "catchment_fj" not in payload["places"]["Pschool"]
