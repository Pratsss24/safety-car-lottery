"""What a safety car is worth, and to whom.

Run with no arguments; the season is cached, so a second run costs nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import charts                                              # noqa: E402
import data                                                # noqa: E402
import gaps                                                # noqa: E402
import lottery                                             # noqa: E402
import neutral                                             # noqa: E402
import report                                              # noqa: E402

SEASONS = (2023,)
OUT = ROOT / "out"

_log: list[str] = []


def say(line: str = "") -> None:
    print(line)
    _log.append(line)


def main() -> None:
    laps, stops, results = data.load(SEASONS)
    times = gaps.elapsed(laps)
    say(f"{len(laps):,} lap times, {len(stops):,} pit stops")

    # ---- what slowed the field, and why -------------------------------
    periods, census = neutral.build(laps, times)
    say()
    say("periods when the whole field was slow")
    for key, value in census.items():
        say(f"  {key:44s} {value:6d}")
    say("  lap times say the field slowed; they cannot say why. Rain does "
        "it too, and in 2023 it does it three times")

    say()
    say(f"  {'race':5s} {'circuit':16s} {'laps':7s} {'peak':>5s} "
        f"{'onset':>5s} {'before':>7s} {'after':>7s} {'change':>7s}  reading")
    for one in periods:
        say(f"  r{one.round:<4d} {one.circuit[:16]:16s} "
            f"{f'{one.first}-{one.last}':7s} {one.peak:5.2f} "
            f"{one.onset:5.2f} {one.before:7.1f} {one.after:7.1f} "
            f"{one.change:7.2f}  {one.kind}")
    say("  a safety car bunches the field up on purpose, so the spread of "
        "the cars collapses. Weather spreads it out, because drivers "
        "differ more in the wet. That one measurement separates two "
        "identical lap-time signatures")

    # ---- is the detector finding anything real? ------------------------
    check = neutral.clustering(stops, periods, census)
    say()
    say("a check that uses no lap times at all")
    for key, value in check.items():
        shown = f"{value:,.4f}" if isinstance(value, float) else f"{value:,}"
        say(f"  {key:34s} {shown:>12s}")
    say(f"  {check['share of stops']:.1%} of the season's stops happened on "
        f"{check['share of race-laps']:.1%} of its laps, an enrichment of "
        f"{check['enrichment']:.2f} times. A safety car makes a stop cheap; "
        f"rain does not, and the enrichment rises when the weather periods "
        f"are taken out, which is the detector being right about something "
        f"it was not fitted on")

    say()
    say("does the threshold do the work?")
    for row in neutral.sensitivity(laps, times):
        say(f"  slow above {row['threshold']:.2f} x green -> "
            f"{row['periods']:2d} periods, {row['neutralised']:2d} "
            f"neutralised, {row['laps']:3d} laps")

    # ---- what a stop costs --------------------------------------------
    priced, pit_census = lottery.price(laps, stops, periods)
    say()
    say("every pit stop, priced against staying out")
    for key, value in pit_census.items():
        say(f"  {key:52s} {value:5d}")

    say()
    for row in lottery.table(priced):
        say(f"  {row['shelter']:14s} n={row['stops']:3d}  median "
            f"{row['median']:6.2f} s   quartiles "
            f"[{row['lower']:6.2f}, {row['upper']:6.2f}]")

    found = lottery.discount(priced)
    say()
    say(f"a stop under green flags costs {found['green']:.2f} s against "
        f"staying out")
    for row in found["shelters"]:
        say(f"  sheltered, {row['shelter']:13s} {row['median']:6.2f} s  "
            f"discount {row['discount']:+6.2f}  "
            f"95% [{row['lower']:+6.2f}, {row['upper']:+6.2f}]")
    full = next(row for row in found["shelters"]
                if row["shelter"] == "both laps")
    worst = next(row for row in found["shelters"]
                 if row["shelter"] == "in-lap only")
    say(f"  so the prize is {full['discount']:.1f} s, about "
        f"{full['discount'] / found['green']:.0%} of a stop, and the "
        f"interval does not contain zero")
    say(f"  pitting with only the in-lap sheltered costs "
        f"{worst['median']:.1f} s, which is *more* than a green stop: the "
        f"car dives in behind the safety car and rejoins as the field is "
        f"released")

    # ---- who got to use it ---------------------------------------------
    took = lottery.takers(stops, periods)
    held = sum(row["with a stop in hand"] for row in took)
    used = sum(row["took it here"] for row in took)
    say()
    say(f"over {len(took)} neutralisations, {used} of {held} cars that still "
        f"had a stop to make took it there ({used / held:.0%})")
    say("  the other half were already on their last set, and watched their "
        "rivals get the same stop for a fifth of the price. Nothing they "
        "did decided which group they were in")

    # ---- what the bunching deleted --------------------------------------
    gone = lottery.erased(periods, times, stops)
    say()
    say("advantage deleted by the bunching, counting only cars that did "
        "not pit in the window")
    say(f"  {'race':5s} {'circuit':16s} {'laps':7s} {'cars':>4s} "
        f"{'erased':>8s} {'worst':>7s}   lead before -> after")
    for row in gone:
        before = row["leader's lead before"]
        after = row["leader's lead after"]
        say(f"  r{row['round']:<4d} {row['circuit'][:16]:16s} "
            f"{row['laps']:7s} {row['cars']:4d} "
            f"{row['seconds erased']:8.1f} {row['worst hit']:7.1f}   "
            f"{before:5.1f} -> {after:.1f}")
    say(f"  {sum(row['seconds erased'] for row in gone):,.0f} seconds of "
        f"earned advantage deleted across the season")

    # ---- output ---------------------------------------------------------
    figures = charts.draw(
        OUT, periods=periods, census=census, check=check, priced=priced,
        table=lottery.table(priced), found=found, took=took, gone=gone,
        sensitivity=neutral.sensitivity(laps, times))
    path = report.build(
        periods=periods, census=census, check=check, pit_census=pit_census,
        priced=priced, table=lottery.table(priced), found=found, took=took,
        gone=gone, seasons=SEASONS, figures=figures,
        out_path=OUT / "report.pdf")

    say()
    say(f"report  {path}")
    for name, figure in figures.items():
        say(f"figure  {figure}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "_run.txt").write_text("\n".join(_log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
