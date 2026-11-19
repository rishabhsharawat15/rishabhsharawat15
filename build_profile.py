"""
Builds an animated, neofetch-style profile card (dark_mode.svg + light_mode.svg):
a coloured ASCII portrait of your photo on the left, terminal-style info on the right.

Usage:
    python build_profile.py                     # uses me.png / me.jpg
    GITHUB_TOKEN=xxx python build_profile.py    # also refreshes live GitHub stats
    CONTACT_EMAIL=you@mail.com python build_profile.py   # shows your email
    STATIC=1 python build_profile.py            # no animation (for previews)

Photo tips: a PNG with a transparent background looks best. If your photo has a
background and `rembg` is installed (pip install rembg), it is removed automatically.

Requires: pip install pillow
"""
import json
import os
import urllib.request
from datetime import date, datetime
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
USERNAME = "rishabhsharawat15"
STATIC = bool(os.environ.get("STATIC"))

# ─────────────────────────── EDIT YOUR INFO HERE ───────────────────────────
CONFIG = {
    "header": "rishabh@sharawat",
    # Set your birthday as (YYYY, M, D) to show your age as "Uptime".
    # Leave None to show how long you've been on GitHub instead.
    "birthday": None,
    "sections": [
        [
            ("OS", "Windows, Linux"),
            ("Host", "Software Developer"),
            ("Kernel", "Full-Stack (Back-end + Front-end)"),
            ("IDE", "VS Code"),
        ],
        [
            ("Languages.Programming", "C, C++, Python, JavaScript"),
            ("Languages.Web", "TypeScript, PHP, HTML, Solidity"),
            ("Frameworks", "React, Next.js, Node, Django"),
            ("Databases", "MySQL, MongoDB"),
            ("Cloud", "AWS, GCP, Vercel, Netlify"),
        ],
        [
            ("Hobbies.Software", "Problem Solving, Web3"),
            ("Hobbies.Design", "Figma, Canva, Sketch"),
        ],
    ],
    "contact": [
        ("Email", os.environ.get("CONTACT_EMAIL")),   # line is hidden when unset
        ("Portfolio", "rishabhsharawat.netlify.app"),
        ("LinkedIn", "rishabh-sharawat-981b501b7"),
        ("Twitter", "@rishabhsh15"),
        ("Instagram", "rishabh_sharawat_"),
    ],
}

# Commands advertised on the card. Keep in sync with COMMANDS in index.html,
# which is the live terminal that actually runs them.
HELP = [
    ("whoami", "who I am, in one line"),
    ("sudo expert", "skills I'm expert in"),
    ("sudo experience", "where I've worked"),
    ("sudo projects", "things I've built"),
    ("sudo education", "where I studied"),
    ("sudo achievements", "certs & milestones"),
    ("sudo stats", "live GitHub stats"),
    ("sudo connect", "all my links"),
    ("sudo resume", "download my CV"),
    ("sudo hire", "why work with me"),
    ("neofetch", "show this card again"),
    ("clear", "wipe the screen"),
]
TERMINAL_URL = f"{USERNAME}.github.io/{USERNAME}"
# ────────────────────────────────────────────────────────────────────────────

# ASCII portrait geometry (small font = more detail)
A_COLS, A_ROWS = 100, 80
A_FONT, A_LH, A_CW = 7, 6.9, 4.0          # font px, line height, char width
A_X, A_Y = 22, 34
A_W = A_COLS * A_CW

# Info column
INFO_WIDTH = 58                            # characters per line
I_FONT, I_LH, I_CW = 15, 20, 8.6
I_X = A_X + A_W + 30
I_Y = 34

CHARSET = " .'`^,:;!i~+=?7tjxcvzunoyeaskZ5S0O8B#%@$"

THEMES = {
    "dark": dict(bg="#0d1117", border="#30363d", text="#c9d1d9", key="#ffa657",
                 value="#a5d6ff", dots="#616e7f", prompt="#3fb950", scan="#58a6ff"),
    "light": dict(bg="#f6f8fa", border="#d0d7de", text="#24292f", key="#953800",
                  value="#0a3069", dots="#c2cfde", prompt="#1a7f37", scan="#0969da"),
}


# ── Photo → coloured ASCII ───────────────────────────────────────────────────
def load_photo():
    from PIL import Image, ImageOps
    for name in ("me.png", "me.jpg", "me.jpeg", "me.webp"):
        p = HERE / name
        if p.exists():
            img = ImageOps.exif_transpose(Image.open(p)).convert("RGBA")
            if img.getextrema()[3][0] == 255:  # no transparency -> try to cut out
                try:
                    from rembg import remove
                    img = remove(img)
                except Exception:
                    pass
            return img
    raise SystemExit("Add your photo as me.png or me.jpg next to this script.")


def ascii_cells():
    """Returns rows of (char, (r,g,b)) cells."""
    from PIL import Image, ImageFilter, ImageOps
    img = load_photo()
    target = A_W / (A_ROWS * A_LH)
    w, h = img.size
    if w / h > target:
        nw = int(h * target)
        img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        img = img.crop((0, 0, w, int(w / target)))
    img = img.resize((A_COLS, A_ROWS), Image.LANCZOS)
    alpha = img.getchannel("A")
    rgb = img.convert("RGB")
    gray = ImageOps.equalize(rgb.convert("L"), mask=alpha.point(lambda a: 255 if a > 128 else 0))
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.5, percent=220, threshold=1))
    G, C, A = gray.load(), rgb.load(), alpha.load()
    n = len(CHARSET)
    rows = []
    for y in range(A_ROWS):
        row = []
        for x in range(A_COLS):
            if A[x, y] < 110:
                row.append((" ", None))
                continue
            idx = 1 + int(G[x, y] / 256 * (n - 1))
            row.append((CHARSET[min(idx, n - 1)], C[x, y]))
        rows.append(row)
    return rows


def tint(rgb, theme):
    """Black and white: map the pixel's brightness to a grey that reads on the theme background."""
    r, g, b = rgb
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    v = 0.32 + lum * 0.68 if theme == "dark" else 0.06 + lum * 0.56
    q = min(int(round(v * 255 / 17)) * 17, 255)  # quantise -> fewer spans
    return "#%02x%02x%02x" % (q, q, q)


# ── GitHub stats ─────────────────────────────────────────────────────────────
CACHE = HERE / "stats_cache.json"


def gh(url, token):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USERNAME}
    if token:  # optional: public stats also work unauthenticated (lower rate limit)
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_stats():
    cached = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    token = os.environ.get("GITHUB_TOKEN")
    try:
        api = "https://api.github.com"
        user = gh(f"{api}/users/{USERNAME}", token)
        repos, page = [], 1
        while True:
            batch = gh(f"{api}/users/{USERNAME}/repos?per_page=100&page={page}", token)
            repos += batch
            if len(batch) < 100:
                break
            page += 1
        commits = gh(f"{api}/search/commits?q=author:{USERNAME}&per_page=1", token)
        stats = {
            "created": user["created_at"][:10],
            "repos": user["public_repos"],
            "followers": user["followers"],
            "stars": sum(r["stargazers_count"] for r in repos if not r["fork"]),
            "commits": commits.get("total_count", 0),
        }
        CACHE.write_text(json.dumps(stats, indent=2))
        return stats
    except Exception as e:  # keep the last good numbers if the API hiccups
        print("Stats fetch failed, using cache:", e)
        return cached


def uptime(stats):
    if CONFIG["birthday"]:
        start, suffix = date(*CONFIG["birthday"]), ""
    elif stats.get("created"):
        start, suffix = datetime.strptime(stats["created"], "%Y-%m-%d").date(), " (GitHub)"
    else:
        return "booting..."
    t = date.today()
    y, m, d = t.year - start.year, t.month - start.month, t.day - start.day
    if d < 0:
        m, d = m - 1, d + 30
    if m < 0:
        y, m = y - 1, m + 12
    return f"{y} years, {m} months, {d} days{suffix}"


# ── Info column ──────────────────────────────────────────────────────────────
def kv(key, value, width):
    value = str(value)
    dots = max(width - len(key) - len(value) - 5, 1)
    return [("dots", ". "), ("key", key), ("text", ":"),
            ("dots", " " + "." * dots + " "), ("value", value)]


def title(text):
    return [("text", f"- {text} " + "—" * (INFO_WIDTH - len(text) - 6) + "-—-")]


def build_info(stats):
    h = CONFIG["header"]
    lines = [[("text", h + " " + "—" * (INFO_WIDTH - len(h) - 4) + "-—-")]]
    for i, section in enumerate(CONFIG["sections"]):
        if i:
            lines.append([("dots", ". ")])
        else:
            lines.append(kv("Uptime", uptime(stats), INFO_WIDTH))
        lines += [kv(k, v, INFO_WIDTH) for k, v in section]
    lines += [[], title("Contact")]
    lines += [kv(k, v, INFO_WIDTH) for k, v in CONFIG["contact"] if v]
    lines += [[], title("GitHub Stats")]
    g = lambda k: stats.get(k, "—")
    half = (INFO_WIDTH - 3) // 2
    lines.append(kv("Repos", g("repos"), half) + [("text", " | ")] + kv("Stars", g("stars"), half)[1:])
    lines.append(kv("Commits", g("commits"), half) + [("text", " | ")] + kv("Followers", g("followers"), half)[1:])
    return lines


# ── SVG ──────────────────────────────────────────────────────────────────────
def anim(xml):
    return "" if STATIC else xml


def render(theme, cells, info):
    t = THEMES[theme]
    ascii_h = A_ROWS * A_LH
    width = int(I_X + INFO_WIDTH * I_CW + 25)
    full_chars = int((width - 2 * A_X) / I_CW)
    col_chars = (full_chars - 4) // 2
    col2_x = A_X + (col_chars + 4) * I_CW

    # ── bottom "terminal" section: `help` typed at the prompt, then the command list
    prompt = [("prompt", CONFIG["header"]), ("text", ":"), ("value", "~"), ("text", "$ ")]
    pw = sum(len(s) for _, s in prompt)

    def cmd(c, d):
        return [("prompt", "$ "), ("key", c.ljust(19)), ("dots", "# "), ("text", d)]

    rows = [[(A_X, prompt + [("text", "help")])],
            [(A_X, [("dots", "# "), ("value", "Interact with me!"),
                    ("text", " Click the card to open my live terminal and type:")])],
            []]
    half = (len(HELP) + 1) // 2
    for i in range(half):
        row = [(A_X, cmd(*HELP[i]))]
        if i + half < len(HELP):
            row.append((col2_x, cmd(*HELP[i + half])))
        rows.append(row)
    rows += [[], [(A_X, prompt)]]

    top_end = max(A_Y + ascii_h, I_Y + len(info) * I_LH)
    sep_y = top_end + 6
    B_Y = sep_y + 32
    height = int(B_Y + (len(rows) - 1) * I_LH + 24)

    info_t = lambda i: 1.6 + i * 0.11
    bot_t0 = info_t(len(info)) + 0.5
    bot_t = lambda i: bot_t0 + (0 if i == 0 else 0.9 + i * 0.12)

    font = "ConsolasFallback,Consolas,'Courier New',monospace"
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" font-family="{font}" '
         f'width="{width}px" height="{height}px" viewBox="0 0 {width} {height}">',
         "<style>",
         f".key{{fill:{t['key']}}} .value{{fill:{t['value']}}} .dots{{fill:{t['dots']}}} "
         f".text{{fill:{t['text']}}} .prompt{{fill:{t['prompt']}}}",
         "text,tspan{white-space:pre}",
         "</style>",
         "<defs>",
         f'<linearGradient id="scan" x1="0" y1="0" x2="0" y2="1">'
         f'<stop offset="0" stop-color="{t["scan"]}" stop-opacity="0"/>'
         f'<stop offset=".5" stop-color="{t["scan"]}" stop-opacity=".22"/>'
         f'<stop offset="1" stop-color="{t["scan"]}" stop-opacity="0"/></linearGradient>']

    def clip(cid, x, y, w0, w1, begin, dur):
        o.append(f'<clipPath id="{cid}"><rect x="{x - 5}" y="{y - I_FONT}" height="{I_LH + 4}" width="{w0}">'
                 f'<animate attributeName="width" from="{w0}" to="{w1}" '
                 f'begin="{begin:.2f}s" dur="{dur}s" fill="freeze"/></rect></clipPath>')

    if not STATIC:
        for i in range(len(info)):
            clip(f"c{i}", I_X, I_Y + i * I_LH, 0, INFO_WIDTH * I_CW + 20, info_t(i), 0.35)
        for i in range(len(rows)):
            y = B_Y + i * I_LH
            if i == 0:   # prompt pops in, then "help" is typed letter by letter
                clip("b0", A_X, y, 0, (pw + 4) * I_CW + 10, bot_t(0), 0.9)
            else:
                clip(f"b{i}", A_X, y, 0, width, bot_t(i), 0.35)
    o.append("</defs>")
    o.append(f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="15" fill="{t["bg"]}" stroke="{t["border"]}"/>')

    # ASCII portrait, revealed row by row
    o.append(f'<g font-size="{A_FONT}px">')
    for y, row in enumerate(cells):
        runs, cur, buf = [], None, ""
        for ch, rgb in row:
            col = tint(rgb, theme) if rgb else None
            if ch == " ":
                col = cur  # spaces join whatever run they're in
            if col != cur and buf:
                runs.append((cur, buf))
                buf = ""
            cur = col
            buf += ch
        if buf:
            runs.append((cur, buf))
        if not any(c for c, _ in runs):
            continue
        spans = "".join(f'<tspan fill="{c}">{escape(s)}</tspan>' if c else escape(s) for c, s in runs)
        yy = A_Y + y * A_LH
        a = anim(f'<animate attributeName="opacity" from="0" to="1" begin="{y * 0.016:.3f}s" dur="0.25s" fill="freeze"/>')
        op = "" if STATIC else ' opacity="0"'
        o.append(f'<text x="{A_X}" y="{yy:.1f}" textLength="{A_W:.0f}" lengthAdjust="spacing"{op}>{spans}{a}</text>')
    o.append("</g>")

    # looping scan line over the portrait
    if not STATIC:
        o.append(f'<rect x="{A_X - 6}" y="0" width="{A_W + 12}" height="60" fill="url(#scan)" opacity="0">'
                 f'<animate attributeName="y" values="{A_Y - 60};{A_Y + ascii_h}" begin="1.6s" dur="3.5s" repeatCount="indefinite"/>'
                 f'<animate attributeName="opacity" from="0" to="1" begin="1.6s" dur="0.1s" fill="freeze"/></rect>')

    def line(x, y, parts, clip_id):
        chars = sum(len(s) for _, s in parts)
        segs = "".join(f'<tspan class="{c}">{escape(s)}</tspan>' for c, s in parts)
        tl = f' textLength="{chars * I_CW:.0f}" lengthAdjust="spacing"' if chars > 4 else ""
        cp = "" if STATIC else f' clip-path="url(#{clip_id})"'
        o.append(f'<text x="{x:.0f}" y="{y}"{tl}{cp}>{segs}</text>')
        return chars

    # info lines, typed out one after another
    o.append(f'<g font-size="{I_FONT}px">')
    for i, parts in enumerate(info):
        if parts:
            line(I_X, I_Y + i * I_LH, parts, f"c{i}")

    # separator + terminal section
    o.append(f'<line x1="{A_X}" y1="{sep_y}" x2="{width - A_X}" y2="{sep_y}" stroke="{t["border"]}" stroke-dasharray="4 4"/>')
    for i, row in enumerate(rows):
        y = B_Y + i * I_LH
        for x, parts in row:
            chars = line(x, y, parts, f"b{i}")
        if i == len(rows) - 1:   # blinking cursor after the final prompt
            cx = A_X + chars * I_CW
            blink = anim(f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" '
                         f'dur="1s" begin="{bot_t(i) + 0.3:.2f}s" repeatCount="indefinite"/>')
            hidden = ' opacity="0"'
            o.append(f'<rect x="{cx:.0f}" y="{y - I_FONT + 3}" width="{I_CW:.0f}" height="{I_FONT}" '
                     f'fill="{t["text"]}"{"" if STATIC else hidden}>{blink}</rect>')
    o.append("</g>\n</svg>")
    return "\n".join(o)


def main():
    cells = ascii_cells()
    info = build_info(fetch_stats())
    for theme in THEMES:
        (HERE / f"{theme}_mode.svg").write_text(render(theme, cells, info), encoding="utf-8")
    print("Wrote dark_mode.svg and light_mode.svg")


if __name__ == "__main__":
    main()
