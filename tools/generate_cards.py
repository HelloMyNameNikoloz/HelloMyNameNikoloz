"""Generate stats.svg and langs.svg for the profile README, in the
nikoloz.de evening-garden palette. Runs in CI with GITHUB_TOKEN."""

import json
import os
import urllib.request

CHARCOAL = "#101914"
RAISED = "#1d2a20"
INK = "#f4ead7"
ACCENT = "#d7a84f"
ACCENT_BRIGHT = "#e8bc66"
BORDER = "#30362f"
LANG_RAMP = ["#e8bc66", "#d7a84f", "#9aa84f", "#8fae72", "#5c7a3f", "#33532f"]

QUERY = """
query($login: String!) {
  user(login: $login) {
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


def fetch(login: str, token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    return data["data"]["user"]


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

    os.makedirs("dist", exist_ok=True)
    with open("dist/stats.svg", "w", encoding="utf-8") as f:
        f.write(stats_svg(user))
    with open("dist/langs.svg", "w", encoding="utf-8") as f:
        f.write(langs_svg(user))
    print("wrote dist/stats.svg and dist/langs.svg")


if __name__ == "__main__":
    main()
