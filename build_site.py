"""
Build a minimal static blog from Markdown journal entries.
Reads entries/ and outputs a complete site to docs/.
"""

import json
import re
import shutil
import time
from pathlib import Path

import markdown
import requests

ENTRIES_DIR = Path(__file__).parent / "entries"
IMAGES_DIR = Path(__file__).parent / "images"
DOCS_DIR = Path(__file__).parent / "docs"

# The planned route as coordinate pairs (for the route line on the map)
ROUTE_COORDS = [
    [-6.2088, 106.8456],   # Jakarta
    [-2.7833, 111.9000],   # Tanjung Puting, Borneo
    [-5.1477, 119.4327],   # Makassar, Sulawesi
    [-2.9667, 119.9000],   # Tana Toraja, Sulawesi
    [-5.1477, 119.4327],   # Makassar (back)
    [-8.4967, 119.8889],   # Labuan Bajo, Flores
    [-8.7914, 120.9722],   # Bajawa
    [-8.8488, 121.6608],   # Ende
    [-6.2088, 106.8456],   # Jakarta (return)
]

GEOCACHE_PATH = Path(__file__).parent / ".geocache.json"


_geocache = None


def _load_geocache():
    global _geocache
    if _geocache is None:
        _geocache = json.loads(GEOCACHE_PATH.read_text()) if GEOCACHE_PATH.exists() else {}
    return _geocache


def _save_geocache():
    if _geocache is not None:
        GEOCACHE_PATH.write_text(json.dumps(_geocache, indent=2, ensure_ascii=False))


def geocode(place_name):
    """Look up coordinates via OpenStreetMap Nominatim, with disk cache."""
    cache = _load_geocache()
    key = place_name.lower().strip()

    if key in cache:
        return cache[key]

    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": f"{place_name}, Indonesia", "format": "json", "limit": 1},
        headers={"User-Agent": "Ferdadagbok-TravelJournal/1.0"},
        timeout=10,
    )

    results = resp.json()
    if results:
        loc = {
            "lat": float(results[0]["lat"]),
            "lng": float(results[0]["lon"]),
            "name": place_name,
        }
        cache[key] = loc
    else:
        cache[key] = None

    time.sleep(1)  # Nominatim rate limit
    return cache[key]


def extract_place_name(title):
    """Try to pull a place name from an entry title.

    Titles look like "May 7 — First Day in Jakarta" or
    "May 5 — Fyrsta kvöldið í Jakarta". We grab the last
    significant word(s) after common prepositions.
    """
    # Strip the date prefix: "May 7 — " or "May 3rd — "
    match = re.search(r"—\s*(.+)$", title)
    if not match:
        match = re.search(r"-\s*(.+)$", title)
    if not match:
        return None

    text = match.group(1).strip()

    # Look for place after "in", "at", "to", "from", "í" (Icelandic)
    place_match = re.search(r"\b(?:in|at|to|from|near|around|í|til|frá)\s+(.+)$", text, re.IGNORECASE)
    if place_match:
        return place_match.group(1).strip()

    # Fallback: use the last capitalized word(s) as a place guess
    words = text.split()
    place_words = []
    for word in reversed(words):
        if word[0].isupper() or (place_words and word.lower() in ("the", "of", "el", "la")):
            place_words.insert(0, word)
        else:
            break
    if place_words:
        return " ".join(place_words)

    return None


def locate_entry(entry):
    """Try to find coordinates for an entry by geocoding its title."""
    place = extract_place_name(entry["title"])
    if not place:
        return None
    return geocode(place)

BASE_STYLE = """\
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
a, a:visited { color: inherit; }

:root {
    --bg: #131E17;
    --surface: #1A2B23;
    --text: #EDE8DF;
    --text-dim: #9A9488;
    --accent: #C4944A;
    --accent-light: #D4AC6E;
    --coral: #D45D4C;
    --sage: #6B7D62;
    --max-w: 720px;
}

@keyframes fadeUp {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    color: var(--text);
    background: var(--bg);
    line-height: 1.8;
    font-size: 16px;
    -webkit-font-smoothing: antialiased;
}

.container {
    max-width: var(--max-w);
    margin: 0 auto;
    padding: 72px 28px 100px;
    animation: fadeUp 0.5s ease both;
}

/* --- Top bar (header + nav unified) --- */

.topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 56px;
    padding-bottom: 20px;
    border-bottom: 1px solid rgba(196, 148, 74, 0.1);
}

.topbar .site-name,
.topbar .site-name:visited {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.01em;
    text-decoration: none;
    color: var(--text);
    transition: opacity 0.2s;
}

.topbar .site-name:hover {
    opacity: 0.7;
}

.topbar nav {
    display: flex;
    gap: 24px;
}

.topbar nav a {
    font-size: 12px;
    color: var(--text-dim);
    text-decoration: none;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 4px 0;
    border-bottom: 1.5px solid transparent;
    transition: color 0.2s, border-color 0.2s;
}

.topbar nav a:hover {
    color: var(--text);
}

.topbar nav a.active {
    color: var(--text);
    border-color: var(--accent);
}

/* --- Section heading --- */

.section-heading {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 36px;
    font-weight: 400;
    color: var(--text);
    margin-bottom: 48px;
    letter-spacing: -0.02em;
}

/* --- Entry list --- */

.entry-list {
    list-style: none;
}

.entry-list li {
    border-bottom: 1px solid rgba(196, 148, 74, 0.08);
}

.entry-list li:first-child {
    border-top: 1px solid rgba(196, 148, 74, 0.08);
}

.entry-list a {
    text-decoration: none;
    color: var(--text);
    display: flex;
    align-items: baseline;
    gap: 24px;
    padding: 24px 0;
    transition: opacity 0.2s;
}

.entry-list a:hover {
    opacity: 0.7;
}

.entry-date {
    font-size: 13px;
    color: var(--text-dim);
    white-space: nowrap;
    min-width: 90px;
    font-variant-numeric: tabular-nums;
}

.entry-title {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 22px;
    font-weight: 500;
    line-height: 1.35;
}

/* --- Article --- */

article h1 {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 44px;
    font-weight: 400;
    line-height: 1.15;
    margin-bottom: 16px;
    letter-spacing: -0.025em;
}

article .entry-date {
    margin-bottom: 48px;
    padding-bottom: 32px;
    border-bottom: 1px solid rgba(196, 148, 74, 0.15);
    min-width: 0;
}

article p {
    margin-bottom: 24px;
}

/* --- Images --- */

article img {
    width: 100%;
    height: auto;
    border-radius: 8px;
    margin: 40px 0;
    display: block;
}

article figure {
    margin: 40px 0;
}

article figure img {
    margin: 0;
}

article figcaption {
    font-size: 13px;
    color: var(--text-dim);
    margin-top: 12px;
    text-align: center;
    line-height: 1.5;
    font-style: italic;
}

/* --- Landing page --- */

.landing-hero {
    text-align: center;
    margin-bottom: 48px;
    padding: 32px 0 40px;
}

.landing-hero .hero-title {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 52px;
    font-weight: 300;
    letter-spacing: -0.03em;
    line-height: 1.1;
    color: var(--text);
    margin-bottom: 16px;
}

.landing-hero .hero-route {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 17px;
    font-style: italic;
    color: var(--accent);
    opacity: 0.6;
    margin-bottom: 20px;
}

.landing-hero .hero-dates {
    font-size: 11px;
    color: var(--text-dim);
    letter-spacing: 0.18em;
    text-transform: uppercase;
}

/* --- Map --- */

.map-section {
    margin-bottom: 0;
}

.map-wrap {
    position: relative;
    width: calc(100% + 56px);
    margin-left: -28px;
}

.map-container {
    width: 100%;
    height: 520px;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 0 0 1px rgba(196, 148, 74, 0.08), 0 12px 48px rgba(0, 0, 0, 0.4);
}

.map-hint {
    position: absolute;
    bottom: 16px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 12px;
    color: rgba(237, 232, 223, 0.7);
    background: rgba(19, 30, 23, 0.75);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    padding: 6px 16px;
    border-radius: 20px;
    letter-spacing: 0.04em;
    pointer-events: none;
    z-index: 1000;
    animation: hintFade 4s ease 2s forwards;
}

@keyframes hintFade {
    to { opacity: 0; }
}

@keyframes pulse {
    0%   { transform: scale(1); opacity: 0.6; }
    100% { transform: scale(2.8); opacity: 0; }
}

.map-pin {
    position: relative;
}

.map-pin .pin-dot {
    width: 12px;
    height: 12px;
    background: #D45D4C;
    border: 2.5px solid #EDE8DF;
    border-radius: 50%;
    position: absolute;
    top: 4px;
    left: 4px;
    z-index: 2;
    cursor: pointer;
    box-shadow: 0 1px 6px rgba(0, 0, 0, 0.3);
}

.map-pin .pin-pulse {
    width: 12px;
    height: 12px;
    background: #D45D4C;
    border-radius: 50%;
    position: absolute;
    top: 4px;
    left: 4px;
    z-index: 1;
    animation: pulse 2.5s ease-out infinite;
}

.map-stop .stop-dot {
    width: 8px;
    height: 8px;
    background: rgba(196, 148, 74, 0.2);
    border: 1.5px solid rgba(196, 148, 74, 0.5);
    border-radius: 50%;
    position: absolute;
    top: 1px;
    left: 1px;
}

.map-stats {
    display: flex;
    justify-content: center;
    gap: 32px;
    padding: 24px 0 16px;
}

.map-stats span {
    font-size: 12px;
    color: var(--text-dim);
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.map-stats span::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
    opacity: 0.4;
    margin-right: 8px;
    vertical-align: middle;
}

.map-container .leaflet-popup-content-wrapper {
    background: var(--surface);
    color: var(--text);
    border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    border: 1px solid rgba(196, 148, 74, 0.15);
}

.map-container .leaflet-popup-tip {
    background: var(--surface);
}

.map-container .leaflet-popup-content a {
    color: var(--accent-light);
    text-decoration: none;
}

.map-container .leaflet-popup-content a:hover {
    text-decoration: underline;
}

.map-container .leaflet-popup-content .popup-title {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 16px;
    font-weight: 500;
    margin-bottom: 6px;
}

.map-container .leaflet-popup-content .popup-date {
    font-size: 11px;
    color: var(--text-dim);
}

/* --- Gallery --- */

.gallery-grid {
    columns: 2;
    column-gap: 16px;
}

.gallery-item {
    break-inside: avoid;
    margin-bottom: 16px;
    border-radius: 8px;
    overflow: hidden;
    background: var(--surface);
    transition: transform 0.3s ease;
}

.gallery-item:hover {
    transform: translateY(-2px);
}

.gallery-item img {
    width: 100%;
    height: auto;
    display: block;
}

.gallery-item .gallery-info {
    padding: 12px 14px;
}

.gallery-item .gallery-caption {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 15px;
    color: var(--text);
    font-style: italic;
    line-height: 1.4;
    margin-bottom: 4px;
}

.gallery-item .gallery-entry-link {
    font-size: 11px;
    color: var(--text-dim);
    text-decoration: none;
    letter-spacing: 0.02em;
    transition: color 0.2s;
}

.gallery-item .gallery-entry-link:hover {
    color: var(--accent);
}

.gallery-empty, .video-empty {
    text-align: center;
    padding: 80px 0;
    color: var(--text-dim);
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 20px;
    font-style: italic;
}

/* --- Videos --- */

.video-grid {
    display: flex;
    flex-direction: column;
    gap: 28px;
}

.video-item {
    background: var(--surface);
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid rgba(196, 148, 74, 0.08);
    transition: transform 0.3s ease;
}

.video-item:hover {
    transform: translateY(-2px);
}

.video-embed {
    position: relative;
    padding-bottom: 56.25%;
    height: 0;
    overflow: hidden;
}

.video-embed iframe {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    border: none;
}

.video-info {
    padding: 18px 22px;
}

.video-title {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 20px;
    font-weight: 500;
    line-height: 1.3;
    margin-bottom: 4px;
}

.video-meta {
    font-size: 12px;
    color: var(--text-dim);
}

.video-meta .video-location {
    color: var(--accent);
}

/* --- Responsive --- */

@media (max-width: 600px) {
    .container { padding: 40px 20px 80px; }
    .topbar { flex-direction: column; align-items: flex-start; gap: 12px; }
    .topbar nav { gap: 16px; }
    .topbar nav a { font-size: 11px; }
    .section-heading { font-size: 28px; }
    article h1 { font-size: 32px; }
    .entry-list a { flex-direction: column; gap: 4px; }
    .entry-title { font-size: 19px; }
    .landing-hero { padding: 16px 0 32px; }
    .landing-hero .hero-title { font-size: 34px; }
    .map-wrap { width: calc(100% + 40px); margin-left: -20px; }
    .map-stats { gap: 20px; }
    .map-stats span { font-size: 11px; }
    .gallery-grid { columns: 1; }
    .map-container { height: 260px; }
}
"""


NAV_PAGES = [
    ("blog.html", "Journal"),
    ("gallery.html", "Photos"),
    ("videos.html", "Videos"),
]


def html_page(title, body, active_page=None, head_extra="", scripts=""):
    nav_links = ""
    for href, label in NAV_PAGES:
        cls = ' class="active"' if href == active_page else ""
        nav_links += f'<a href="{href}"{cls}>{label}</a>'
    topbar = f"""\
<div class="topbar">
<a href="index.html" class="site-name">Fer&eth;adagb&oacute;k</a>
<nav>{nav_links}</nav>
</div>"""

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;0,600;1,400&family=Inter:wght@400;500&display=swap" rel="stylesheet">
{head_extra}<style>html {{ background: #131E17; }}</style>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="container">
{topbar}
{body}
</div>
{scripts}</body>
</html>
"""


def parse_entry(filepath):
    """Parse a Markdown entry file into metadata."""
    text = filepath.read_text()
    # Extract title from first # heading
    title_match = re.match(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1) if title_match else filepath.stem

    # Extract date from filename (always present — filenames are yyyy-mm-dd-slug.md)
    clean_name = re.sub(r"[^0-9a-zA-Z._-]", "", filepath.name)
    date_match = re.match(r"(\d{4}-\d{2}-\d{2})", clean_name)
    date_str = date_match.group(1) if date_match else clean_name[:10]

    # Convert to HTML (skip the title line, we render it separately)
    body_md = text[title_match.end():].strip() if title_match else text
    # Rewrite image paths: ../images/ → images/ (entries are in docs/, images in docs/images/)
    body_md = body_md.replace("](../images/", "](images/")
    body_html = markdown.markdown(body_md)
    # Remove trailing horizontal rules (from leftover --- in Markdown)
    body_html = re.sub(r"(\s*<hr\s*/?>)+\s*$", "", body_html)
    # Wrap captioned images in <figure>/<figcaption>
    def _img_to_figure(m):
        alt, src = m.group(1), m.group(2)
        if alt:
            return f'<figure><img src="{src}" alt="{alt}"><figcaption>{alt}</figcaption></figure>'
        return f'<img src="{src}" alt="">'
    body_html = re.sub(r'<img\s+alt="([^"]*)"\s+src="([^"]*)"(?:\s*/)?>', _img_to_figure, body_html)

    return {
        "title": title,
        "date": date_str,
        "body_html": body_html,
        "slug": filepath.stem,
    }


def build():
    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir()

    (DOCS_DIR / "style.css").write_text(BASE_STYLE)

    docs_images = DOCS_DIR / "images"
    if IMAGES_DIR.exists() and any(IMAGES_DIR.iterdir()):
        shutil.copytree(IMAGES_DIR, docs_images)
        print(f"Copied {len(list(docs_images.iterdir()))} images → docs/images/")

    entry_files = sorted(ENTRIES_DIR.glob("*.md"))
    entries = [parse_entry(f) for f in entry_files]

    for entry in entries:
        body = f'<article><h1>{entry["title"]}</h1><div class="entry-date">{entry["date"]}</div>{entry["body_html"]}</article>'
        page = html_page(entry["title"], body, active_page="blog.html")
        (DOCS_DIR / f'{entry["slug"]}.html').write_text(page)

    # Build blog page (entry list)
    items = ""
    for entry in reversed(entries):  # newest first
        items += (
            f'<li><a href="{entry["slug"]}.html">'
            f'<div class="entry-date">{entry["date"]}</div>'
            f'<div class="entry-title">{entry["title"]}</div>'
            f'</a></li>\n'
        )
    blog_body = f'<h2 class="section-heading">Journal</h2>\n<ul class="entry-list">{items}</ul>'
    blog_page = html_page("Ferðadagbók — Blog", blog_body, active_page="blog.html")
    (DOCS_DIR / "blog.html").write_text(blog_page)

    gallery_items = []
    seen_srcs = set()
    for entry in reversed(entries):
        for m in re.finditer(r'<(?:figure><)?img\s+src="([^"]*)"(?:\s+alt="([^"]*)")?[^>]*>(?:<figcaption>([^<]*)</figcaption></figure>)?', entry["body_html"]):
            src = m.group(1)
            if src in seen_srcs:
                continue
            seen_srcs.add(src)
            caption = m.group(3) or m.group(2) or ""
            caption_html = f'<div class="gallery-caption">{caption}</div>' if caption else ""
            gallery_items.append(
                f'<div class="gallery-item">'
                f'<img src="{src}" alt="{caption}">'
                f'<div class="gallery-info">'
                f'{caption_html}'
                f'<a class="gallery-entry-link" href="{entry["slug"]}.html">{entry["title"]}</a>'
                f'</div></div>'
            )

    if not gallery_items:
        gallery_body = '<p class="gallery-empty">No photos yet — they\'ll appear here as the journey unfolds.</p>'
    else:
        gallery_body = f'<h2 class="section-heading">Photos</h2>\n<div class="gallery-grid">{chr(10).join(gallery_items)}</div>'
    gallery_page = html_page("Ferðadagbók — Photos", gallery_body, active_page="gallery.html")
    (DOCS_DIR / "gallery.html").write_text(gallery_page)

    # Build videos page
    videos_path = Path(__file__).parent / "videos.json"
    if videos_path.exists():
        videos = json.loads(videos_path.read_text())
        # Filter out placeholder entries
        videos = [v for v in videos if v.get("id") and not v["id"].startswith("YOUR_")]
    else:
        videos = []

    if not videos:
        videos_body = '<h2 class="section-heading">Videos</h2>\n<p class="video-empty">Drone footage coming soon — stay tuned.</p>'
    else:
        video_items = ""
        for v in videos:
            location_html = f' &middot; <span class="video-location">{v["location"]}</span>' if v.get("location") else ""
            video_items += (
                f'<div class="video-item">'
                f'<div class="video-embed">'
                f'<iframe src="https://www.youtube.com/embed/{v["id"]}" '
                f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
                f'allowfullscreen loading="lazy"></iframe>'
                f'</div>'
                f'<div class="video-info">'
                f'<div class="video-title">{v.get("title", "Untitled")}</div>'
                f'<div class="video-meta">{v.get("date", "")}{location_html}</div>'
                f'</div></div>\n'
            )
        videos_body = f'<h2 class="section-heading">Videos</h2>\n<div class="video-grid">{video_items}</div>'

    videos_page = html_page("Ferðadagbók — Videos", videos_body, active_page="videos.html")
    (DOCS_DIR / "videos.html").write_text(videos_page)
    video_count = len(videos)

    # Build map data — group entries by location
    location_groups = {}
    for entry in entries:
        loc = locate_entry(entry)
        if loc:
            key = (loc["lat"], loc["lng"])
            if key not in location_groups:
                location_groups[key] = {"name": loc["name"], "lat": loc["lat"], "lng": loc["lng"], "entries": []}
            location_groups[key]["entries"].append({
                "title": entry["title"],
                "date": entry["date"],
                "slug": entry["slug"],
            })

    map_markers_json = json.dumps(list(location_groups.values()))
    route_json = json.dumps(ROUTE_COORDS)

    # Build landing page (index) — custom layout with map
    entry_count = len(entries)
    image_count = len(seen_srcs)

    landing_body = f"""\
<div class="landing-hero">
<div class="hero-title">A journey through Indonesia</div>
<div class="hero-route">Jakarta &rarr; Borneo &rarr; Sulawesi &rarr; Flores &rarr; Jakarta</div>
<div class="hero-dates">May 1 &ndash; June 6, 2026</div>
</div>
<div class="map-section">
<div class="map-wrap">
<div id="map" class="map-container"></div>
<div class="map-hint">Click the pins to explore entries</div>
</div>
<div class="map-stats">
<span>{entry_count} entries</span>
<span>{image_count} photos</span>
<span>{video_count} videos</span>
</div>
</div>"""

    map_script = f"""\
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function() {{
    var map = L.map('map', {{
        zoomControl: false,
        attributionControl: false
    }}).setView([-4.5, 115.5], 5);

    L.control.zoom({{ position: 'bottomright' }}).addTo(map);

    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
        maxZoom: 13
    }}).addTo(map);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
        maxZoom: 13
    }}).addTo(map);

    var route = {route_json};
    L.polyline(route, {{
        color: '#C4944A',
        weight: 2,
        opacity: 0.45,
        dashArray: '6, 8',
        smoothFactor: 1.5
    }}).addTo(map);

    var markers = {map_markers_json};
    if (markers.length > 1) {{
        var travelled = markers.map(function(m) {{ return [m.lat, m.lng]; }});
        L.polyline(travelled, {{
            color: '#D45D4C',
            weight: 2.5,
            opacity: 0.8,
            smoothFactor: 1.5
        }}).addTo(map);
    }}

    var pinIcon = L.divIcon({{
        className: 'map-pin',
        html: '<div class="pin-dot"></div><div class="pin-pulse"></div>',
        iconSize: [20, 20],
        iconAnchor: [10, 10],
        popupAnchor: [0, -14]
    }});

    var stopIcon = L.divIcon({{
        className: 'map-stop',
        html: '<div class="stop-dot"></div>',
        iconSize: [10, 10],
        iconAnchor: [5, 5]
    }});

    var visitedKeys = {{}};
    markers.forEach(function(m) {{ visitedKeys[m.lat + ',' + m.lng] = true; }});
    route.forEach(function(coord) {{
        var key = coord[0] + ',' + coord[1];
        if (!visitedKeys[key]) {{
            visitedKeys[key] = true;
            L.marker(coord, {{ icon: stopIcon }}).addTo(map);
        }}
    }});

    markers.forEach(function(loc) {{
        var popupLines = '<div class="popup-title">' + loc.name + '</div>';
        loc.entries.forEach(function(e) {{
            popupLines += '<a href="' + e.slug + '.html"><span class="popup-date">' + e.date + '</span> ' + e.title.replace(/.*?—\\s*/, '') + '</a><br>';
        }});
        L.marker([loc.lat, loc.lng], {{ icon: pinIcon }})
            .bindPopup(popupLines, {{ maxWidth: 240 }})
            .addTo(map);
    }});
}})();
</script>"""

    leaflet_css = '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />\n'
    landing_html = html_page("Ferðadagbók", landing_body, head_extra=leaflet_css, scripts=map_script)
    (DOCS_DIR / "index.html").write_text(landing_html)

    _save_geocache()
    print(f"Built {len(entries)} entries + blog + gallery + landing → docs/")


if __name__ == "__main__":
    build()
