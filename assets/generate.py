#!/usr/bin/env python3
"""
Profile-card generator (standard library only, no third-party services).

Reads your public data straight from GitHub's own REST / GraphQL APIs and
writes five self-contained SVG files into ./assets:

    hero.svg      identity card
    city.svg      isometric contribution city
    stats.svg     "Profile Signal" tiles
    projects.svg  project list
    visit.svg     social pill(s)

Usage:
    GITHUB_TOKEN=... python generate.py            # live data
    python generate.py --offline                   # placeholder data, no network

Edit the CONFIG block below to customise.
"""
import base64
import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape

# ───────────────────────────── CONFIG ─────────────────────────────
USERNAME = os.environ.get("PROFILE_USER", "serine-na")
DISPLAY_NAME = os.environ.get("PROFILE_NAME", "Serine")
TAGLINE = os.environ.get("PROFILE_TAGLINE", "")            # empty → your GitHub bio, nothing invented
SOCIALS = [  # label, handle, (more entries become extra pills)
    ("GitHub", "@" + USERNAME),
    # ("LinkedIn", "@your-handle"),
]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "assets")
AVATAR_FILE = os.path.join(OUT_DIR, "avatar.jpg")   # your own picture, embedded as-is
PROJECT_COUNT = 4

PALETTE = {
    "text": "#e8fffa", "muted": "#7fd6c6", "teal": "#4fe3c1",
    "purple": "#8b6cf0", "blue": "#4b7bec", "cyan": "#22d3ee",
    "border": "#3fd0b4",
}
SANS = "Roboto,'Segoe UI','Helvetica Neue',Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace"
LANG_COLORS = {
    "HTML": "#e34c26", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Python": "#3572A5", "Shell": "#89e051", "Vim Script": "#199f4b",
    "Vim script": "#199f4b", "R": "#198CE7", "Go": "#00ADD8", "Rust": "#dea584",
    "C": "#555555", "C++": "#f34b7d", "Java": "#b07219", "Ruby": "#701516",
    "PHP": "#4F5D95", "CSS": "#563d7c", "Jupyter Notebook": "#DA5B0B",
}
# ──────────────────────────────────────────────────────────────────


# ───────────────────────────── DATA ───────────────────────────────
def _req(url, token=None, data=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-card-generator"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = json.dumps(data).encode() if data is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=30) as r:
        return r.read()


def _json(url, token=None, data=None):
    return json.loads(_req(url, token, data))


def local_avatar():
    if os.path.exists(AVATAR_FILE):
        with open(AVATAR_FILE, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return None


def offline_data():
    return {
        "name": DISPLAY_NAME or USERNAME, "login": USERNAME,
        "bio": TAGLINE, "avatar": local_avatar(), "stars": 0, "repos": 0, "followers": 0,
        "languages": [],
        "total": 0, "days": [[0] * 7 for _ in range(53)],
        "active": 0, "busiest": 0, "projects": [],
    }


def live_data(token):
    u = _json(f"https://api.github.com/users/{USERNAME}", token)
    repos, page = [], 1
    while True:
        chunk = _json(f"https://api.github.com/users/{USERNAME}/repos?per_page=100&page={page}&type=owner", token)
        repos += chunk
        if len(chunk) < 100:
            break
        page += 1
    own = [r for r in repos if not r["fork"]]
    stars = sum(r["stargazers_count"] for r in own)
    counts = {}
    for r in own:
        if r["language"]:
            counts[r["language"]] = counts.get(r["language"], 0) + 1
    languages = [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:4]

    # contributions (GraphQL needs a token; the Actions GITHUB_TOKEN works)
    total, days, active, busiest, pinned = 0, [[0] * 7 for _ in range(53)], 0, 0, []
    if token:
        q = """query($l:String!){user(login:$l){
          pinnedItems(first:6,types:REPOSITORY){nodes{... on Repository{name description stargazerCount
            pushedAt primaryLanguage{name}}}}
          contributionsCollection{contributionCalendar{totalContributions
            weeks{contributionDays{contributionCount}}}}}}"""
        try:
            res = json.loads(_req("https://api.github.com/graphql", token, {"query": q, "variables": {"l": USERNAME}}))
            usr = res["data"]["user"]
            cal = usr["contributionsCollection"]["contributionCalendar"]
            total = cal["totalContributions"]
            for wi, w in enumerate(cal["weeks"][:53]):
                for di, d in enumerate(w["contributionDays"][:7]):
                    days[wi][di] = d["contributionCount"]
            flat = [c for w in days for c in w]
            active, busiest = sum(1 for c in flat if c), max(flat or [0])
            pinned = usr["pinnedItems"]["nodes"]
        except Exception as e:  # keep going with REST-only data
            print("GraphQL skipped:", e, file=sys.stderr)

    if pinned:
        projects = [{"name": p["name"], "desc": p["description"] or "", "stars": p["stargazerCount"],
                     "lang": (p["primaryLanguage"] or {}).get("name"), "pushed": p["pushedAt"]} for p in pinned]
    else:
        top = sorted(own, key=lambda r: (-r["stargazers_count"], r["pushed_at"] or ""), reverse=False)[:PROJECT_COUNT]
        projects = [{"name": r["name"], "desc": r["description"] or "", "stars": r["stargazers_count"],
                     "lang": r["language"], "pushed": r["pushed_at"]} for r in top]
    projects = projects[:PROJECT_COUNT]
    for p in projects:  # ring = share of the top language by bytes
        try:
            langs = _json(f"https://api.github.com/repos/{USERNAME}/{p['name']}/languages", token)
            tot = sum(langs.values())
            p["pct"] = round(100 * max(langs.values()) / tot) if tot else 0
        except Exception:
            p["pct"] = 0

    avatar = local_avatar()          # your own picture wins; GitHub's avatar is only a fallback
    if not avatar:
        try:
            raw = _req(u["avatar_url"] + ("&" if "?" in u["avatar_url"] else "?") + "s=160")
            avatar = "data:image/jpeg;base64," + base64.b64encode(raw).decode()
        except Exception:
            pass
    return {
        "name": DISPLAY_NAME or u.get("name") or u["login"], "login": u["login"],
        "bio": TAGLINE or u.get("bio") or "", "avatar": avatar, "stars": stars,
        "repos": u["public_repos"], "followers": u["followers"], "languages": languages,
        "total": total, "days": days, "active": active, "busiest": busiest, "projects": projects,
    }


# ───────────────────────────── HELPERS ────────────────────────────
def esc(s):
    return escape(str(s), {'"': "&quot;"})


def ago(iso):
    if not iso:
        return "recently"
    d = datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))
    s = d.total_seconds()
    for unit, size in (("y", 31536000), ("mo", 2592000), ("d", 86400), ("h", 3600)):
        if s >= size:
            return f"{int(s // size)}{unit} ago"
    return "just now"


def clip(text, n):
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def wrap2(text, n):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) <= n:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > 2:
        lines = [lines[0], clip(" ".join(lines[1:]), n)]
    return lines


def lang_color(name):
    return LANG_COLORS.get(name, "#4fe3c1")


def svg_open(w, h, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{esc(title)}">\n<title>{esc(title)}</title>\n')


def card_shell(w, h, inner_inset=24, dot=True):
    """Glassy rounded card: layered gradients, border, inner panel, pulsing dot."""
    p = PALETTE
    s = f"""<defs>
  <linearGradient id="base" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#0c3b37"/><stop offset=".5" stop-color="#082a2a"/><stop offset="1" stop-color="#061f22"/>
  </linearGradient>
  <radialGradient id="glowT" cx=".16" cy=".02" r=".62">
    <stop offset="0" stop-color="#2fd0b0" stop-opacity=".55"/><stop offset="1" stop-color="#2fd0b0" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="glowB" cx=".96" cy=".98" r=".5">
    <stop offset="0" stop-color="#3b7be0" stop-opacity=".6"/><stop offset="1" stop-color="#3b7be0" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="glowR" cx=".98" cy=".5" r=".35">
    <stop offset="0" stop-color="#1fa98f" stop-opacity=".25"/><stop offset="1" stop-color="#1fa98f" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="panel" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#021a1c" stop-opacity=".55"/><stop offset="1" stop-color="#02161a" stop-opacity=".7"/>
  </linearGradient>
  <clipPath id="clipCard"><rect width="{w}" height="{h}" rx="28"/></clipPath>
</defs>
<g clip-path="url(#clipCard)">
  <rect width="{w}" height="{h}" fill="url(#base)"/>
  <rect width="{w}" height="{h}" fill="url(#glowT)"/>
  <rect width="{w}" height="{h}" fill="url(#glowR)"/>
  <rect width="{w}" height="{h}" fill="url(#glowB)"/>
</g>
<rect x=".75" y=".75" width="{w-1.5}" height="{h-1.5}" rx="27.5" fill="none" stroke="{p['border']}" stroke-opacity=".38" stroke-width="1.5"/>
"""
    if inner_inset:
        i = inner_inset
        s += (f'<rect x="{i}" y="{i}" width="{w-2*i}" height="{h-2*i}" rx="22" fill="url(#panel)" '
              f'stroke="{p["border"]}" stroke-opacity=".45" stroke-width="1"/>\n')
    if dot:
        s += (f'<circle cx="{w-i-26 if inner_inset else w-30}" cy="{i+26 if inner_inset else 30}" r="3.5" fill="#2fbf9f">'
              f'<animate attributeName="opacity" values=".35;1;.35" dur="4s" repeatCount="indefinite"/></circle>\n')
    return s


def pct_bar(x, y, w, frac, color, track="#ffffff"):
    frac = max(0.08, min(1.0, frac))
    return (f'<rect x="{x}" y="{y}" width="{w}" height="7" rx="3.5" fill="{track}" fill-opacity=".1"/>'
            f'<rect x="{x}" y="{y}" width="{w*frac:.1f}" height="7" rx="3.5" fill="{color}"/>\n')


# ───────────────────────────── CARDS ──────────────────────────────
def hero(d):
    W, H, p = 900, 252, PALETTE
    s = svg_open(W, H, f"{d['name']} profile")
    s += card_shell(W, H, 28)
    # avatar
    cx, cy, r = 100, 98, 50
    s += f'<defs><clipPath id="av"><circle cx="{cx}" cy="{cy}" r="{r-5}"/></clipPath></defs>\n'
    s += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#04201f" stroke="{p["teal"]}" stroke-width="2.5"/>\n'
    if d["avatar"]:
        s += (f'<image href="{d["avatar"]}" x="{cx-r+5}" y="{cy-r+5}" width="{2*(r-5)}" height="{2*(r-5)}" '
              f'preserveAspectRatio="xMidYMid slice" clip-path="url(#av)"/>\n')
    else:
        s += (f'<g clip-path="url(#av)" fill="#0f5a52"><circle cx="{cx}" cy="{cy-8}" r="15"/>'
              f'<ellipse cx="{cx}" cy="{cy+42}" rx="30" ry="26"/></g>\n')
    # swoosh + handle
    s += f'<path d="M262 62 C 330 46, 420 50, 498 76" fill="none" stroke="{p["teal"]}" stroke-opacity=".55" stroke-width="1.6"/>\n'
    s += (f'<text x="176" y="69" font-family="{SANS}" font-size="11.5" font-weight="700" letter-spacing="2.2" '
          f'fill="{p["teal"]}">@{esc(d["login"])}</text>\n')
    s += (f'<text x="175" y="127" font-family="{SANS}" font-size="39" font-weight="800" letter-spacing="-.6" '
          f'fill="{p["text"]}">{esc(clip(d["name"], 24))}</text>\n')
    s += f'<text x="177" y="150" font-family="{SANS}" font-size="13.5" fill="{p["muted"]}">{esc(clip(d["bio"], 60))}</text>\n'
    # language chips
    x = 48
    for lang in d["languages"][:4]:
        wch = 20 + len(lang) * 7.4
        s += (f'<rect x="{x:.0f}" y="173" width="{wch:.0f}" height="30" rx="15" fill="#06302f" fill-opacity=".8" '
              f'stroke="{p["teal"]}" stroke-opacity=".5"/>'
              f'<text x="{x+wch/2:.0f}" y="192" text-anchor="middle" font-family="{SANS}" font-size="11.5" '
              f'font-weight="700" fill="{p["text"]}">{esc(lang)}</text>\n')
        x += wch + 12
    # total stars
    s += (f'<text x="769" y="119" text-anchor="middle" font-family="{SANS}" font-size="32" font-weight="800" '
          f'fill="{p["teal"]}">{d["stars"]}</text>\n'
          f'<text x="769" y="137" text-anchor="middle" font-family="{SANS}" font-size="10" font-weight="700" '
          f'letter-spacing="2" fill="{p["muted"]}">TOTAL STARS</text>\n')
    return s + "</svg>\n"


def city(d):
    W, H, p = 900, 442, PALETTE
    s = svg_open(W, H, "Contribution city")
    s += card_shell(W, H, 0, dot=False)
    s += f'<rect x="1.5" y="1.5" width="{W-3}" height="{H-3}" rx="26" fill="none"/>\n'
    s += (f'<text x="36" y="66" font-family="{MONO}" font-size="12.5" letter-spacing="2.4" fill="{p["teal"]}">CONTRIBUTION CITY</text>\n'
          f'<text x="35" y="100" font-family="{SANS}" font-size="30" font-weight="800" fill="{p["text"]}">{d["total"]}</text>\n'
          f'<text x="36" y="124" font-family="{SANS}" font-size="13.5" font-weight="700" fill="#bff5e8">contributions in the last year</text>\n'
          f'<text x="36" y="158" font-family="{SANS}" font-size="12" font-weight="700" fill="#bff5e8">{d["active"]} active days</text>\n'
          f'<text x="36" y="178" font-family="{SANS}" font-size="12" font-weight="700" fill="#bff5e8">Busiest day: {d["busiest"]}</text>\n'
          f'<text x="36" y="394" font-family="{MONO}" font-size="12" fill="{p["teal"]}" fill-opacity=".85">@{esc(d["login"])}</text>\n'
          f'<text x="36" y="412" font-family="{SANS}" font-size="10.5" fill="{p["muted"]}" fill-opacity=".7">Isometric contribution view, drawn from GitHub data</text>\n')

    s += f'<text x="36" y="214" font-family="{SANS}" font-size="10.5" fill="{p["muted"]}">Less</text>'
    for n, col in enumerate(("#19716a", "#27a592", "#34c9ae", "#58e6c4", "#9bf5dc")):
        s += f'<rect x="{66+n*16}" y="205" width="12" height="12" rx="3" fill="{col}"/>'
    s += f'<text x="152" y="214" font-family="{SANS}" font-size="10.5" fill="{p["muted"]}">More</text>\n'

    a, b = 10.5, 5.5              # iso half-width / half-height of one cell
    ox, oy = 322, 96              # projection origin
    mx = max(d["busiest"], 1)
    levels = [  # top, left face, right face
        ("#19716a", "#104e48", "#0c403b"),
        ("#27a592", "#187064", "#115a50"),
        ("#34c9ae", "#1d8a79", "#157066"),
        ("#58e6c4", "#27a58f", "#1b8574"),
        ("#9bf5dc", "#3cc3a8", "#27a08a"),
    ]
    cells = []
    for i in range(53):
        for j in range(7):
            c = d["days"][i][j]
            lv = 0 if c == 0 else min(4, 1 + int(3 * (c - 1) / max(mx - 1, 1)) if mx > 1 else 1)
            h = 2.5 if c == 0 else 6 + 62 * (c / mx) ** 0.8
            cells.append((i + j, i, j, h, lv))
    cells.sort()
    g = 0.5                       # gap between cells
    s += '<g stroke-linejoin="round" stroke-width=".6">\n'
    for _, i, j, h, lv in cells:
        px, py = ox + (i - j) * a, oy + (i + j) * b
        t, l, r = levels[lv]
        A = (px, py - h); B = (px + a - g, py + b - h)
        C = (px, py + 2 * b - g - h); D = (px - a + g, py + b - h)
        Cb = (C[0], C[1] + h); Db = (D[0], D[1] + h); Bb = (B[0], B[1] + h)
        f = lambda *pts: " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        s += f'<polygon points="{f(D, C, Cb, Db)}" fill="{l}" stroke="#062b2a"/>'
        s += f'<polygon points="{f(C, B, Bb, Cb)}" fill="{r}" stroke="#062b2a"/>'
        s += f'<polygon points="{f(A, B, C, D)}" fill="{t}" stroke="#062b2a"/>\n'
    s += "</g>\n"
    return s + "</svg>\n"


def stats(d):
    W, H, p = 900, 273, PALETTE
    s = svg_open(W, H, "Profile signal")
    s += card_shell(W, H, 26)
    s += (f'<text x="46" y="68" font-family="{SANS}" font-size="25" font-weight="800" fill="#bff5e8">Profile Signal</text>\n'
          f'<text x="47" y="88" font-family="{SANS}" font-size="12.5" font-weight="700" fill="{p["teal"]}">Live GitHub stats, drawn from your public profile</text>\n')
    tiles = [("Stars", d["stars"], p["teal"], 25), ("Contributions", d["total"], p["purple"], 1000),
             ("Repos", d["repos"], p["blue"], 28), ("Followers", d["followers"], p["cyan"], 27)]
    tw, gap, x0, y0, th = 196, 16, 34, 106, 128
    for k, (label, val, col, tgt) in enumerate(tiles):
        x = x0 + k * (tw + gap)
        s += (f'<rect x="{x}" y="{y0}" width="{tw}" height="{th}" rx="20" fill="#01100f" fill-opacity=".72" '
              f'stroke="{p["border"]}" stroke-opacity=".5"/>\n'
              f'<text x="{x+20}" y="{y0+33}" font-family="{SANS}" font-size="12" font-weight="700" letter-spacing=".6" fill="#bff5e8">{label}</text>\n'
              f'<text x="{x+19}" y="{y0+78}" font-family="{SANS}" font-size="35" font-weight="800" fill="{col}">{val}</text>\n')
        s += pct_bar(x + 20, y0 + 97, tw - 40, val / tgt, col)
    return s + "</svg>\n"


def ring(cx, cy, r, pct, color):
    circ = 2 * math.pi * r
    on = circ * pct / 100
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#2a6a9a" stroke-opacity=".55" stroke-width="7"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="7" '
            f'stroke-dasharray="{on:.1f} {circ-on:.1f}" transform="rotate(-90 {cx} {cy})"/>'
            f'<text x="{cx}" y="{cy+4}" text-anchor="middle" font-family="{SANS}" font-size="11.5" font-weight="800" fill="#fff">{pct}%</text>\n')


def projects(d):
    W, H, p = 900, 498, PALETTE
    s = svg_open(W, H, "Projects list")
    s += card_shell(W, H, 0, dot=False)
    s += (f'<text x="36" y="56" font-family="{MONO}" font-size="12" letter-spacing="2.4" fill="{p["teal"]}">PROJECTS.LIST</text>\n'
          f'<text x="190" y="56" font-family="{MONO}" font-size="12" fill="{p["muted"]}">./projects.sh --all</text>\n'
          f'<text x="864" y="56" text-anchor="end" font-family="{MONO}" font-size="12" fill="{p["muted"]}">{len(d["projects"])} project{"" if len(d["projects"]) == 1 else "s"}</text>\n'
          f'<line x1="36" y1="72" x2="864" y2="72" stroke="{p["border"]}" stroke-opacity=".45"/>\n')
    pw, ph, gx, gy, x0, y0 = 407, 184, 14, 14, 36, 98
    if not d["projects"]:
        s += (f'<rect x="36" y="98" width="828" height="{ph*2+gy}" rx="14" fill="#02181a" fill-opacity=".78" '
              f'stroke="{p["border"]}" stroke-opacity=".5"/>\n'
              f'<text x="450" y="{98+ph+gy/2-4}" text-anchor="middle" font-family="{MONO}" font-size="15" fill="{p["text"]}">No pinned repositories yet<tspan fill="{p["teal"]}"> _</tspan></text>\n'
              f'<text x="450" y="{98+ph+gy/2+20}" text-anchor="middle" font-family="{MONO}" font-size="12" fill="{p["muted"]}">Pin repositories on your profile and they will appear here.</text>\n')
        return s + "</svg>\n"
    for k in range(min(4, len(d["projects"]))):
        x, y = x0 + (k % 2) * (pw + gx), y0 + (k // 2) * (ph + gy)
        pr = d["projects"][k]
        s += (f'<rect x="{x}" y="{y}" width="{pw}" height="{ph}" rx="14" fill="#02181a" fill-opacity=".78" '
              f'stroke="{p["border"]}" stroke-opacity=".5"/>\n'
              f'<line x1="{x}" y1="{y+34}" x2="{x+pw}" y2="{y+34}" stroke="{p["border"]}" stroke-opacity=".4"/>\n')
        name = pr["name"] if pr else "your-repository"
        s += (f'<text x="{x+16}" y="{y+22}" font-family="{MONO}" font-size="11.5" fill="{p["muted"]}">• {esc(clip(name, 34))}</text>\n'
              f'<circle cx="{x+pw-16}" cy="{y+17}" r="3.5" fill="#4aa898"/>\n'
              f'<text x="{x+18}" y="{y+68}" font-family="{MONO}" font-size="19" font-weight="700" fill="{p["text"]}">{esc(clip(name, 22))} '
              f'<tspan fill="{p["teal"]}">_</tspan></text>\n')
        desc = wrap2(pr["desc"] if pr and pr["desc"] else "Add a description to this repository.", 38)
        for n, line in enumerate(desc):
            s += f'<text x="{x+18}" y="{y+93+n*18}" font-family="{MONO}" font-size="12" fill="#a9ddd2">{esc(line)}</text>\n'
        lang = pr["lang"] if pr and pr["lang"] else "Code"
        cw = 22 + len(lang) * 7
        s += (f'<rect x="{x+16}" y="{y+128}" width="{cw}" height="20" rx="10" fill="#0a3b36" stroke="{p["teal"]}" stroke-opacity=".5"/>'
              f'<text x="{x+16+cw/2:.0f}" y="{y+142}" text-anchor="middle" font-family="{MONO}" font-size="10.5" fill="{p["teal"]}">{esc(lang)}</text>\n')
        stars = pr["stars"] if pr else 0
        s += (f'<text x="{x+18}" y="{y+171}" font-family="{SANS}" font-size="12" fill="#f2cc60">★</text>'
              f'<text x="{x+34}" y="{y+171}" font-family="{MONO}" font-size="11.5" fill="#bfe9df">{stars}</text>'
              f'<text x="{x+66}" y="{y+171}" font-family="{MONO}" font-size="11.5" fill="{p["muted"]}">updated {ago(pr["pushed"]) if pr else "—"}</text>\n')
        s += ring(x + pw - 52, y + 98, 22, pr["pct"] if pr else 0, lang_color(lang))
    return s + "</svg>\n"


def visit(d):
    W, H, p = 900, 133, PALETTE
    s = svg_open(W, H, "Visit")
    s += card_shell(W, H, 24)
    gap = 18
    widths = [max(170, 76 + min(len(h), 28) * 8.6) for _, h in SOCIALS]
    x = (W - (sum(widths) + gap * (len(widths) - 1))) / 2
    s += ('<defs><linearGradient id="pill" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6ff0d2"/>'
          '<stop offset=".5" stop-color="#ffffff" stop-opacity=".85"/><stop offset="1" stop-color="#4fe3c1"/></linearGradient></defs>\n')
    for (label, handle), pw in zip(SOCIALS, widths):
        s += (f'<rect x="{x:.0f}" y="40" width="{pw:.0f}" height="54" rx="27" fill="#04201f" fill-opacity=".9" stroke="url(#pill)" stroke-width="1.8"/>'
              f'<circle cx="{x+30:.0f}" cy="67" r="12" fill="#1c3a3d"/>'
              f'<text x="{x+30:.0f}" y="71.5" text-anchor="middle" font-family="{SANS}" font-size="12.5" font-weight="800" fill="#fff">{esc(label[0])}</text>'
              f'<text x="{x+52:.0f}" y="61" font-family="{SANS}" font-size="10" font-weight="800" fill="{p["teal"]}">{esc(label)}</text>'
              f'<text x="{x+52:.0f}" y="79" font-family="{SANS}" font-size="14" font-weight="800" fill="#fff">{esc(clip(handle, 28))}</text>\n')
        x += pw + gap
    return s + "</svg>\n"


# ───────────────────────────── MAIN ───────────────────────────────
def main():
    offline = "--offline" in sys.argv
    data = offline_data() if offline else live_data(os.environ.get("GITHUB_TOKEN"))
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, fn in (("hero", hero), ("city", city), ("stats", stats), ("projects", projects), ("visit", visit)):
        with open(os.path.join(OUT_DIR, name + ".svg"), "w", encoding="utf-8") as f:
            f.write(fn(data))
        print("wrote", name + ".svg")


if __name__ == "__main__":
    main()
