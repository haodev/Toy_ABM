"""Write the people, homes, places, and hourly locations the simulator already reads."""

from __future__ import annotations

import json
from pathlib import Path

from model import TUESDAY, run_clock
from population import Town


def to_papdata(town: Town) -> dict:
    people = {
        person.person_id: {
            "sex": person.sex,
            "age": person.age,
            "home": person.home_id,
            "home_cbg": person.home_cbg,
        }
        for person in town.people
    }
    homes = {
        home.home_id: {
            "cbg": home.cbg,
            "members": home.members,
            "latitude": home.latitude,
            "longitude": home.longitude,
        }
        for home in town.homes
    }
    places = {
        place.place_id: {
            "label": place.name,
            "latitude": place.latitude,
            "longitude": place.longitude,
            "top_category": place.function,
        }
        for place in town.places
    }
    return {"people": people, "homes": homes, "places": places}


def write_outputs(town: Town, directory: Path, patterns: dict | None = None, seed: int = 42) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    if patterns is None:
        patterns = run_clock(town, start=TUESDAY, seed=seed)
    papdata = to_papdata(town)
    (directory / "papdata.json").write_text(json.dumps(papdata, indent=2), encoding="utf-8")
    (directory / "patterns.json").write_text(json.dumps(patterns, indent=2), encoding="utf-8")
    return {"papdata": papdata, "patterns": patterns}


def people_at(patterns: dict, minute: int, person_id: str) -> tuple[str, str] | None:
    """Return ('home'|'place', location id) for one person at one snapshot."""
    step = patterns[str(minute)]
    for home_id, occupants in step["homes"].items():
        if person_id in occupants:
            return "home", home_id
    for place_id, occupants in step["places"].items():
        if person_id in occupants:
            return "place", place_id
    return None
