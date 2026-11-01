"""What a safety car is worth, and to whom.

Three measurements, in the order they have to be made.

**The price of a stop.** A pit stop costs about twenty-two seconds
against the field under green flags. Under a safety car the pit lane
takes exactly as long, but the field is crawling, so the same stop
costs far less *relative to everyone else* - and relative to everyone
else is the only thing that decides a race. The difference between
those two numbers is the prize in this lottery.

**The ticket.** Nobody can choose when a safety car appears. Whether a
car can use one depends on where it happened to be in its stint: a car
yet to stop collects the discount, a car that stopped three laps ago
collects nothing and watches its rivals get a cheap stop. The ticket is
drawn by someone else's accident.

**The advantage destroyed.** Separately from the pit-stop prize, a
safety car deletes the gaps themselves. A leader who spent thirty laps
building twenty seconds has it taken away in one. This is measured only
on cars that did *not* pit during the period, so that what is being
measured is the bunching and not the stop.

The three are kept apart because they are different mechanisms and a
car can win on one and lose on another. Adding them into a single
"luck" number would hide exactly the cases worth looking at.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

import neutral

MIN_GREEN = 8         # green laps a car needs before its baseline is usable
MIN_CARS = 6
GAIN = 0.0            # a gap cannot be destroyed by a negative amount


@dataclass(frozen=True)
class Stop:
    """One pit stop, priced against what the field did on the same laps."""

    season: int
    round: int
    circuit: str
    driver: str
    lap: int
    loss: float           # seconds lost to the field by stopping
    in_lap: bool          # was the in-lap neutralised
    out_lap: bool         # was the out-lap neutralised

    @property
    def race(self) -> tuple[int, int]:
        return (self.season, self.round)

    @property
    def shelter(self) -> str:
        if self.in_lap and self.out_lap:
            return "both laps"
        if self.out_lap:
            return "out-lap only"
        if self.in_lap:
            return "in-lap only"
        return "green"


def own_laps(laps) -> dict[tuple, dict[int, float]]:
    out: dict[tuple, dict[int, float]] = defaultdict(dict)
    for row in laps:
        out[(row.season, row.round, row.driver)][row.lap] = row.seconds
    return dict(out)


def green_line(laps, stops, under: set, stopped: set
               ) -> dict[tuple[int, int], tuple]:
    """A straight line through each race's clean green laps.

    Built from laps that are neither pit laps nor neutralised, so it
    describes what a lap costs when nothing is happening. The slope is
    the fuel load burning off.
    """
    pit = _pit_laps(stops)
    rows: dict[tuple[int, int], list[tuple[int, float]]] = defaultdict(list)
    for row in laps:
        race = (row.season, row.round)
        if row.lap <= 1 or row.lap in pit[(row.season, row.round, row.driver)]:
            continue
        if (race[0], race[1], row.lap) in under | stopped:
            continue
        rows[race].append((row.lap, row.seconds))

    out = {}
    for race, seen in rows.items():
        if len(seen) < MIN_GREEN:
            continue
        numbers = np.array([lap for lap, _ in seen], dtype=float)
        values = np.array([value for _, value in seen])
        # The median car, not the mean, so one blown engine per race
        # does not tilt the line it is measured against.
        keep = values < np.percentile(values, 90)
        design = np.column_stack([np.ones(int(keep.sum())), numbers[keep]])
        beta, *_ = np.linalg.lstsq(design, values[keep], rcond=None)
        out[race] = (float(beta[0]), float(beta[1]))
    return out


def _pit_laps(stops) -> dict[tuple, set[int]]:
    """In-laps and out-laps, which are never evidence about normal pace."""
    pit: dict[tuple, set[int]] = defaultdict(set)
    for stop in stops:
        key = (stop.season, stop.round, stop.driver)
        pit[key].add(stop.lap)
        pit[key].add(stop.lap + 1)
    return pit


def factors(laps, stops, lines, under: set, stopped: set
            ) -> dict[tuple, float]:
    """How each car's pace compares with its race's green line.

    A ratio rather than a number of seconds, so that it carries over to
    a neutralised lap: a car one per cent quicker than the line is one
    per cent quicker whether the lap takes ninety seconds or a hundred
    and forty.
    """
    pit = _pit_laps(stops)
    seen: dict[tuple, list[float]] = defaultdict(list)
    for row in laps:
        race = (row.season, row.round)
        if race not in lines or row.lap <= 1:
            continue
        if row.lap in pit[(row.season, row.round, row.driver)]:
            continue
        if (race[0], race[1], row.lap) in under | stopped:
            continue
        base, slope = lines[race]
        seen[(row.season, row.round, row.driver)].append(
            row.seconds / (base + slope * row.lap))
    return {key: float(np.median(values)) for key, values in seen.items()
            if len(values) >= MIN_GREEN}


def multipliers(laps, stops, lines, periods, stopped: set, factor: dict
                ) -> dict[tuple, float]:
    """How much slower a neutralised lap is, per period.

    Per period rather than per lap, and this is the whole point. On
    twelve of the sixty-one neutralised laps in 2023 fewer than six cars
    stayed out, and on some of them nobody did: the entire field dived
    into the pits at once, which is exactly what a safety car is for.
    A per-lap reference collapses on precisely those laps, and refusing
    them throws away the stops with the largest discount - the estimate
    then comes back near zero because the sample has had its subject
    removed.

    Each car's own pace is divided back out before the median is taken.
    Without that the multiplier is not the slowdown, it is the slowdown
    times the pace of whoever happened to stay out - and under a safety
    car the cars that stay out are not a random half of the grid. In a
    synthetic race where only the slowest car stayed out, leaving its
    pace in understated every sheltered stop by two seconds.

    Pooling the cars that stayed out across the whole period survives a
    lap with nobody on it, as long as the period has somebody somewhere.
    When nobody stayed out for the whole period - which happens, and in
    2023 it happens once - this returns no multiplier for it, and the
    caller must refuse those stops rather than assume anything.
    """
    pit = _pit_laps(stops)
    inside: dict[tuple, list[float]] = defaultdict(list)
    index = {}
    for number, period in enumerate(periods):
        if period.kind != "neutralised":
            continue
        for lap in range(period.first, period.last + 1):
            index[(period.season, period.round, lap)] = number

    for row in laps:
        key = (row.season, row.round, row.lap)
        if key not in index or key in stopped or row.lap in pit[
                (row.season, row.round, row.driver)]:
            continue
        race = (row.season, row.round)
        if race not in lines:
            continue
        pace = factor.get((row.season, row.round, row.driver))
        if pace is None:
            continue
        base, slope = lines[race]
        inside[index[key]].append(
            row.seconds / ((base + slope * row.lap) * pace))
    return {number: float(np.median(values))
            for number, values in inside.items() if values}


def price(laps, stops, periods) -> tuple[list[Stop], dict[str, int]]:
    """Every pit stop, priced in seconds lost against staying out.

    The counterfactual is explicit: what this car would have taken on
    these two laps had it not stopped, which is its race's green line
    for those laps, times its own pace factor, times the slowdown in
    force. The difference is what the stop cost.
    """
    under = neutral.under(periods)
    stopped = neutral.halted(laps)
    lines = green_line(laps, stops, under, stopped)
    factor = factors(laps, stops, lines, under, stopped)
    slow = multipliers(laps, stops, lines, periods, stopped, factor)
    mine = own_laps(laps)
    circuits = {(row.season, row.round): row.circuit for row in laps}

    where: dict[tuple[int, int, int], int] = {}
    for number, period in enumerate(periods):
        if period.kind != "neutralised":
            continue
        for lap in range(period.first, period.last + 1):
            where[(period.season, period.round, lap)] = number

    def expected(race, driver, lap) -> float | None:
        base, slope = lines[race]
        pace = (base + slope * lap) * factor[(race[0], race[1], driver)]
        number = where.get((race[0], race[1], lap))
        if number is None:                       # a green lap
            return pace
        if number not in slow:
            # Every car pitted, so there is no evidence of how slow the
            # lap was. Defaulting to green pace here is not a small
            # error: it reports the entire safety car as time the car
            # lost by stopping, and in 2023 that was +85 s on 19 stops.
            return None
        return pace * slow[number]

    census = {"stops": len(stops), "priced": 0,
              "refused: no green line for the race": 0,
              "refused: no usable pace factor": 0,
              "refused: in-lap or out-lap not recorded": 0,
              "refused: the race was stopped on one of them": 0,
              "refused: nobody stayed out to measure the slowdown": 0}
    out: list[Stop] = []
    for stop in stops:
        race = (stop.season, stop.round)
        key = (stop.season, stop.round, stop.driver)
        if race not in lines:
            census["refused: no green line for the race"] += 1
            continue
        if key not in factor:
            census["refused: no usable pace factor"] += 1
            continue
        first, second = stop.lap, stop.lap + 1
        if first not in mine[key] or second not in mine[key]:
            census["refused: in-lap or out-lap not recorded"] += 1
            continue
        if ((race[0], race[1], first) in stopped
                or (race[0], race[1], second) in stopped):
            # A stop whose laps were run under a red flag is not a pit
            # stop in the sense being priced here; the car was parked.
            census["refused: the race was stopped on one of them"] += 1
            continue
        taken = mine[key][first] + mine[key][second]
        one = expected(race, stop.driver, first)
        two = expected(race, stop.driver, second)
        if one is None or two is None:
            census["refused: nobody stayed out to measure the slowdown"] += 1
            continue
        stayed = one + two
        out.append(Stop(
            season=stop.season, round=stop.round, circuit=circuits[race],
            driver=stop.driver, lap=stop.lap,
            loss=float(taken - stayed),
            in_lap=(race[0], race[1], first) in under,
            out_lap=(race[0], race[1], second) in under))
        census["priced"] += 1
    return out, census


def table(priced: list[Stop]) -> list[dict]:
    """The price of a stop, by how much of it was sheltered."""
    groups: dict[str, list[float]] = defaultdict(list)
    for stop in priced:
        groups[stop.shelter].append(stop.loss)
    order = ("green", "in-lap only", "out-lap only", "both laps")
    return [{"shelter": name, "stops": len(groups[name]),
             "median": float(np.median(groups[name])),
             "lower": float(np.percentile(groups[name], 25)),
             "upper": float(np.percentile(groups[name], 75))}
            for name in order if groups[name]]


def discount(priced: list[Stop], *, draws: int = 4000,
             seed: int = 11) -> dict:
    """What shelter is worth, as a difference of medians with an interval.

    Not a regression on means, and the reason is in the data rather than
    in taste. A handful of stops carry a five-second penalty served at
    the stop, or a wheel that would not go on, and those land in the
    right tail at sixty or a hundred seconds. The mean green stop is
    about thirty-five seconds and the median about twenty-three; the
    mean is describing the pit lane's disasters and the median is
    describing a pit stop. Fitting least squares here produces a number
    with an interval wide enough to contain both the answer and its
    opposite.

    The interval comes from resampling whole races with replacement,
    because the stops within a race share one safety car, one pit lane
    and one afternoon. Resampling stops individually would treat twenty
    cars queuing behind the same safety car as twenty independent facts
    and give an interval several times too narrow.
    """
    races = sorted({stop.race for stop in priced})
    by_race: dict[tuple[int, int], list[Stop]] = defaultdict(list)
    for stop in priced:
        by_race[stop.race].append(stop)

    def medians(sample: list[Stop]) -> dict[str, float]:
        groups: dict[str, list[float]] = defaultdict(list)
        for stop in sample:
            groups[stop.shelter].append(stop.loss)
        return {name: float(np.median(values))
                for name, values in groups.items() if values}

    found = medians(priced)
    rng = np.random.default_rng(seed)
    draws_by_name: dict[str, list[float]] = defaultdict(list)
    for _ in range(draws):
        picked: list[Stop] = []
        for number in rng.integers(0, len(races), len(races)):
            picked.extend(by_race[races[number]])
        shuffled = medians(picked)
        if "green" not in shuffled:
            continue
        for name, value in shuffled.items():
            if name != "green":
                draws_by_name[name].append(shuffled["green"] - value)

    out = {"green": found.get("green", float("nan")), "shelters": []}
    for name in ("in-lap only", "out-lap only", "both laps"):
        if name not in found:
            continue
        spread = np.array(draws_by_name.get(name, []))
        out["shelters"].append({
            "shelter": name,
            "median": found[name],
            "discount": found["green"] - found[name],
            "lower": float(np.percentile(spread, 2.5)) if spread.size else
            float("nan"),
            "upper": float(np.percentile(spread, 97.5)) if spread.size else
            float("nan"),
            "draws": int(spread.size)})
    return out


def takers(stops, periods) -> list[dict]:
    """Who collected a discounted stop, and who was not in a position to.

    Built from the raw stop list, not from the priced ones. Whether a
    car pitted on a given lap is a fact that needs no model, and some
    stops cannot be priced - in one 2023 race the whole field pitted at
    once, so there was nobody left on track to measure the slowdown
    against. Reading this off the priced stops reported that race as
    nineteen cars declining a free stop they had all just taken.

    A car "could have" used a neutralisation only if it still had a stop
    left to make, which is known after the fact from its own stop list.
    """
    mine: dict[tuple, list] = defaultdict(list)
    for stop in stops:
        mine[(stop.season, stop.round, stop.driver)].append(stop)

    out = []
    for period in periods:
        if period.kind != "neutralised":
            continue
        held, took = 0, 0
        for key, theirs in mine.items():
            if (key[0], key[1]) != period.race:
                continue
            later = [one for one in theirs if one.lap >= period.first]
            if not later:
                continue
            held += 1
            if any(period.covers(one.lap) for one in later):
                took += 1
        out.append({"season": period.season, "round": period.round,
                    "circuit": period.circuit,
                    "laps": f"{period.first}-{period.last}",
                    "with a stop in hand": held, "took it here": took,
                    "share": took / held if held else float("nan")})
    return out


def erased(periods, times, stops) -> list[dict]:
    """Seconds of earned advantage deleted by the bunching.

    Measured only on cars that did not pit during the period, because a
    car that pits changes its own gap for reasons that have nothing to
    do with the safety car. What is left is the leader's advantage being
    handed back.
    """
    out = []
    for period in periods:
        if period.kind != "neutralised":
            continue
        # Anyone who stopped anywhere in the window, including the lap
        # on either side that the gaps are read on.
        pitted = {stop.driver for stop in stops
                  if (stop.season, stop.round) == period.race
                  and period.first - 1 <= stop.lap <= period.last + 1}
        before = _standings(times, period.race, period.first - 1)
        after = _standings(times, period.race, period.last + 1)
        shared = sorted((set(before) & set(after)) - pitted)
        if len(shared) < MIN_CARS:
            continue
        lost = [max(before[name] - after[name], GAIN) for name in shared]
        out.append({"season": period.season, "round": period.round,
                    "circuit": period.circuit,
                    "laps": f"{period.first}-{period.last}",
                    "cars": len(shared), "pitted, excluded": len(pitted),
                    "seconds erased": float(sum(lost)),
                    "worst hit": float(max(lost)) if lost else 0.0,
                    "leader's lead before": _lead(before),
                    "leader's lead after": _lead(after)})
    return out


def _lead(standings: dict[str, float]) -> float:
    """The leader's margin over second, not over last.

    `standings` holds gaps to the leader, so the leader's own entry is
    zero and the largest entry is the back of the field. The lead is the
    second smallest.
    """
    if len(standings) < 2:
        return float("nan")
    return float(sorted(standings.values())[1])


def _standings(times, race, lap) -> dict[str, float]:
    """Each car's gap to the leader on a lap, in seconds."""
    values = {key[2]: float(row[lap]) for key, row in times.items()
              if key[0] == race[0] and key[1] == race[1]
              and 0 <= lap < row.size and np.isfinite(row[lap])}
    if len(values) < MIN_CARS:
        return {}
    front = min(values.values())
    return {name: value - front for name, value in values.items()}
