"""Run the 21550 toy and write papdata.json plus patterns.json."""

from pathlib import Path

from census import load_census
from export import people_at, write_outputs
from geometry import load_zone
from model import HOURS_THROUGH_SATURDAY_MORNING, TUESDAY, run_clock
from places import load_places
from population import build_town


def main() -> None:
    zone = load_zone()
    census = load_census(zone)
    places = load_places(zone)
    town = build_town(zone, census, places)
    patterns = run_clock(town, start=TUESDAY, hours=HOURS_THROUGH_SATURDAY_MORNING)
    out = Path(__file__).resolve().parent / "output"
    write_outputs(town, out, patterns)
    print(f"people {len(town.people)} homes {len(town.homes)} places {len(town.places)}")
    print(f"wrote {out}")
    for minute, label in ((600, "Tuesday 10:00"), (1200, "Tuesday 20:00"), (6420, "Saturday 11:00")):
        print(label, _tally(town, patterns, minute))


def _tally(town, patterns, minute: int) -> dict[str, int]:
    counts = {"home": 0, "school": 0, "work": 0, "grocery": 0, "other": 0}
    places = {place.place_id: place.function for place in town.places}
    for person in town.people:
        found = people_at(patterns, minute, person.person_id)
        if found is None or found[0] == "home":
            counts["home"] += 1
            continue
        function = places.get(found[1], "other")
        if function in counts:
            counts[function] += 1
        else:
            counts["other"] += 1
    return counts


if __name__ == "__main__":
    main()
