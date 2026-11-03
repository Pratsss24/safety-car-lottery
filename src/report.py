"""The report, as a printable PDF built out of matplotlib pages.

`paper.py` owns the page furniture; everything here is this project's own
argument, in the order the argument runs.
"""

from __future__ import annotations

from pathlib import Path

from paper import Paper


def _periods(periods) -> tuple[list[str], list[list[str]]]:
    rows = []
    for one in periods:
        # A change that is not a number is a period with nothing to
        # compare against, not a change of zero.
        change = "—" if one.change != one.change else f"{one.change:.2f}"
        rows.append([f"r{one.round} {one.circuit}",
                     f"{one.first}–{one.last}", f"{one.peak:.2f}",
                     f"{one.before:.1f}", f"{one.after:.1f}", change,
                     one.kind])
    return (["race", "laps", "peak", "spread before", "after", "change",
             "reading"], rows)


def _discounts(found: dict) -> tuple[list[str], list[list[str]]]:
    rows = [[row["shelter"], f"{row['median']:.2f}",
             f"{row['discount']:+.2f}",
             f"[{row['lower']:+.2f}, {row['upper']:+.2f}]",
             "yes" if row["lower"] > 0 else "no"]
            for row in found["shelters"]]
    return (["shelter", "median, s", "discount", "95% interval",
             "excludes zero"], rows)


def _gone(gone) -> tuple[list[str], list[list[str]]]:
    rows = []
    for row in gone:
        before = row["leader's lead before"]
        after = row["leader's lead after"]
        rows.append([f"r{row['round']} {row['circuit']}", str(row["laps"]),
                     str(row["cars"]), f"{row['seconds erased']:.0f}",
                     f"{row['worst hit']:.0f}",
                     f"{before:.1f} → {after:.1f}"])
    return (["race", "laps", "cars", "seconds erased", "worst hit",
             "leader's lead"], rows)


def build(*, periods, census, check, pit_census, priced, table, found, took,
          gone, seasons, figures, out_path: Path) -> Path:
    full = next(row for row in found["shelters"]
                if row["shelter"] == "both laps")
    worst = next(row for row in found["shelters"]
                 if row["shelter"] == "in-lap only")
    held = sum(row["with a stop in hand"] for row in took)
    used = sum(row["took it here"] for row in took)
    erased = sum(row["seconds erased"] for row in gone)
    years = ", ".join(str(one) for one in seasons)
    out = Path(out_path)
    out = out.with_name("report.pdf") if out.suffix != ".pdf" else out
    out.parent.mkdir(parents=True, exist_ok=True)

    with Paper(out, "The safety car lottery",
               f"Formula 1, {years}. What a safety car is worth, who gets "
               f"to use it, and how much earned advantage it deletes.") \
            as paper:

        paper.cover(
            headline=f"A sheltered pit stop costs "
                     f"{full['discount']:.1f} s less",
            small=f"A stop sheltered on both laps costs "
                  f"{full['median']:.1f} s against {found['green']:.1f} s "
                  f"under green — about "
                  f"{full['discount'] / found['green']:.0%} of a pit stop, "
                  f"handed to whoever happened to be at the right point "
                  f"in their stint when somebody else crashed.",
            tiles=[("a green-flag stop", f"{found['green']:.1f} s"),
                   ("sheltered by a safety car",
                    f"{full['median']:.1f} s"),
                   ("the prize", f"{full['discount']:+.1f} s"),
                   ("advantage deleted", f"{erased:,.0f} s")],
            blurb="Nothing in the source says where the safety cars were. "
                  "They are found in the lap times and then told apart "
                  "from the weather, which produces the same lap-time "
                  "signature and the opposite effect on the order.",
            figure_path=figures["interval"])

        paper.section(
            "Finding them, and knowing what you found",
            note="A safety car is obvious in lap times: everybody is "
                 "thirty to sixty per cent slower at once. That part is "
                 "four lines of code.",
            warn="The hard part is that rain does the same thing, and a "
                 "detector that does not ask why will price a lottery "
                 "that never happened.",
            body="The gaps separate them. Under a safety car the field is "
                 "bunched up deliberately and the spread of the cars "
                 "collapses, typically to a fifth. Weather does the "
                 "opposite, because drivers differ far more in the wet. "
                 "Same lap-time signature, opposite effect on the order.",
            figure_path=figures["separation"],
            table=(["what", "count"],
                   [[key, f"{value:,}"] for key, value in census.items()]))

        paper.section("Every period the detector found", table=_periods(periods))

        paper.section(
            "A check that uses no lap times",
            note="A safety car makes a pit stop cheap, so if these laps "
                 "really are safety cars the stops should pile up on "
                 "them.",
            body=f"{check['share of stops']:.1%} of the season's "
                 f"{check['stops']:,} pit stops happened on "
                 f"{check['share of race-laps']:.1%} of its race-laps, an "
                 f"enrichment of {check['enrichment']:.2f} times.\n\n"
                 f"Nothing downstream depends on this number. It is here "
                 f"so the detector can be wrong in public.",
            figure_path=figures["validation"])

        paper.section(
            "What a stop costs",
            warn=f"A stop with only its in-lap sheltered costs "
                 f"{worst['median']:.1f} s — more than a green one. "
                 f"The car dives in behind the safety car and rejoins "
                 f"just as the field is released, paying the pit lane's "
                 f"price and collecting none of the discount.",
            figure_path=figures["price"],
            table=(["shelter", "stops", "median loss, s", "quartiles"],
                   [[row["shelter"], str(row["stops"]),
                     f"{row['median']:.2f}",
                     f"[{row['lower']:.2f}, {row['upper']:.2f}]"]
                    for row in table]))

        paper.section(
            "The prize, with an interval on it",
            table=_discounts(found),
            after="Each discount is measured against the green-flag "
                  "median, and the interval is wide because eighteen "
                  "neutralisations is not many.")

        paper.section(
            "Who was in a position to use it",
            body=f"Over {len(took)} neutralisations, {used} of {held} cars "
                 f"that still had a stop to make took it there "
                 f"({used / held:.0%}). The rest were already on their "
                 f"last set and watched their rivals buy the same stop "
                 f"for a fifth of the price.\n\n"
                 f"Which group a car was in depended on where it happened "
                 f"to be in its stint when somebody else crashed. That is "
                 f"the lottery in the title: not the discount, but who is "
                 f"eligible for it.",
            figure_path=figures["winners"])

        paper.section(
            "And what the bunching deleted",
            note="Counting only the cars that did not pit anywhere in the "
                 "window, so this is the bunching alone and not the "
                 "stops.",
            body=f"{erased:,.0f} seconds of earned advantage deleted "
                 f"across the season.",
            figure_path=figures["destroyed"], table=_gone(gone))

        paper.section(
            "What this does not do",
            body="It does not know where the safety cars actually were "
                 "— it infers them, and the three-way split leaves "
                 "five periods unclear rather than forcing them. It "
                 "cannot separate a full safety car from a virtual one, "
                 "which have different slowdowns and different prizes. It "
                 "prices a stop against staying out, which is not the "
                 "same as the positions gained, because that depends on "
                 "who else stopped. And it is one season: eighteen "
                 "neutralisations is why the interval on the prize is as "
                 "wide as it is.",
            table=(["step", "stops"],
                   [[key, f"{value:,}"]
                    for key, value in pit_census.items()]),
            after="Lap times, pit stops and results from the Jolpica "
                  "mirror of the Ergast schema.")

    return out
