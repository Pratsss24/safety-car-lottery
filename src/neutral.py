"""Finding the laps the whole field was slow, and working out why.

The source records no safety car. It records lap times, and a safety
car is obvious in them: everybody is thirty to sixty per cent slower at
once. Detecting *that the field slowed* is almost trivial, and this
module spends four lines on it.

The hard part is the next question, which is **why**. Rain slows the
whole field too, and so does a wet patch, a damp restart, or a track
that is still drying. A detector built on lap times alone cannot tell
a safety car from weather, and one that does not try will quietly call
twenty laps of Monaco rain a safety car and then price a lottery that
never happened.

What separates them is not the lap times but the **gaps**. Under a
safety car the field is bunched up behind it deliberately: the spread
of the cars collapses, typically to a fifth of what it was. Weather
does the opposite - drivers differ far more in the wet than in the dry,
so the field spreads out. That single measurement tells two
indistinguishable lap-time signatures apart, and it is the reason this
module reads gaps at all.

Periods that do neither are reported as unclear rather than forced into
one bucket. There are two of them in 2023 and they are in the output.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from data import Lap

SLOW = 1.15           # median lap this much above the green line is slow
HALT = 3.0            # above this the race is stopped, not neutralised
GREEN = 1.07          # laps under this are trusted to fit the green line
BRIDGE = 1            # a single green lap does not end a safety car
COMPRESSED = 0.80     # the field closed up this much: a neutralisation
SPREAD = 1.20         # the field opened out: conditions, not a safety car
MIN_CARS = 6          # fewer than this and a spread means nothing
ROUNDS = 6            # refits of the green line


@dataclass(frozen=True)
class Period:
    """A run of laps on which the whole field was slow."""

    season: int
    round: int
    circuit: str
    first: int
    last: int
    peak: float           # the worst lap, as a multiple of green pace
    onset: float          # the jump from the lap before: how sharp it was
    before: float         # spread of the field going in, seconds
    after: float          # spread coming out
    kind: str             # neutralised | conditions | unclear | to the flag

    @property
    def laps(self) -> int:
        return self.last - self.first + 1

    @property
    def change(self) -> float:
        """What the field's spread was multiplied by."""
        return self.after / self.before if self.before else float("nan")

    @property
    def race(self) -> tuple[int, int]:
        return (self.season, self.round)

    def covers(self, lap: int) -> bool:
        return self.first <= lap <= self.last


def field(laps: list[Lap]) -> dict[tuple[int, int], dict[int, float]]:
    """The median lap time of everyone still running, per race per lap.

    The median rather than the mean, because one car crawling to the
    pits with a puncture should not make the whole lap look neutralised.
    That is precisely the event most likely to be happening.
    """
    rows: dict[tuple[int, int], dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list))
    for lap in laps:
        rows[(lap.season, lap.round)][lap.lap].append(lap.seconds)
    return {race: {lap: float(np.median(times))
                   for lap, times in sorted(per.items())}
            for race, per in rows.items()}


def green_line(medians: dict[int, float]) -> tuple[float, float]:
    """A straight line through the laps that were not slow.

    Fuel burns off over a race and the field gets about three seconds
    quicker from start to finish, so a flat baseline is slightly wrong
    early and slightly wrong late. Fitting a line and refitting it on
    whatever still looks green removes that.

    It is worth saying what this is *not* worth: a safety car is a thirty
    per cent effect and fuel is a three per cent one, so correcting for
    fuel moves about three race-laps out of thirteen hundred across the
    season. It is here because it is two lines and principled, not
    because it changes an answer.
    """
    numbers = np.array(sorted(medians))
    values = np.array([medians[lap] for lap in numbers])
    # Lap 1 is a standing start and is slow in every race ever run. It
    # is never evidence about green pace.
    keep = numbers > 1
    base, slope = float(values.mean()), 0.0
    for _ in range(ROUNDS):
        design = np.column_stack([np.ones(int(keep.sum())), numbers[keep]])
        beta, *_ = np.linalg.lstsq(design, values[keep], rcond=None)
        base, slope = float(beta[0]), float(beta[1])
        fresh = (numbers > 1) & (values / (base + slope * numbers) < GREEN)
        if int(fresh.sum()) < 5 or bool((fresh == keep).all()):
            break
        keep = fresh
    return base, slope


def ratios(medians: dict[int, float]) -> dict[int, float]:
    """Each lap's median as a multiple of the green pace for that lap."""
    base, slope = green_line(medians)
    return {lap: value / (base + slope * lap)
            for lap, value in medians.items()}


def runs(slow: list[int], bridge: int = BRIDGE) -> list[tuple[int, int]]:
    """Group slow laps into periods, stepping over short green gaps.

    A safety car's last lap is partly green - the field is released
    somewhere along it - so one lap under the threshold in the middle of
    a neutralisation is the norm rather than a second event. Bridging a
    single lap merges 33 fragments into 27 periods, and bridging two
    merges nothing further, which is the sign that one is the right
    number rather than a tuned one.
    """
    if not slow:
        return []
    out: list[tuple[int, int]] = []
    first = previous = slow[0]
    for lap in slow[1:]:
        if lap <= previous + 1 + bridge:
            previous = lap
            continue
        out.append((first, previous))
        first = previous = lap
    out.append((first, previous))
    return out


def spread(times: dict, race: tuple[int, int], lap: int) -> float:
    """How strung out the field is on one lap, in seconds.

    The interquartile range of the gaps to the leader, not their
    standard deviation. One car three laps down and limping puts a
    thousand seconds into the standard deviation and makes a bunched
    field look like a scattered one; it moves the quartiles not at all.
    This is not a refinement, it is the difference between the
    classification below working and not.
    """
    values = [float(row[lap]) for key, row in times.items()
              if key[0] == race[0] and key[1] == race[1]
              and 0 <= lap < row.size and np.isfinite(row[lap])]
    if len(values) < MIN_CARS:
        return float("nan")
    gaps = np.array(values) - min(values)
    return float(np.percentile(gaps, 75) - np.percentile(gaps, 25))


def classify(change: float, *, ended: bool = False) -> str:
    """What closed or opened the field tells you what slowed it.

    A period still running when the flag falls has no lap afterwards to
    measure, so it gets its own label. Calling it unclear would suggest
    the evidence was ambiguous; the evidence does not exist.
    """
    if ended:
        return "to the flag"
    if not np.isfinite(change):
        return "unclear"
    if change < COMPRESSED:
        return "neutralised"
    if change > SPREAD:
        return "conditions"
    return "unclear"


def build(laps: list[Lap], times: dict, *, slow: float = SLOW
          ) -> tuple[list[Period], dict[str, int]]:
    """Every period of a slow field in the season, with a reading of why."""
    circuits = {(lap.season, lap.round): lap.circuit for lap in laps}
    medians = field(laps)
    census = {"races": len(medians), "race-laps": 0, "laps slow": 0,
              "laps the race was stopped": 0, "periods": 0,
              "periods neutralised": 0, "periods from conditions": 0,
              "periods unclear": 0, "periods still running at the flag": 0}

    out: list[Period] = []
    for race, per in sorted(medians.items()):
        ratio = ratios(per)
        census["race-laps"] += sum(1 for lap in ratio if lap > 1)
        census["laps the race was stopped"] += sum(
            1 for lap, value in ratio.items() if value > HALT)
        hits = sorted(lap for lap, value in ratio.items()
                      if lap > 1 and slow < value <= HALT)
        census["laps slow"] += len(hits)

        for first, last in runs(hits):
            before = spread(times, race, first - 1)
            after = spread(times, race, last + 1)
            change = after / before if before else float("nan")
            kind = classify(change, ended=last >= max(ratio))
            out.append(Period(
                season=race[0], round=race[1], circuit=circuits[race],
                first=first, last=last,
                # Only the laps that actually counted as slow. A single
                # red-flag lap bridged inside a period would otherwise
                # report the period's worst lap as thirty times green
                # pace, which describes a stationary car, not a slow one.
                peak=max(ratio[lap] for lap in range(first, last + 1)
                         if lap in ratio and ratio[lap] <= HALT),
                onset=(ratio[first] / ratio[first - 1]
                       if first - 1 in ratio else float("nan")),
                before=before, after=after, kind=kind))
            census["periods"] += 1
            census[{"neutralised": "periods neutralised",
                    "conditions": "periods from conditions",
                    "unclear": "periods unclear",
                    "to the flag": "periods still running at the flag",
                    }[kind]] += 1
    return out, census


def neutralised(periods: list[Period]) -> dict[tuple[int, int], list[Period]]:
    """The safety cars only, indexed by race."""
    out: dict[tuple[int, int], list[Period]] = defaultdict(list)
    for period in periods:
        if period.kind == "neutralised":
            out[period.race].append(period)
    return dict(out)


def under(periods: list[Period]) -> set[tuple[int, int, int]]:
    """(season, round, lap) for every lap run under a safety car."""
    return {(period.season, period.round, lap)
            for period in periods if period.kind == "neutralised"
            for lap in range(period.first, period.last + 1)}


def sensitivity(laps: list[Lap], times: dict,
                thresholds=(1.10, 1.15, 1.20, 1.25)) -> list[dict]:
    """Does the answer depend on where the threshold was put?

    If the count of safety cars moves a lot between 1.10 and 1.25 then
    the threshold is doing the work rather than the data, and nothing
    downstream of it is worth reading.
    """
    out = []
    for value in thresholds:
        found, census = build(laps, times, slow=value)
        out.append({"threshold": value,
                    "periods": census["periods"],
                    "neutralised": census["periods neutralised"],
                    "laps": census["laps slow"]})
    return out


def clustering(stops, periods: list[Period], census: dict) -> dict:
    """Do pit stops pile up on the laps this module calls neutralised?

    This is the one check on the detector that uses no lap times, and so
    is the only one that can fail honestly. A safety car makes a pit
    stop cheap, so if these laps really are safety cars the stops should
    be concentrated on them far above their share of the season; if the
    detector were picking up rain or noise there would be no reason for
    stops to care.

    Nothing downstream depends on this number. It exists so that the
    detector can be wrong in public.
    """
    laps = under(periods)
    on = sum(1 for stop in stops
             if (stop.season, stop.round, stop.lap) in laps)
    share = len(laps) / census["race-laps"] if census["race-laps"] else 0.0
    rate = on / len(stops) if stops else float("nan")
    return {"neutralised laps": len(laps),
            "share of race-laps": share,
            "stops": len(stops),
            "stops under neutralisation": on,
            "share of stops": rate,
            "enrichment": rate / share if share else float("nan")}


def halted(laps: list[Lap]) -> set[tuple[int, int, int]]:
    """(season, round, lap) for laps run while the race was stopped.

    A red flag is not a slow lap, it is a lap spent stationary in the
    pit lane, and the recorded times run to thirty times normal. These
    are not evidence about anything - not about green pace, not about a
    car's own speed, and not about what a pit stop costs - so every
    other calculation has to be able to exclude them by name.
    """
    out: set[tuple[int, int, int]] = set()
    for race, medians in field(laps).items():
        for lap, value in ratios(medians).items():
            if value > HALT:
                out.add((race[0], race[1], lap))
    return out
