"""Hourly clock. One Mesa step is one hour. Destinations were chosen already."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from mesa import Agent, Model

from population import Person, Town


# 2026-10-13 is a Tuesday at midnight. The first recorded hour is 01:00.
# 143 hours later is Sunday 2026-10-18 23:00.
TUESDAY = datetime(2026, 10, 13)
HOURS_THROUGH_SUNDAY_NIGHT = 5 * 24 + 23
GROCERY_PROBABILITY = 0.3


def choose_location(person: Person, when: datetime, rng: random.Random) -> tuple[str, str]:
    """Return ('home' or 'place', location id) for this clock time."""
    weekday = when.weekday()
    hour = when.hour
    if weekday < 5 and person.role == "student" and person.school_id and 8 <= hour < 15:
        return "place", person.school_id
    if weekday < 5 and person.role == "worker" and person.work_id and 9 <= hour < 17:
        return "place", person.work_id
    if weekday == 5 and person.grocery_id and 10 <= hour < 13 and rng.random() < GROCERY_PROBABILITY:
        return "place", person.grocery_id
    return "home", person.home_id


class PersonAgent(Agent):
    def __init__(self, model: "TownModel", person: Person):
        super().__init__(model)
        self.person = person
        self.location_kind = "home"
        self.location_id = person.home_id

    def step(self) -> None:
        kind, location_id = choose_location(self.person, self.model.when, self.model.clock)
        self.location_kind = kind
        self.location_id = location_id


class TownModel(Model):
    def __init__(self, town: Town, start: datetime = TUESDAY, seed: int = 42):
        super().__init__(rng=seed)
        self.town = town
        self.start = start
        self.when = start
        self.clock = random.Random(seed)
        self.patterns: dict[str, dict] = {}
        for person in town.people:
            PersonAgent(self, person)

    def step(self) -> None:
        self.when = self.when + timedelta(hours=1)
        self.agents.do("step")
        homes: dict[str, list[str]] = {}
        places: dict[str, list[str]] = {}
        for agent in self.agents:
            bucket = places if agent.location_kind == "place" else homes
            bucket.setdefault(agent.location_id, []).append(agent.person.person_id)
        minute = str(int((self.when - self.start).total_seconds() // 60))
        self.patterns[minute] = {"homes": homes, "places": places}


def run_clock(
    town: Town,
    start: datetime = TUESDAY,
    hours: int = HOURS_THROUGH_SUNDAY_NIGHT,
    seed: int = 42,
) -> dict[str, dict]:
    """Step the Mesa model and return minute -> {homes, places}."""
    model = TownModel(town, start=start, seed=seed)
    for _ in range(hours):
        model.step()
    return model.patterns
