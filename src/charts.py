"""Six figures, written straight to PNG so the README renders on GitHub."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402

INK = "#16181d"
MUTED = "#5b6472"
GRID = "#e3e6ea"
GOOD = "#17803d"
BAD = "#b4232c"
LINE = "#1f5fa8"
WARM = "#d9a441"
SOFT = "#aab4c0"

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.titlesize": 12, "figure.dpi": 130, "savefig.bbox": "tight"})

COLOURS = {"neutralised": LINE, "conditions": WARM,
           "unclear": SOFT, "to the flag": "#7a6fa8"}


def _frame(axis, title: str, subtitle: str = "") -> None:
    axis.set_title(title, loc="left", pad=22 if subtitle else 8,
                   fontweight="bold")
    if subtitle:
        axis.text(0, 1.02, subtitle, transform=axis.transAxes,
                  fontsize=9, color=MUTED, va="bottom")
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.set_axisbelow(True)


def separation(path: Path, periods) -> Path:
    """The whole argument: what slowed the field against what it did to it."""
    figure, axis = plt.subplots(figsize=(8.4, 5.4))
    for kind in ("neutralised", "conditions", "unclear", "to the flag"):
        rows = [one for one in periods
                if one.kind == kind and np.isfinite(one.change)]
        if not rows:
            continue
        axis.scatter([one.change for one in rows],
                     [one.peak for one in rows],
                     s=[18 + 14 * one.laps for one in rows],
                     color=COLOURS[kind], alpha=0.85, edgecolor="white",
                     linewidth=0.8, label=f"{kind} ({len(rows)})", zorder=3)
    axis.axvline(1.0, color=INK, linewidth=1.0, zorder=2)
    axis.axvspan(0, 0.80, color=LINE, alpha=0.06, zorder=1)
    axis.axvspan(1.20, 6, color=WARM, alpha=0.07, zorder=1)
    axis.set_xscale("log")
    axis.set_xlim(0.07, 6)
    axis.set_xticks([0.1, 0.25, 0.5, 1, 2, 4])
    axis.set_xticklabels(["0.1", "0.25", "0.5", "1", "2", "4"])
    axis.set_xlabel("what the field's spread was multiplied by\n"
                    "(left: bunched up    right: strung out)")
    axis.set_ylim(1.0, 2.1)
    axis.set_ylabel("how slow the worst slow lap was, x green pace")
    axis.grid(color=GRID, linewidth=0.8)
    axis.legend(frameon=False, fontsize=9, loc="lower right")
    _frame(axis, "Lap times cannot tell you why the field slowed",
           "every period of a slow field in 2023; the gaps separate them")
    axis.text(0.145, 1.9, "a safety car\nbunches the field", fontsize=9,
              color=LINE, ha="center")
    axis.text(3.0, 1.9, "weather\nspreads it out", fontsize=9,
              color=WARM, ha="center")
    out = path / "separation.png"
    figure.savefig(out)
    plt.close(figure)
    return out


def validation(path: Path, check, sensitivity) -> Path:
    """The detector checked against something that is not a lap time."""
    figure, (left, right) = plt.subplots(
        1, 2, figsize=(9.0, 3.6), gridspec_kw={"width_ratios": [1, 1.25]})

    shares = [100 * check["share of race-laps"], 100 * check["share of stops"]]
    bars = left.bar(["of the season's\nrace-laps", "of the season's\npit stops"],
                    shares, color=[SOFT, LINE], width=0.58)
    for bar, value in zip(bars, shares):
        left.text(bar.get_x() + bar.get_width() / 2, value + 0.6,
                  f"{value:.1f}%", ha="center", fontsize=10,
                  fontweight="bold")
    left.set_ylim(0, max(shares) * 1.35)
    left.set_ylabel("per cent")
    left.grid(axis="y", color=GRID, linewidth=0.8)
    _frame(left, "Stops pile up on these laps",
           f"{check['enrichment']:.1f} times over")

    values = [row["neutralised"] for row in sensitivity]
    marks = [row["threshold"] for row in sensitivity]
    right.plot(marks, values, marker="o", color=LINE, linewidth=1.8)
    for mark, value in zip(marks, values):
        right.annotate(f"{value}", (mark, value), textcoords="offset points",
                       xytext=(0, 8), ha="center", fontsize=9)
    right.set_ylim(0, max(values) * 1.4)
    right.set_xlabel("a lap counts as slow above this x green pace")
    right.set_ylabel("safety cars found")
    right.grid(color=GRID, linewidth=0.8)
    _frame(right, "The threshold is not doing the work",
           "the count barely moves across any sensible choice")

    figure.tight_layout()
    out = path / "validation.png"
    figure.savefig(out)
    plt.close(figure)
    return out


def price(path: Path, priced, table) -> Path:
    """What a stop costs, by how much of it was sheltered."""
    figure, axis = plt.subplots(figsize=(8.4, 4.6))
    order = [row["shelter"] for row in table]
    spots = np.arange(len(order))
    for spot, name in enumerate(order):
        losses = np.array([one.loss for one in priced if one.shelter == name])
        jitter = np.random.default_rng(spot).normal(0, 0.075, losses.size)
        axis.scatter(losses, np.full(losses.size, spot) + jitter, s=14,
                     color=SOFT, alpha=0.55, zorder=2)
    for spot, row in enumerate(table):
        colour = LINE if row["shelter"] == "green" else GOOD
        axis.plot([row["lower"], row["upper"]], [spot, spot],
                  color=colour, linewidth=3.0, solid_capstyle="round",
                  zorder=3)
        axis.scatter([row["median"]], [spot], s=120, color=colour,
                     edgecolor="white", linewidth=1.2, zorder=4)
        axis.text(row["median"], spot + 0.30, f"{row['median']:.1f} s",
                  ha="center", fontsize=9.5, color=colour,
                  fontweight="bold")
    axis.axvline(0, color=INK, linewidth=1.0, zorder=1)
    axis.set_yticks(spots)
    axis.set_yticklabels([f"{row['shelter']}\n({row['stops']} stops)"
                          for row in table])
    axis.invert_yaxis()
    axis.set_xlim(-45, 95)
    axis.set_xlabel("seconds lost against staying out")
    axis.grid(axis="x", color=GRID, linewidth=0.8)
    _frame(axis, "A stop under a safety car costs a fifth of the price",
           "each dot is one stop; the bar is the median and the quartiles")
    out = path / "price.png"
    figure.savefig(out)
    plt.close(figure)
    return out


def interval(path: Path, found) -> Path:
    """The discount with the uncertainty that one season actually supports."""
    figure, axis = plt.subplots(figsize=(8.0, 3.2))
    rows = found["shelters"]
    spots = np.arange(len(rows))
    for spot, row in enumerate(rows):
        good = row["lower"] > 0
        colour = GOOD if good else (BAD if row["upper"] < 0 else SOFT)
        axis.plot([row["lower"], row["upper"]], [spot, spot], color=colour,
                  linewidth=3.2, solid_capstyle="round", zorder=3)
        axis.scatter([row["discount"]], [spot], s=110, color=colour,
                     edgecolor="white", linewidth=1.2, zorder=4)
        axis.text(row["upper"] + 1.4, spot, f"{row['discount']:+.1f} s",
                  va="center", fontsize=9.5, color=colour,
                  fontweight="bold")
    axis.axvline(0, color=INK, linewidth=1.2, zorder=2)
    axis.set_yticks(spots)
    axis.set_yticklabels([row["shelter"] for row in rows])
    axis.invert_yaxis()
    axis.set_xlim(-26, 42)
    axis.set_xlabel("seconds saved against a green-flag stop "
                    "(95% interval, races resampled)")
    axis.grid(axis="x", color=GRID, linewidth=0.8)
    _frame(axis, "Only a stop sheltered on both laps is worth anything",
           "pitting as the safety car ends costs more than not using it")
    out = path / "interval.png"
    figure.savefig(out)
    plt.close(figure)
    return out


def winners(path: Path, took) -> Path:
    """Who was in a position to use each safety car."""
    figure, axis = plt.subplots(figsize=(8.4, 5.0))
    rows = sorted(took, key=lambda one: one["share"])
    spots = np.arange(len(rows))
    held = [one["with a stop in hand"] for one in rows]
    used = [one["took it here"] for one in rows]
    axis.barh(spots, held, color=GRID, height=0.62, label="had a stop in hand")
    axis.barh(spots, used, color=LINE, height=0.62, label="took it here")
    for spot, one in enumerate(rows):
        axis.text(one["with a stop in hand"] + 0.3, spot,
                  f"{one['share']:.0%}", va="center", fontsize=9,
                  color=MUTED)
    axis.set_yticks(spots)
    axis.set_yticklabels([f"r{one['round']} {one['circuit'][:13]} "
                          f"({one['laps']})" for one in rows], fontsize=8.5)
    axis.set_xlabel("cars")
    axis.set_xlim(0, max(held) * 1.18)
    axis.grid(axis="x", color=GRID, linewidth=0.8)
    axis.legend(frameon=False, fontsize=9, loc="upper right")
    _frame(axis, "Half the field could use it; half could not",
           "whether a car still had a stop in hand was decided by "
           "someone else's accident")
    out = path / "winners.png"
    figure.savefig(out)
    plt.close(figure)
    return out


def destroyed(path: Path, gone) -> Path:
    """The leader's advantage, before and after the bunching."""
    figure, axis = plt.subplots(figsize=(8.4, 4.8))
    rows = sorted(gone, key=lambda one: -one["seconds erased"])
    spots = np.arange(len(rows))
    erased = [one["seconds erased"] for one in rows]
    axis.barh(spots, erased, color=LINE, height=0.6)
    for spot, one in enumerate(rows):
        axis.text(one["seconds erased"] + 6, spot,
                  f"worst car {one['worst hit']:.0f} s", va="center",
                  fontsize=8.5, color=MUTED)
    axis.set_yticks(spots)
    axis.set_yticklabels([f"r{one['round']} {one['circuit'][:13]} "
                          f"({one['laps']})" for one in rows], fontsize=8.5)
    axis.set_xlim(0, max(erased) * 1.42)
    axis.set_xlabel("seconds of advantage deleted, summed over the cars "
                    "that stayed out")
    axis.grid(axis="x", color=GRID, linewidth=0.8)
    _frame(axis, f"{sum(erased):,.0f} seconds of earned advantage, deleted",
           "cars that pitted in the window are excluded, so this is the "
           "bunching alone")
    out = path / "destroyed.png"
    figure.savefig(out)
    plt.close(figure)
    return out


def draw(path: Path, **kwargs) -> dict[str, Path]:
    path.mkdir(parents=True, exist_ok=True)
    return {
        "separation": separation(path, kwargs["periods"]),
        "validation": validation(path, kwargs["check"],
                                 kwargs["sensitivity"]),
        "price": price(path, kwargs["priced"], kwargs["table"]),
        "interval": interval(path, kwargs["found"]),
        "winners": winners(path, kwargs["took"]),
        "destroyed": destroyed(path, kwargs["gone"]),
    }
