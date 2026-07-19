"""Generate profile cards for the README, in the
nikoloz.de evening-garden palette. Runs in CI with GITHUB_TOKEN."""

import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

CHARCOAL = "#101914"
RAISED = "#1d2a20"
INK = "#f4ead7"
ACCENT = "#d7a84f"
ACCENT_BRIGHT = "#e8bc66"
BORDER = "#30362f"
LANG_RAMP = ["#e8bc66", "#d7a84f", "#9aa84f", "#8fae72", "#5c7a3f", "#33532f"]
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar { totalContributions }
    }
  }
}
"""

CALENDAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""

STYLE = """
    .sans { font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; }
    .num { font-variant-numeric: tabular-nums; }
    .up { opacity: 0; animation: rise 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
    .d1 { animation-delay: 0.05s; }
    .d2 { animation-delay: 0.20s; }
    .d3 { animation-delay: 0.35s; }
    .d4 { animation-delay: 0.50s; }
    @keyframes rise {
      from { opacity: 0; transform: translateY(10px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    @media (prefers-reduced-motion: reduce) { .up { animation: none; opacity: 1; } }
"""


@dataclass(frozen=True)
class StreakSummary:
    total: int
    first_date: date
    current: int
    current_start: date | None
    current_end: date | None
    longest: int
    longest_start: date | None
    longest_end: date | None


def graphql(query: str, variables: dict, token: str) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    return data["data"]


def fetch(login: str, token: str) -> dict:
    return graphql(QUERY, {"login": login}, token)["user"]


def fetch_contribution_days(
    login: str,
    token: str,
    created_at: str,
    through: date | None = None,
) -> dict[date, int]:
    first_date = date.fromisoformat(created_at[:10])
    last_date = through or datetime.now(UTC).date()
    contributions: dict[date, int] = {}
    period_start = first_date

    # GitHub limits each contributionsCollection request to a one-year window.
    while period_start <= last_date:
        period_end = min(period_start + timedelta(days=364), last_date)
        variables = {
            "login": login,
            "from": f"{period_start.isoformat()}T00:00:00Z",
            "to": f"{period_end.isoformat()}T23:59:59Z",
        }
        calendar = graphql(CALENDAR_QUERY, variables, token)["user"][
            "contributionsCollection"
        ]["contributionCalendar"]
        for week in calendar["weeks"]:
            for contribution_day in week["contributionDays"]:
                day = date.fromisoformat(contribution_day["date"])
                if period_start <= day <= period_end:
                    contributions[day] = contribution_day["contributionCount"]
        period_start = period_end + timedelta(days=1)

    day = first_date
    while day <= last_date:
        contributions.setdefault(day, 0)
        day += timedelta(days=1)
    return contributions


def calculate_streaks(contributions: dict[date, int], today: date) -> StreakSummary:
    first_date = min(contributions, default=today)
    total = sum(contributions.values())
    longest = 0
    longest_start: date | None = None
    longest_end: date | None = None
    run = 0
    run_start: date | None = None

    day = first_date
    while day <= today:
        if contributions.get(day, 0) > 0:
            if run == 0:
                run_start = day
            run += 1
            if run > longest:
                longest = run
                longest_start = run_start
                longest_end = day
        else:
            run = 0
            run_start = None
        day += timedelta(days=1)

    current_end = today
    if contributions.get(current_end, 0) == 0:
        current_end -= timedelta(days=1)
    current_start = current_end
    while current_start >= first_date and contributions.get(current_start, 0) > 0:
        current_start -= timedelta(days=1)
    current_start += timedelta(days=1)
    current = (current_end - current_start).days + 1
    if contributions.get(current_end, 0) == 0:
        current = 0
        current_start = None
        current_end = None

    return StreakSummary(
        total=total,
        first_date=first_date,
        current=current,
        current_start=current_start,
        current_end=current_end,
        longest=longest,
        longest_start=longest_start,
        longest_end=longest_end,
    )


def fmt(n: int) -> str:
    return f"{n:,}"


def card(inner: str, width: int = 495, height: int = 195, label: str = "") -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" role="img" aria-label="{label}">
  <style>{STYLE}</style>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="15.5" fill="{CHARCOAL}" stroke="{BORDER}"/>
{inner}
</svg>
"""


def stats_svg(user: dict) -> str:
    repos = user["repositories"]
    contrib = user["contributionsCollection"]
    stars = sum(r["stargazerCount"] for r in repos["nodes"])
    total = contrib["contributionCalendar"]["totalContributions"]
    languages = {
        e["node"]["name"] for r in repos["nodes"] for e in r["languages"]["edges"]
    }

    # only show stats that have something to say
    rows = [
        (label, value)
        for label, value in [
            ("Commits, last year", contrib["totalCommitContributions"]),
            ("Repositories", repos["totalCount"]),
            ("Languages used", len(languages)),
            ("Stars earned", stars),
            ("Pull requests", contrib["totalPullRequestContributions"]),
            ("Followers", user["followers"]["totalCount"]),
        ]
        if value > 0
    ][:6]

    parts = [
        f'  <text class="sans up d1" x="24" y="40" font-size="15" font-weight="600" letter-spacing="0.5" fill="{ACCENT_BRIGHT}">GitHub, at a glance</text>',
        f'  <text class="sans num up d2" x="471" y="58" text-anchor="end" font-size="52" font-weight="300" fill="none" stroke="{INK}" stroke-opacity="0.22">{fmt(total)}</text>',
        f'  <text class="sans up d2" x="471" y="76" text-anchor="end" font-size="10.5" letter-spacing="1.5" fill="{INK}" opacity="0.5">CONTRIBUTIONS IN THE LAST YEAR</text>',
    ]

    # 2 columns x 3 rows starting under the watermark
    for i, (label, value) in enumerate(rows):
        col, row = divmod(i, 3)
        x_label = 24 + col * 240
        x_value = 214 + col * 257
        y = 116 + row * 27
        d = "d3" if col == 0 else "d4"
        parts.append(
            f'  <text class="sans up {d}" x="{x_label}" y="{y}" font-size="13" fill="{INK}" opacity="0.68">{label}</text>'
        )
        parts.append(
            f'  <text class="sans num up {d}" x="{x_value}" y="{y}" text-anchor="end" font-size="13.5" font-weight="600" fill="{ACCENT}">{fmt(value)}</text>'
        )

    return card("\n".join(parts), label="GitHub statistics for Nikoloz")


def short_date(day: date) -> str:
    return f"{MONTHS[day.month - 1]} {day.day}"


def date_range(start: date | None, end: date | None, present: bool = False) -> str:
    if start is None or end is None:
        return "No streak yet"
    if present:
        return f"{short_date(start)} - Present"
    if start == end:
        return short_date(start)
    return f"{short_date(start)} - {short_date(end)}"


def streak_svg(summary: StreakSummary) -> str:
    first_label = f"{short_date(summary.first_date)}, {summary.first_date.year} - Present"
    current_label = date_range(summary.current_start, summary.current_end, present=summary.current > 0)
    longest_label = date_range(summary.longest_start, summary.longest_end)
    parts = [
        f'  <line class="up d1" x1="165" y1="26" x2="165" y2="169" stroke="{BORDER}"/>',
        f'  <line class="up d1" x1="330" y1="26" x2="330" y2="169" stroke="{BORDER}"/>',
        f'  <text class="sans num up d2" x="82.5" y="80" text-anchor="middle" font-size="29" font-weight="600" fill="{INK}">{fmt(summary.total)}</text>',
        f'  <text class="sans up d3" x="82.5" y="116" text-anchor="middle" font-size="13" fill="{INK}" opacity="0.62">Total contributions</text>',
        f'  <text class="sans up d4" x="82.5" y="145" text-anchor="middle" font-size="10.5" fill="{INK}" opacity="0.42">{first_label}</text>',
        f'  <circle class="up d2" cx="247.5" cy="73" r="40" fill="none" stroke="{BORDER}" stroke-width="5"/>',
        f'  <circle class="up d2" cx="247.5" cy="73" r="40" fill="none" stroke="{ACCENT}" stroke-width="5" stroke-linecap="round"/>',
        f'  <text class="sans num up d3" x="247.5" y="82" text-anchor="middle" font-size="29" font-weight="600" fill="{INK}">{fmt(summary.current)}</text>',
        f'  <text class="sans up d3" x="247.5" y="132" text-anchor="middle" font-size="13" font-weight="600" fill="{ACCENT}">Current streak</text>',
        f'  <text class="sans up d4" x="247.5" y="158" text-anchor="middle" font-size="10.5" fill="{INK}" opacity="0.42">{current_label}</text>',
        f'  <text class="sans num up d2" x="412.5" y="80" text-anchor="middle" font-size="29" font-weight="600" fill="{INK}">{fmt(summary.longest)}</text>',
        f'  <text class="sans up d3" x="412.5" y="116" text-anchor="middle" font-size="13" fill="{INK}" opacity="0.62">Longest streak</text>',
        f'  <text class="sans up d4" x="412.5" y="145" text-anchor="middle" font-size="10.5" fill="{INK}" opacity="0.42">{longest_label}</text>',
    ]
    label = (
        f"GitHub contribution streak for Nikoloz: {summary.current} days current, "
        f"{summary.longest} days longest"
    )
    return card("\n".join(parts), label=label)


def langs_svg(user: dict) -> str:
    sizes: dict[str, int] = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            sizes[name] = sizes.get(name, 0) + edge["size"]

    top = sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)[:6]
    total = sum(sizes.values()) or 1

    parts = [
        f'  <text class="sans up d1" x="24" y="40" font-size="15" font-weight="600" letter-spacing="0.5" fill="{ACCENT_BRIGHT}">Most used languages</text>',
        '  <clipPath id="bar"><rect x="24" y="58" width="447" height="10" rx="5"/></clipPath>',
        f'  <rect class="up d2" x="24" y="58" width="447" height="10" rx="5" fill="{RAISED}"/>',
    ]

    x = 24.0
    for i, (name, size) in enumerate(top):
        w = 447 * size / total
        parts.append(
            f'  <rect class="up d2" x="{x:.1f}" y="58" width="{w:.1f}" height="10" fill="{LANG_RAMP[i]}" clip-path="url(#bar)"/>'
        )
        x += w

    for i, (name, size) in enumerate(top):
        pct = 100 * size / total
        col, row = divmod(i, 3)
        cx = 30 + col * 240
        y = 102 + row * 27
        d = "d3" if col == 0 else "d4"
        parts.append(f'  <circle class="up {d}" cx="{cx}" cy="{y - 4}" r="4" fill="{LANG_RAMP[i]}"/>')
        parts.append(
            f'  <text class="sans up {d}" x="{cx + 14}" y="{y}" font-size="13" fill="{INK}" opacity="0.85">{name}</text>'
        )
        parts.append(
            f'  <text class="sans num up {d}" x="{cx + 184}" y="{y}" text-anchor="end" font-size="12.5" fill="{INK}" opacity="0.5">{pct:.1f}%</text>'
        )

    return card("\n".join(parts), label="Most used languages")


def main() -> None:
    login = os.environ["GITHUB_REPOSITORY_OWNER"]
    token = os.environ["GITHUB_TOKEN"]
    user = fetch(login, token)
    today = datetime.now(UTC).date()
    contribution_days = fetch_contribution_days(login, token, user["createdAt"], today)
    streak = calculate_streaks(contribution_days, today)

    os.makedirs("dist", exist_ok=True)
    with open("dist/stats.svg", "w", encoding="utf-8") as f:
        f.write(stats_svg(user))
    with open("dist/langs.svg", "w", encoding="utf-8") as f:
        f.write(langs_svg(user))
    with open("dist/streak.svg", "w", encoding="utf-8") as f:
        f.write(streak_svg(streak))
    print("wrote dist/stats.svg, dist/langs.svg, and dist/streak.svg")


if __name__ == "__main__":
    main()
