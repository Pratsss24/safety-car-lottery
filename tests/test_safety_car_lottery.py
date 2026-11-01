"""Tests for the safety-car-lottery pipeline.

Three kinds of anchor, in descending order of how much they are worth.

**Algebra.** Bridging a gap of one lap merges two runs and bridging
nothing does not; the leader's lead is the second-smallest gap. These
have one right answer.

**Recovery of a planted truth.** A synthetic race is built with a known
green pace, a known fuel slope, a known safety car at known laps with a
known slowdown, and a known pit loss. The pipeline has to give those
numbers back. This is the only kind of test that catches a sign error
or a silent default, and three of the tests below exist because it did.

**Refusal.** A measurement that cannot be made has to be declined and
counted. The important one is the race where every car pits at once:
there is then nobody left on track to measure the slowdown against, and
the honest answer is to refuse rather than to assume green pace. That
assumption, before it was removed, turned one safety car into an
eighty-five second loss for nineteen cars.

No test compares against saved output.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import lottery                                             # noqa: E402
import neutral                                             # noqa: E402
from data import Lap, Stop                                 # noqa: E402


# --------------------------------------------------------------------
# a synthetic race
# --------------------------------------------------------------------

def race(*, cars: int = 10, laps: int = 40, base: float = 90.0,
         slope: float = -0.02, round_: int = 1, slow: dict | None = None,
         pace: float = 0.15, stops: dict | None = None,
         pit_cost: float = 22.0, bunch: bool = True, catch: float = 1.0,
         noise: float = 0.0, seed: int = 0):
    """Laps and stops for one race with everything planted.

    `slow` maps a lap to the multiple of green pace the field ran it at.

    `bunch` says whether those laps also close the field up, which is
    what makes a safety car a safety car rather than weather. It is not
    enough to slow everybody equally: that leaves every gap exactly
    where it was. A safety car physically gathers the cars into a queue,
    so on the *first* lap of each run every car is placed `catch`
    seconds behind the one in front, and the rest of the run is a clean
    multiple of green pace. Putting the gathering on the first lap
    rather than the last leaves the later laps uncontaminated, so a
    stop taken inside the window can be priced exactly. With `bunch`
    False the slower cars lose far more than the quick ones instead,
    which is what rain does.

    `stops` maps a driver to the lap they pit on.
    """
    slow = slow or {}
    stops = stops or {}
    rng = np.random.default_rng(seed)
    names = [f"car{number:02d}" for number in range(cars)]

    seconds: dict[str, dict[int, float]] = {}
    for number, name in enumerate(names):
        offset = number * pace
        per = {}
        for lap in range(1, laps + 1):
            green = base + slope * lap
            value = green + offset
            if lap in slow:
                # The car keeps its own pace through the slow laps,
                # which is what the model assumes. A fixture that gave
                # every car an identical time under the safety car
                # would be testing that assumption rather than the
                # code, and would show a bias of about 1.7 s that is
                # the fixture's and not the pipeline's.
                value = (green + offset) * slow[lap]
                if not bunch:
                    value += offset * 10
            per[lap] = float(value)
        seconds[name] = per

    if bunch:
        for first, last in neutral.runs(sorted(slow), bridge=0):
            if last >= laps:
                continue
            running = {name: sum(seconds[name][lap]
                                 for lap in range(1, first + 1))
                       for name in names}
            # The queue is centred on the middle car, not hung off the
            # leader. A safety car slows the leader as much as it lets
            # the back of the field catch up, and centring keeps the
            # field's median lap time at the planted multiple instead
            # of dragging it down by the size of the gathering.
            middle = float(np.median(list(running.values())))
            order = sorted(running, key=running.get)
            for number, name in enumerate(order):
                target = middle + catch * (number - (len(order) - 1) / 2)
                seconds[name][first] += target - running[name]

    # The pit cost goes on after the bunching, not before. Adding it
    # first lets the bunching absorb it - every car is placed back in
    # the queue regardless - and the planted stop then costs nothing,
    # which makes the fixture agree with the code about a number
    # neither of them computed.
    for name in names:
        if name in stops:
            seconds[name][stops[name]] += pit_cost
        if noise:
            for lap in seconds[name]:
                seconds[name][lap] += rng.normal(0, noise)

    out_laps, out_stops = [], []
    for number, name in enumerate(names):
        for lap in range(1, laps + 1):
            out_laps.append(Lap(
                season=2023, round=round_, race=f"race {round_}",
                circuit=f"circuit{round_}", driver=name, lap=lap,
                seconds=seconds[name][lap], position=number + 1))
        if name in stops:
            out_stops.append(Stop(season=2023, round=round_, driver=name,
                                  lap=stops[name], stop=1, duration=23.0))
    return out_laps, out_stops


def elapsed(laps):
    """gaps.elapsed without importing it, so these tests stand alone."""
    rows: dict[tuple, dict[int, float]] = {}
    for lap in laps:
        rows.setdefault((lap.season, lap.round, lap.driver), {})[
            lap.lap] = lap.seconds
    out = {}
    for key, per in rows.items():
        last = max(per)
        times = np.full(last + 1, np.nan)
        times[0] = 0.0
        for lap in range(1, last + 1):
            times[lap] = times[lap - 1] + per.get(lap, np.nan)
        out[key] = times
    return out


# --------------------------------------------------------------------
# grouping laps into periods
# --------------------------------------------------------------------

def test_consecutive_slow_laps_are_one_period():
    assert neutral.runs([4, 5, 6]) == [(4, 6)]


def test_a_single_green_lap_in_the_middle_does_not_end_a_safety_car():
    # The field is released somewhere along the last lap, so one lap
    # under the threshold mid-period is the norm, not a second event.
    assert neutral.runs([4, 5, 7, 8], bridge=1) == [(4, 8)]
    assert neutral.runs([4, 5, 7, 8], bridge=0) == [(4, 5), (7, 8)]


def test_a_long_green_stretch_does_end_one():
    assert neutral.runs([4, 5, 20, 21], bridge=1) == [(4, 5), (20, 21)]


def test_no_slow_laps_is_no_periods():
    assert neutral.runs([]) == []


# --------------------------------------------------------------------
# the green line and the ratios
# --------------------------------------------------------------------

def test_the_green_line_recovers_a_planted_base_and_fuel_slope():
    laps, _ = race(base=95.0, slope=-0.04, laps=50)
    medians = neutral.field(laps)
    base, slope = neutral.green_line(medians[(2023, 1)])
    # The median car sits a little above the quickest, so the intercept
    # is the base plus that offset; the slope is the fuel burn and is
    # not affected by a constant offset.
    assert slope == pytest.approx(-0.04, abs=1e-6)
    assert base == pytest.approx(95.0 + 0.15 * 4.5, abs=0.05)


def test_a_planted_slow_lap_shows_the_planted_ratio():
    laps, _ = race(slow={20: 1.5, 21: 1.5})
    medians = neutral.field(laps)
    found = neutral.ratios(medians[(2023, 1)])
    assert found[20] == pytest.approx(1.5, abs=0.02)
    assert found[10] == pytest.approx(1.0, abs=0.02)


def test_lap_one_is_never_evidence_about_green_pace():
    # A standing start is slow in every race ever run, so a line fitted
    # through it would be tilted in every race ever run.
    quick, _ = race(laps=40)
    medians = neutral.field(quick)
    clean = neutral.green_line(medians[(2023, 1)])
    slowed = [Lap(**{**row.__dict__,
                     "seconds": row.seconds + (25.0 if row.lap == 1 else 0)})
              for row in quick]
    dirty = neutral.green_line(neutral.field(slowed)[(2023, 1)])
    assert dirty == pytest.approx(clean, abs=1e-6)


# --------------------------------------------------------------------
# telling a safety car from the weather
# --------------------------------------------------------------------

def test_a_slow_period_that_bunches_the_field_is_a_safety_car():
    laps, _ = race(slow={20: 1.5, 21: 1.5, 22: 1.5}, bunch=True)
    periods, census = neutral.build(laps, elapsed(laps))
    assert census["periods neutralised"] == 1
    found = periods[0]
    assert (found.first, found.last) == (20, 22)
    assert found.change < neutral.COMPRESSED
    assert found.kind == "neutralised"


def test_a_slow_period_that_spreads_the_field_is_not():
    # Same lap times, opposite effect on the order. Nothing in the lap
    # times distinguishes these two tests from each other.
    laps, _ = race(slow={20: 1.5, 21: 1.5, 22: 1.5}, bunch=False)
    periods, census = neutral.build(laps, elapsed(laps))
    assert census["periods neutralised"] == 0
    assert census["periods from conditions"] == 1
    assert periods[0].change > neutral.SPREAD


def test_a_period_running_to_the_flag_is_labelled_not_guessed():
    laps, _ = race(laps=30, slow={29: 1.5, 30: 1.5})
    periods, census = neutral.build(laps, elapsed(laps))
    assert census["periods still running at the flag"] == 1
    assert periods[0].kind == "to the flag"


def test_classify_reads_the_thresholds_the_way_it_says():
    assert neutral.classify(0.2) == "neutralised"
    assert neutral.classify(3.0) == "conditions"
    assert neutral.classify(1.0) == "unclear"
    assert neutral.classify(float("nan")) == "unclear"
    assert neutral.classify(0.2, ended=True) == "to the flag"


def test_a_red_flag_is_found_and_is_not_a_safety_car():
    laps, _ = race(slow={20: 30.0, 21: 30.0})
    stopped = neutral.halted(laps)
    assert (2023, 1, 20) in stopped and (2023, 1, 21) in stopped
    periods, census = neutral.build(laps, elapsed(laps))
    assert census["laps the race was stopped"] == 2
    assert census["periods"] == 0          # stationary is not slow


def test_the_peak_ignores_a_red_flag_lap_bridged_inside_a_period():
    # Without this the worst lap of the period reads as thirty times
    # green pace, which describes a parked car, not a slow one.
    laps, _ = race(slow={20: 1.5, 21: 30.0, 22: 1.5})
    periods, _ = neutral.build(laps, elapsed(laps))
    assert len(periods) == 1
    assert periods[0].peak == pytest.approx(1.5, abs=0.05)


def test_the_spread_ignores_a_car_three_laps_down():
    # One limping car puts a thousand seconds into a standard deviation
    # and nothing at all into the quartiles.
    laps, _ = race(cars=12, slow={20: 1.5, 21: 1.5})
    crippled = [Lap(**{**row.__dict__, "seconds": row.seconds + 60.0})
                if row.driver == "car11" and row.lap > 5 else row
                for row in laps]
    periods, census = neutral.build(crippled, elapsed(crippled))
    assert census["periods neutralised"] == 1


# --------------------------------------------------------------------
# the detector, checked against something that is not a lap time
# --------------------------------------------------------------------

def test_stops_taken_under_a_safety_car_show_up_as_enrichment():
    under = {f"car{n:02d}": 20 for n in range(8)}
    laps, stops = race(cars=10, laps=40, slow={20: 1.5, 21: 1.5},
                       stops=under)
    periods, census = neutral.build(laps, elapsed(laps))
    found = neutral.clustering(stops, periods, census)
    assert found["stops under neutralisation"] == 8
    assert found["enrichment"] > 5.0


def test_enrichment_is_about_one_when_stops_ignore_the_safety_car():
    spread = {f"car{n:02d}": 5 + n for n in range(8)}
    laps, stops = race(cars=10, laps=40, slow={20: 1.5, 21: 1.5},
                       stops=spread)
    periods, census = neutral.build(laps, elapsed(laps))
    found = neutral.clustering(stops, periods, census)
    assert found["stops under neutralisation"] == 0


# --------------------------------------------------------------------
# pricing a stop
# --------------------------------------------------------------------

def test_a_green_pit_stop_is_priced_at_what_it_cost():
    laps, stops = race(cars=10, laps=40, pit_cost=22.0,
                       stops={"car03": 20})
    periods, _ = neutral.build(laps, elapsed(laps))
    priced, census = lottery.price(laps, stops, periods)
    assert census["priced"] == 1
    assert priced[0].shelter == "green"
    assert priced[0].loss == pytest.approx(22.0, abs=0.2)


def test_a_car_s_own_pace_is_taken_out_so_a_quick_car_does_not_pit_for_free():
    # car00 is the quickest on the grid. Without the pace factor its
    # in-lap and out-lap both look cheap against the field and its stop
    # would be priced below what it cost.
    laps, stops = race(cars=10, laps=40, pace=0.5, pit_cost=22.0,
                       stops={"car00": 20})
    periods, _ = neutral.build(laps, elapsed(laps))
    priced, _ = lottery.price(laps, stops, periods)
    assert priced[0].loss == pytest.approx(22.0, abs=0.3)


def test_a_sheltered_stop_is_not_charged_for_the_safety_car():
    laps, stops = race(cars=14, laps=40, slow={20: 1.5, 21: 1.5, 22: 1.5},
                       pit_cost=22.0, stops={"car03": 21})
    periods, _ = neutral.build(laps, elapsed(laps))
    priced, _ = lottery.price(laps, stops, periods)
    assert priced[0].shelter == "both laps"
    # The two laps would have taken 1.5x green whether this car stopped
    # or not, so the stop costs what the pit lane added on top of that
    # and nothing more. Charging it the safety car as well was the bug.
    assert priced[0].loss == pytest.approx(22.0, abs=1.5)


def test_the_shelter_label_depends_on_both_laps_not_one():
    laps, stops = race(cars=10, laps=40, slow={21: 1.5},
                       stops={"car03": 20, "car05": 21})
    periods, _ = neutral.build(laps, elapsed(laps))
    priced, _ = lottery.price(laps, stops, periods)
    labels = {one.driver: one.shelter for one in priced}
    assert labels["car03"] == "out-lap only"     # pits into it
    assert labels["car05"] == "in-lap only"      # pits out of it


def test_a_period_where_everybody_pitted_is_refused_not_assumed_green():
    # The bug this replaces: with no car left on track the slowdown was
    # silently taken to be 1.0, and the whole safety car was charged to
    # the stop. In 2023 that read as +85 s on nineteen stops.
    everyone = {f"car{n:02d}": 20 for n in range(10)}
    laps, stops = race(cars=10, laps=40, slow={20: 1.5, 21: 1.5},
                       stops=everyone)
    periods, _ = neutral.build(laps, elapsed(laps))
    priced, census = lottery.price(laps, stops, periods)
    assert census["refused: nobody stayed out to measure the slowdown"] == 10
    assert priced == []


def test_one_car_staying_out_is_enough_to_measure_the_slowdown():
    most = {f"car{n:02d}": 21 for n in range(9)}
    laps, stops = race(cars=10, laps=40, slow={20: 1.5, 21: 1.5, 22: 1.5},
                       stops=most)
    periods, _ = neutral.build(laps, elapsed(laps))
    priced, census = lottery.price(laps, stops, periods)
    assert census["priced"] == 9
    assert all(one.loss == pytest.approx(22.0, abs=2.0) for one in priced)


def test_a_stop_made_while_the_race_was_stopped_is_refused():
    laps, stops = race(cars=10, laps=40, slow={20: 30.0},
                       stops={"car03": 20})
    periods, _ = neutral.build(laps, elapsed(laps))
    priced, census = lottery.price(laps, stops, periods)
    assert census["refused: the race was stopped on one of them"] == 1
    assert priced == []


def test_the_pace_factor_is_a_ratio_and_recovers_a_planted_offset():
    laps, stops = race(cars=10, laps=40, pace=0.9, stops={})
    under: set = set()
    lines = lottery.green_line(laps, stops, under, set())
    found = lottery.factors(laps, stops, lines, under, set())
    base, slope = lines[(2023, 1)]
    middle = base + slope * 20
    # Where the fitted line sits depends on trimming, so anchor on the
    # difference between two cars rather than on either one's level:
    # car09 is 0.9 * 9 seconds a lap slower than car00, whatever the
    # line is, and as a ratio that is that gap over a lap.
    gap = found[(2023, 1, "car09")] - found[(2023, 1, "car00")]
    assert gap == pytest.approx(0.9 * 9 / middle, abs=0.002)
    assert found[(2023, 1, "car00")] < 1.0 < found[(2023, 1, "car09")]


def test_the_slowdown_multiplier_recovers_what_was_planted():
    laps, stops = race(cars=10, laps=40, slow={20: 1.4, 21: 1.4})
    periods, _ = neutral.build(laps, elapsed(laps))
    under = neutral.under(periods)
    lines = lottery.green_line(laps, stops, under, set())
    factor = lottery.factors(laps, stops, lines, under, set())
    found = lottery.multipliers(laps, stops, lines, periods, set(), factor)
    assert len(found) == 1
    assert next(iter(found.values())) == pytest.approx(1.4, abs=0.02)


# --------------------------------------------------------------------
# who took it, and what it deleted
# --------------------------------------------------------------------

def test_takers_counts_cars_that_pitted_in_the_window():
    taken = {f"car{n:02d}": 20 for n in range(4)}
    taken.update({f"car{n:02d}": 30 for n in range(4, 8)})
    laps, stops = race(cars=20, laps=40, slow={20: 1.5, 21: 1.5, 22: 1.5},
                       stops=taken)
    periods, _ = neutral.build(laps, elapsed(laps))
    rows = lottery.takers(stops, periods)
    assert len(rows) == 1
    assert rows[0]["with a stop in hand"] == 8
    assert rows[0]["took it here"] == 4
    assert rows[0]["share"] == pytest.approx(0.5)


def test_takers_counts_a_stop_that_could_not_be_priced():
    # Whether a car pitted is a fact that needs no model. Reading this
    # off the priced stops reported a race in which the whole field
    # pitted as nineteen cars declining a free stop they had taken.
    everyone = {f"car{n:02d}": 20 for n in range(10)}
    laps, stops = race(cars=10, laps=40, slow={20: 1.5, 21: 1.5},
                       stops=everyone)
    periods, _ = neutral.build(laps, elapsed(laps))
    priced, _ = lottery.price(laps, stops, periods)
    assert priced == []                      # nothing could be priced
    rows = lottery.takers(stops, periods)
    assert rows[0]["took it here"] == 10     # but all ten took it


def test_a_car_with_no_stop_left_is_not_counted_as_declining_one():
    laps, stops = race(cars=10, laps=40, slow={30: 1.5, 31: 1.5},
                       stops={"car01": 10, "car02": 35})
    periods, _ = neutral.build(laps, elapsed(laps))
    rows = lottery.takers(stops, periods)
    # car01 stopped on lap 10 and had nothing left; only car02 counts.
    assert rows[0]["with a stop in hand"] == 1


def test_erased_measures_the_bunching_and_excludes_cars_that_pitted():
    laps, stops = race(cars=10, laps=40, slow={20: 1.5, 21: 1.5},
                       stops={"car03": 20})
    periods, _ = neutral.build(laps, elapsed(laps))
    rows = lottery.erased(periods, elapsed(laps), stops)
    assert len(rows) == 1
    assert rows[0]["pitted, excluded"] == 1
    assert rows[0]["cars"] == 9
    assert rows[0]["seconds erased"] > 0


def test_erased_is_zero_when_the_field_does_not_close_up():
    laps, _ = race(cars=10, laps=40, slow={20: 1.5, 21: 1.5}, bunch=False)
    periods, _ = neutral.build(laps, elapsed(laps))
    # Nothing was neutralised, so there is nothing to have been erased.
    assert lottery.erased(periods, elapsed(laps), []) == []


def test_the_leaders_lead_is_the_margin_over_second_not_over_last():
    standings = {"a": 0.0, "b": 1.5, "c": 40.0}
    assert lottery._lead(standings) == pytest.approx(1.5)
    assert np.isnan(lottery._lead({"a": 0.0}))


# --------------------------------------------------------------------
# the discount
# --------------------------------------------------------------------

def test_the_discount_recovers_a_planted_difference():
    laps, stops = [], []
    for round_ in range(1, 13):
        # Half the field pits under the safety car, half under green.
        plan = {f"car{n:02d}": 21 for n in range(5)}
        plan.update({f"car{n:02d}": 32 for n in range(5, 14)})
        these, those = race(cars=14, laps=40, round_=round_,
                            slow={20: 1.5, 21: 1.5, 22: 1.5}, stops=plan,
                            pit_cost=18.0 + 0.7 * round_, noise=0.15,
                            seed=round_)
        laps += these
        stops += those
    times = elapsed(laps)
    periods, _ = neutral.build(laps, times)
    priced, _ = lottery.price(laps, stops, periods)
    found = lottery.discount(priced, draws=400, seed=3)
    full = next(row for row in found["shelters"]
                if row["shelter"] == "both laps")
    # Both groups paid the same 22 seconds in this fixture, so there is
    # no discount to find and the interval has to say so.
    assert full["discount"] == pytest.approx(0.0, abs=1.5)
    assert full["lower"] < 0 < full["upper"]


def test_the_discount_finds_a_prize_when_one_was_planted():
    laps, stops = [], []
    for round_ in range(1, 13):
        plan = {f"car{n:02d}": 21 for n in range(5)}
        plan.update({f"car{n:02d}": 32 for n in range(5, 14)})
        these, those = race(cars=14, laps=40, round_=round_,
                            slow={20: 1.5, 21: 1.5, 22: 1.5}, stops=plan,
                            pit_cost=18.0 + 0.7 * round_, noise=0.15,
                            seed=round_)
        # Make the sheltered stops genuinely cheaper, by ten seconds,
        # on the lap they are actually taken.
        these = [Lap(**{**row.__dict__, "seconds": row.seconds - 10.0})
                 if row.driver in {f"car{n:02d}" for n in range(5)}
                 and row.lap == 21 else row
                 for row in these]
        laps += these
        stops += those
    periods, _ = neutral.build(laps, elapsed(laps))
    priced, _ = lottery.price(laps, stops, periods)
    found = lottery.discount(priced, draws=400, seed=3)
    full = next(row for row in found["shelters"]
                if row["shelter"] == "both laps")
    assert full["discount"] == pytest.approx(10.0, abs=1.5)
    assert full["lower"] > 0


def test_the_bootstrap_resamples_races_not_stops():
    # Twenty stops behind one safety car are not twenty independent
    # facts about what a safety car is worth. Clustering on the race
    # has to give a wider interval than treating each stop as its own
    # evidence, and here the races are deliberately made to differ.
    laps, stops = [], []
    for round_ in range(1, 7):
        plan = {f"car{n:02d}": 21 for n in range(5)}
        plan.update({f"car{n:02d}": 32 for n in range(5, 14)})
        these, those = race(cars=14, laps=40, round_=round_,
                            slow={20: 1.4, 21: 1.4, 22: 1.4},
                            stops=plan, pit_cost=14.0 + 3.0 * round_,
                            noise=0.2, seed=round_)
        laps += these
        stops += those
    periods, _ = neutral.build(laps, elapsed(laps))
    priced, _ = lottery.price(laps, stops, periods)
    found = lottery.discount(priced, draws=800, seed=5)
    full = next(row for row in found["shelters"]
                if row["shelter"] == "both laps")
    clustered = full["upper"] - full["lower"]

    # The same bootstrap, pretending the stops are independent.
    green = np.array([one.loss for one in priced if one.shelter == "green"])
    shelter = np.array([one.loss for one in priced
                        if one.shelter == "both laps"])
    rng = np.random.default_rng(5)
    naive = [float(np.median(rng.choice(green, green.size))
                   - np.median(rng.choice(shelter, shelter.size)))
             for _ in range(800)]
    loose = float(np.percentile(naive, 97.5) - np.percentile(naive, 2.5))

    assert clustered > loose
