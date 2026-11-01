"""One self-contained HTML file: charts inlined, no assets, no server."""

from __future__ import annotations

import base64
from pathlib import Path

CSS = """
body{font:15px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;max-width:1120px;
margin:40px auto;padding:0 20px;color:#16181d}
h1{margin-bottom:4px}h2{margin-top:38px;border-bottom:1px solid #e3e6ea;
padding-bottom:6px}
.sub{color:#5b6472;margin-top:0}
.tiles{display:flex;gap:14px;flex-wrap:wrap;margin:22px 0}
.tile{flex:1;min-width:150px;background:#f6f8fa;border:1px solid #e3e6ea;
border-radius:9px;padding:14px 16px}
.tile .v{font-size:25px;font-weight:650;letter-spacing:-.5px}
.tile .k{font-size:11px;text-transform:uppercase;letter-spacing:.07em;
color:#5b6472;margin-top:3px}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:14px}
th,td{border:1px solid #e3e6ea;padding:7px 10px;text-align:right}
th:first-child,td:first-child{text-align:left}
th{background:#f6f8fa;font-weight:600}
td.good{color:#17803d}td.bad{color:#b4232c}
img{width:100%;margin:14px 0;border:1px solid #e3e6ea;border-radius:7px}
.note{background:#fff8e6;border-left:3px solid #d9a441;padding:11px 15px;
margin:18px 0;font-size:14px}
code{background:#f0f2f5;padding:1px 5px;border-radius:4px;font-size:13px}
"""


def _img(path: Path) -> str:
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f'<img src="data:image/png;base64,{encoded}" alt="{Path(path).stem}">'


def _counts(census: dict) -> str:
    return "".join(f"<tr><td>{key}</td><td>{value:,}</td></tr>"
                   for key, value in census.items())


def _period_row(one) -> str:
    colour = {"neutralised": ' class="good"',
              "conditions": ' class="bad"'}.get(one.kind, "")
    change = "-" if one.change != one.change else f"{one.change:.2f}"
    return (f"<tr><td>r{one.round} {one.circuit}</td>"
            f"<td>{one.first}-{one.last}</td><td>{one.peak:.2f}</td>"
            f"<td>{one.before:.1f}</td><td>{one.after:.1f}</td>"
            f"<td>{change}</td><td{colour}>{one.kind}</td></tr>")


def _gone_row(row: dict) -> str:
    before = row["leader's lead before"]
    after = row["leader's lead after"]
    return (f"<tr><td>r{row['round']} {row['circuit']}</td>"
            f"<td>{row['laps']}</td><td>{row['cars']}</td>"
            f"<td>{row['seconds erased']:.0f}</td>"
            f"<td>{row['worst hit']:.0f}</td>"
            f"<td>{before:.1f} &rarr; {after:.1f}</td></tr>")


def _discount_row(row: dict) -> str:
    clear = row["lower"] > 0
    cell = ' class="good"' if clear else ""
    return (f"<tr><td>{row['shelter']}</td><td>{row['median']:.2f}</td>"
            f"<td>{row['discount']:+.2f}</td>"
            f"<td>{row['lower']:+.2f} to {row['upper']:+.2f}</td>"
            f"<td{cell}>{'yes' if clear else 'no'}</td></tr>")


def build(*, periods, census, check, pit_census, priced, table, found, took,
          gone, seasons, figures, out_path: Path) -> Path:
    full = next(row for row in found["shelters"]
                if row["shelter"] == "both laps")
    worst = next(row for row in found["shelters"]
                 if row["shelter"] == "in-lap only")
    held = sum(row["with a stop in hand"] for row in took)
    used = sum(row["took it here"] for row in took)
    erased = sum(row["seconds erased"] for row in gone)

    tiles = [("a green-flag stop", f"{found['green']:.1f} s"),
             ("sheltered by a safety car", f"{full['median']:.1f} s"),
             ("the prize", f"{full['discount']:+.1f} s"),
             ("advantage deleted in 2023", f"{erased:,.0f} s")]
    tiles_html = "".join(
        f'<div class="tile"><div class="v">{v}</div><div class="k">{k}</div></div>'
        for k, v in tiles)

    price_html = "".join(
        f"<tr><td>{row['shelter']}</td><td>{row['stops']}</td>"
        f"<td>{row['median']:.2f}</td>"
        f"<td>{row['lower']:.2f} to {row['upper']:.2f}</td></tr>"
        for row in table)

    discount_html = "".join(_discount_row(row)
                            for row in found["shelters"])
    gone_html = "".join(_gone_row(row) for row in gone)

    years = ", ".join(str(one) for one in seasons)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>The safety car lottery</title><style>{CSS}</style></head>
<body>
<h1>The safety car lottery</h1>
<p class="sub">Formula 1, {years}. What a safety car is worth, who gets to
use it, and how much earned advantage it deletes. Nothing in the source
says where the safety cars were; they are found in the lap times and
then told apart from the weather.</p>
{tiles_html}

<h2>Finding them, and knowing what you found</h2>
<p>A safety car is obvious in lap times: everybody is thirty to sixty
per cent slower at once. That part is four lines of code. The hard part
is that <em>rain does the same thing</em>, and a detector that does not
ask why will price a lottery that never happened.</p>
{_img(figures['separation'])}
<p>The gaps separate them. Under a safety car the field is bunched up
deliberately and the spread of the cars collapses, typically to a fifth.
Weather does the opposite, because drivers differ far more in the wet.
Same lap-time signature, opposite effect on the order.</p>
<table><tr><th>what</th><th>count</th></tr>{_counts(census)}</table>
<table><tr><th>race</th><th>laps</th><th>peak</th><th>spread before</th>
<th>after</th><th>change</th><th>reading</th></tr>
{"".join(_period_row(one) for one in periods)}</table>

<h2>A check that uses no lap times</h2>
{_img(figures['validation'])}
<p>A safety car makes a pit stop cheap, so if these laps really are
safety cars the stops should pile up on them.
<b>{check['share of stops']:.1%} of the season's {check['stops']:,} pit
stops happened on {check['share of race-laps']:.1%} of its race-laps, an
enrichment of {check['enrichment']:.2f} times.</b> Nothing downstream
depends on this number; it is here so the detector can be wrong in
public.</p>

<h2>What a stop costs</h2>
<table><tr><th>step</th><th>stops</th></tr>{_counts(pit_census)}</table>
{_img(figures['price'])}
<table><tr><th>shelter</th><th>stops</th><th>median loss, s</th>
<th>quartiles</th></tr>{price_html}</table>
{_img(figures['interval'])}
<table><tr><th>shelter</th><th>median, s</th><th>discount</th>
<th>95% interval</th><th>excludes zero</th></tr>{discount_html}</table>
<div class="note"><b>A stop sheltered on both laps costs
{full['median']:.1f} s against {found['green']:.1f} s under green: a
prize of {full['discount']:.1f} s, about
{full['discount'] / found['green']:.0%} of a pit stop.</b> But a stop
with only its in-lap sheltered costs {worst['median']:.1f} s &mdash;
<em>more</em> than a green one. The car dives in behind the safety car
and rejoins just as the field is released, paying the pit lane's price
and collecting none of the discount.</div>

<h2>Who was in a position to use it</h2>
{_img(figures['winners'])}
<p>Over {len(took)} neutralisations, <b>{used} of {held} cars that still
had a stop to make took it there ({used / held:.0%})</b>. The rest were
already on their last set and watched their rivals buy the same stop for
a fifth of the price. Which group a car was in depended on where it
happened to be in its stint when somebody else crashed.</p>

<h2>And what the bunching deleted</h2>
{_img(figures['destroyed'])}
<table><tr><th>race</th><th>laps</th><th>cars</th><th>seconds erased</th>
<th>worst hit</th><th>leader's lead</th></tr>{gone_html}</table>
<p>Counting only the cars that did not pit anywhere in the window, so
this is the bunching alone and not the stops. <b>{erased:,.0f} seconds
of earned advantage deleted across the season.</b></p>

<h2>What this does not do</h2>
<p>It does not know where the safety cars actually were &mdash; it
infers them, and the three-way split leaves five periods unclear rather
than forcing them. It cannot separate a full safety car from a virtual
one, which have different slowdowns and different prizes. It prices a
stop against staying out, which is not the same as the positions
gained, because that depends on who else stopped. And it is one season:
eighteen neutralisations is why the interval on the prize is as wide as
it is.</p>

<p class="sub">Generated by <code>run.py</code>. Lap times, pit stops
and results from the Jolpica mirror of the Ergast schema. The cleaning
rules are carried over from the stint-degradation, undercut-effect,
pace-to-pass and driver-or-car projects.</p>
</body></html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
