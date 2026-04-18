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


def load_geocache():
    """Load cached geocoding results from disk."""
    if GEOCACHE_PATH.exists():
        return json.loads(GEOCACHE_PATH.read_text())
    return {}


def save_geocache(cache):
    """Save geocoding results to disk."""
    GEOCACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def geocode(place_name):
    """Look up coordinates for a place name using OpenStreetMap Nominatim.

    Results are cached in .geocache.json so we only query once per place.
    """
    cache = load_geocache()
    key = place_name.lower().strip()

    if key in cache:
        return cache[key]

    # Query Nominatim — bounded to Indonesia for relevance
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": f"{place_name}, Indonesia",
            "format": "json",
            "limit": 1,
        },
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
        save_geocache(cache)
        # Be polite to Nominatim — max 1 request per second
        time.sleep(1)
        return loc

    # Cache misses too, so we don't re-query
    cache[key] = None
    save_geocache(cache)
    return None


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

:root {
    --bg: #1F2E28;
    --bg-light: #253530;
    --text: #F2EDE4;
    --text-muted: #B8B0A4;
    --wood: #A67348;
    --wood-dark: #8B5A3C;
    --mustard: #D4A82A;
    --tomato: #C94C3D;
    --orange: #D96A3B;
    --sage: #7A8B6F;
    --card-bg: rgba(37, 53, 48, 0.7);
    --max-width: 680px;
}

body {
    font-family: 'Inter', 'General Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    color: var(--text);
    background: var(--bg);
    line-height: 1.85;
    font-size: 17px;
    -webkit-font-smoothing: antialiased;
    /* subtle grain texture */
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E");
}

.container {
    max-width: var(--max-width);
    margin: 0 auto;
    padding: 100px 28px;
}

/* --- Header --- */

header {
    margin-bottom: 100px;
}

header a {
    text-decoration: none;
    color: inherit;
}

header h1 {
    font-family: 'Cormorant Garamond', 'Fraunces', Georgia, serif;
    font-size: 42px;
    font-weight: 500;
    letter-spacing: -0.02em;
    line-height: 1.15;
    color: var(--text);
}

header p {
    font-size: 14px;
    color: var(--text-muted);
    margin-top: 8px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

/* --- Entry list (index page) --- */

.entry-list {
    list-style: none;
}

.entry-list li {
    margin-bottom: 12px;
}

.entry-list a {
    text-decoration: none;
    color: var(--text);
    display: block;
    padding: 28px 32px;
    background: var(--card-bg);
    border-radius: 12px;
    border-left: 3px solid var(--wood);
    transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
}

.entry-list a:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.25);
    border-color: var(--mustard);
}

.entry-title {
    font-family: 'Cormorant Garamond', 'Fraunces', Georgia, serif;
    font-size: 24px;
    font-weight: 500;
    line-height: 1.35;
    letter-spacing: -0.01em;
}

.entry-date {
    font-size: 13px;
    color: var(--text-muted);
    margin-top: 6px;
    letter-spacing: 0.03em;
}

/* --- Article (entry page) --- */

article h1 {
    font-family: 'Cormorant Garamond', 'Fraunces', Georgia, serif;
    font-size: 38px;
    font-weight: 500;
    line-height: 1.2;
    margin-bottom: 12px;
    letter-spacing: -0.02em;
}

article .entry-date {
    margin-bottom: 48px;
    padding-bottom: 32px;
    border-bottom: 1px solid var(--wood-dark);
}

article p {
    margin-bottom: 24px;
}

/* --- Back navigation --- */

nav.back {
    margin-bottom: 60px;
}

nav.back a {
    font-size: 14px;
    color: var(--wood);
    text-decoration: none;
    letter-spacing: 0.02em;
    transition: color 0.2s ease;
}

nav.back a:hover {
    color: var(--mustard);
}

/* --- Images --- */

article img {
    width: 100%;
    height: auto;
    border-radius: 12px;
    margin: 36px 0;
    display: block;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

article figure {
    margin: 36px 0;
}

article figure img {
    margin: 0;
}

article figcaption {
    font-size: 14px;
    color: var(--text-muted);
    margin-top: 12px;
    text-align: center;
    line-height: 1.5;
    font-style: italic;
}

/* --- Landing page --- */

.landing-header {
    margin-bottom: 80px;
    text-align: center;
}

.landing-header h1 {
    font-family: 'Cormorant Garamond', 'Fraunces', Georgia, serif;
    font-size: 64px;
    font-weight: 400;
    letter-spacing: -0.03em;
    line-height: 1.05;
    color: var(--text);
}

.landing-header .subtitle {
    font-size: 15px;
    color: var(--text-muted);
    margin-top: 12px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}

.landing-header .route {
    font-family: 'Cormorant Garamond', 'Fraunces', Georgia, serif;
    font-size: 18px;
    font-style: italic;
    color: var(--sage);
    margin-top: 20px;
    line-height: 1.6;
}

.landing-divider {
    width: 48px;
    height: 2px;
    background: linear-gradient(90deg, var(--wood-dark), var(--wood), var(--wood-dark));
    margin: 0 auto 64px;
    border: none;
    border-radius: 1px;
}

.landing-nav {
    display: flex;
    gap: 20px;
    list-style: none;
}

.landing-nav li {
    flex: 1;
}

.landing-nav a {
    text-decoration: none;
    color: var(--text);
    display: block;
    padding: 40px 32px 36px;
    background: linear-gradient(160deg, rgba(37, 53, 48, 0.85), rgba(31, 46, 40, 0.6));
    border-radius: 16px;
    border: 1px solid rgba(166, 115, 72, 0.15);
    transition: all 0.3s ease;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
    position: relative;
    overflow: hidden;
}

.landing-nav a::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--wood-dark), var(--wood), var(--mustard));
    opacity: 0;
    transition: opacity 0.3s ease;
}

.landing-nav a:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.3);
    border-color: rgba(166, 115, 72, 0.3);
    background: linear-gradient(160deg, rgba(37, 53, 48, 0.95), rgba(31, 46, 40, 0.75));
}

.landing-nav a:hover::before {
    opacity: 1;
}

.landing-nav .nav-number {
    font-family: 'Cormorant Garamond', 'Fraunces', Georgia, serif;
    font-size: 48px;
    font-weight: 300;
    color: rgba(166, 115, 72, 0.25);
    line-height: 1;
    margin-bottom: 20px;
}

.landing-nav .nav-label {
    font-family: 'Cormorant Garamond', 'Fraunces', Georgia, serif;
    font-size: 28px;
    font-weight: 500;
    letter-spacing: -0.01em;
    margin-bottom: 8px;
}

.landing-nav .nav-desc {
    font-size: 14px;
    color: var(--text-muted);
    line-height: 1.5;
}

/* --- Section heading on subpages --- */

.section-heading {
    font-family: 'Cormorant Garamond', 'Fraunces', Georgia, serif;
    font-size: 32px;
    font-weight: 400;
    font-style: italic;
    color: var(--sage);
    margin-bottom: 40px;
    padding-bottom: 20px;
    border-bottom: 1px solid rgba(166, 115, 72, 0.2);
}

/* --- Gallery --- */

.gallery-grid {
    columns: 2;
    column-gap: 20px;
}

.gallery-item {
    break-inside: avoid;
    margin-bottom: 24px;
    position: relative;
    border-radius: 12px;
    overflow: hidden;
    background: var(--card-bg);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.gallery-item:hover {
    transform: translateY(-3px);
    box-shadow: 0 10px 36px rgba(0, 0, 0, 0.35);
}

.gallery-item img {
    width: 100%;
    height: auto;
    display: block;
    transition: transform 0.4s ease;
}

.gallery-item:hover img {
    transform: scale(1.03);
}

.gallery-item .gallery-info {
    padding: 14px 16px;
}

.gallery-item .gallery-caption {
    font-family: 'Cormorant Garamond', 'Fraunces', Georgia, serif;
    font-size: 16px;
    color: var(--text);
    font-style: italic;
    line-height: 1.4;
    margin-bottom: 4px;
}

.gallery-item .gallery-entry-link {
    font-size: 12px;
    color: var(--wood);
    text-decoration: none;
    letter-spacing: 0.02em;
    transition: color 0.2s ease;
}

.gallery-item .gallery-entry-link:hover {
    color: var(--mustard);
}

.gallery-empty {
    text-align: center;
    padding: 80px 0;
    color: var(--text-muted);
    font-family: 'Cormorant Garamond', 'Fraunces', Georgia, serif;
    font-size: 22px;
    font-style: italic;
}

/* --- Map --- */

.map-section {
    margin-bottom: 64px;
}

.map-container {
    width: 100%;
    height: 380px;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 6px 28px rgba(0, 0, 0, 0.35);
    border: 1px solid rgba(166, 115, 72, 0.2);
}

.map-container .leaflet-popup-content-wrapper {
    background: #1F2E28;
    color: #F2EDE4;
    border-radius: 10px;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.4);
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    border: 1px solid rgba(166, 115, 72, 0.25);
}

.map-container .leaflet-popup-tip {
    background: #1F2E28;
}

.map-container .leaflet-popup-content a {
    color: #D4A82A;
    text-decoration: none;
}

.map-container .leaflet-popup-content a:hover {
    text-decoration: underline;
}

.map-container .leaflet-popup-content .popup-title {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 17px;
    font-weight: 500;
    margin-bottom: 4px;
}

.map-container .leaflet-popup-content .popup-date {
    font-size: 12px;
    color: #B8B0A4;
}

/* --- Videos --- */

.video-grid {
    display: flex;
    flex-direction: column;
    gap: 32px;
}

.video-item {
    background: var(--card-bg);
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.video-item:hover {
    transform: translateY(-3px);
    box-shadow: 0 10px 36px rgba(0, 0, 0, 0.35);
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
    padding: 20px 24px;
}

.video-title {
    font-family: 'Cormorant Garamond', 'Fraunces', Georgia, serif;
    font-size: 22px;
    font-weight: 500;
    line-height: 1.3;
    margin-bottom: 6px;
}

.video-meta {
    font-size: 13px;
    color: var(--text-muted);
    letter-spacing: 0.02em;
}

.video-meta .video-location {
    color: var(--wood);
}

.video-empty {
    text-align: center;
    padding: 80px 0;
    color: var(--text-muted);
    font-family: 'Cormorant Garamond', 'Fraunces', Georgia, serif;
    font-size: 22px;
    font-style: italic;
}

/* --- Subpage navigation --- */

.subnav {
    display: flex;
    gap: 8px;
    margin-bottom: 48px;
    padding-bottom: 24px;
    border-bottom: 1px solid rgba(166, 115, 72, 0.15);
}

.subnav a {
    font-size: 14px;
    color: var(--text-muted);
    text-decoration: none;
    padding: 6px 16px;
    border-radius: 20px;
    transition: all 0.2s ease;
    letter-spacing: 0.02em;
}

.subnav a:hover {
    color: var(--text);
    background: rgba(242, 237, 228, 0.08);
}

.subnav a.active {
    color: var(--text);
    background: rgba(166, 115, 72, 0.2);
}

/* --- Ambient glow decoration --- */

body::before {
    content: '';
    position: fixed;
    top: -200px;
    right: -100px;
    width: 500px;
    height: 500px;
    background: radial-gradient(circle, rgba(212, 168, 42, 0.06) 0%, transparent 70%);
    pointer-events: none;
    z-index: -1;
}

body::after {
    content: '';
    position: fixed;
    bottom: -150px;
    left: -100px;
    width: 400px;
    height: 400px;
    background: radial-gradient(circle, rgba(166, 115, 72, 0.05) 0%, transparent 70%);
    pointer-events: none;
    z-index: -1;
}

/* --- Responsive --- */

@media (max-width: 600px) {
    .container { padding: 60px 20px; }
    header { margin-bottom: 60px; }
    header h1 { font-size: 32px; }
    article h1 { font-size: 28px; }
    .entry-title { font-size: 20px; }
    .entry-list a { padding: 22px 20px; }
    .landing-header h1 { font-size: 42px; }
    .landing-nav { flex-direction: column; gap: 14px; }
    .landing-nav a { padding: 32px 24px; }
    .landing-nav .nav-number { font-size: 36px; margin-bottom: 12px; }
    .gallery-grid { columns: 1; }
    .section-heading { font-size: 26px; }
    .map-container { height: 280px; }
}
"""


SUBNAV_PAGES = [
    ("index.html", "Home"),
    ("blog.html", "Journal"),
    ("gallery.html", "Photos"),
    ("videos.html", "Videos"),
]


def html_page(title, body, back_to=None, active_page=None):
    if back_to:
        back_nav = f'<nav class="back"><a href="{back_to}">&larr; Back</a></nav>'
    else:
        back_nav = ""

    if active_page:
        nav_links = ""
        for href, label in SUBNAV_PAGES:
            cls = ' class="active"' if href == active_page else ""
            nav_links += f'<a href="{href}"{cls}>{label}</a>\n'
        subnav = f'<nav class="subnav">{nav_links}</nav>'
    else:
        subnav = ""

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<style>html {{ background: #1F2E28; }}</style>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="container">
<header><a href="index.html"><h1>Fer&eth;adagb&oacute;k</h1><p>Indonesia &middot; 2026</p></a></header>
{subnav}
{back_nav}
{body}
</div>
</body>
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

    # Write CSS to a separate cached file
    (DOCS_DIR / "style.css").write_text(BASE_STYLE)

    # Copy images to docs/images/ if any exist
    docs_images = DOCS_DIR / "images"
    if IMAGES_DIR.exists() and any(IMAGES_DIR.iterdir()):
        shutil.copytree(IMAGES_DIR, docs_images)
        print(f"Copied {len(list(docs_images.iterdir()))} images → docs/images/")

    # Gather and sort entries by filename (date)
    entry_files = sorted(ENTRIES_DIR.glob("*.md"))
    entries = [parse_entry(f) for f in entry_files]

    # Build individual entry pages
    for entry in entries:
        body = f'<article><h1>{entry["title"]}</h1><div class="entry-date">{entry["date"]}</div>{entry["body_html"]}</article>'
        page = html_page(entry["title"], body, back_to="blog.html")
        (DOCS_DIR / f'{entry["slug"]}.html').write_text(page)

    # Build blog page (entry list)
    items = ""
    for entry in reversed(entries):  # newest first
        items += (
            f'<li><a href="{entry["slug"]}.html">'
            f'<div class="entry-title">{entry["title"]}</div>'
            f'<div class="entry-date">{entry["date"]}</div>'
            f'</a></li>\n'
        )
    blog_body = f'<h2 class="section-heading">Journal</h2>\n<ul class="entry-list">{items}</ul>'
    blog_page = html_page("Ferðadagbók — Blog", blog_body, active_page="blog.html")
    (DOCS_DIR / "blog.html").write_text(blog_page)

    # Build gallery page (all images from entries)
    # Collect images — track seen URLs to avoid duplicates from figure+img
    gallery_items = ""
    seen_srcs = set()
    for entry in reversed(entries):
        # Check for figure-wrapped images first
        for fig_match in re.finditer(r'<figure><img\s+src="([^"]*)"(?:\s+alt="([^"]*)")?><figcaption>([^<]*)</figcaption></figure>', entry["body_html"]):
            src, alt, caption = fig_match.group(1), fig_match.group(2) or "", fig_match.group(3)
            seen_srcs.add(src)
            caption_html = f'<div class="gallery-caption">{caption}</div>' if caption else ""
            gallery_items += (
                f'<div class="gallery-item">'
                f'<img src="{src}" alt="{alt}">'
                f'<div class="gallery-info">'
                f'{caption_html}'
                f'<a class="gallery-entry-link" href="{entry["slug"]}.html">{entry["title"]}</a>'
                f'</div></div>\n'
            )
        # Then standalone images not already captured
        for img_match in re.finditer(r'<img\s+src="([^"]*)"(?:\s+alt="([^"]*)")?', entry["body_html"]):
            src, alt = img_match.group(1), img_match.group(2) or ""
            if src in seen_srcs:
                continue
            seen_srcs.add(src)
            caption_html = f'<div class="gallery-caption">{alt}</div>' if alt else ""
            gallery_items += (
                f'<div class="gallery-item">'
                f'<img src="{src}" alt="{alt}">'
                f'<div class="gallery-info">'
                f'{caption_html}'
                f'<a class="gallery-entry-link" href="{entry["slug"]}.html">{entry["title"]}</a>'
                f'</div></div>\n'
            )

    if not gallery_items:
        gallery_body = '<p class="gallery-empty">No photos yet — they\'ll appear here as the journey unfolds.</p>'
    else:
        gallery_body = f'<h2 class="section-heading">Photos</h2>\n<div class="gallery-grid">{gallery_items}</div>'
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
    landing_html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fer&eth;adagb&oacute;k</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>html {{ background: #1F2E28; }}</style>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="container">
<div class="landing-header">
<h1>Fer&eth;adagb&oacute;k</h1>
<div class="subtitle">Indonesia &middot; 2026</div>
<div class="route">Jakarta &rarr; Borneo &rarr; Sulawesi &rarr; Flores &rarr; Jakarta</div>
</div>
<hr class="landing-divider">
<div class="map-section">
<div id="map" class="map-container"></div>
</div>
<ul class="landing-nav">
<li><a href="blog.html">
<div class="nav-number">I</div>
<div class="nav-label">Journal</div>
<div class="nav-desc">{entry_count} entries from the road</div>
</a></li>
<li><a href="gallery.html">
<div class="nav-number">II</div>
<div class="nav-label">Photos</div>
<div class="nav-desc">{image_count} snapshots along the way</div>
</a></li>
<li><a href="videos.html">
<div class="nav-number">III</div>
<div class="nav-label">Videos</div>
<div class="nav-desc">{video_count} drone shots from above</div>
</a></li>
</ul>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function() {{
    var map = L.map('map', {{
        zoomControl: false,
        attributionControl: false
    }}).setView([-4.5, 115.5], 5);

    L.control.zoom({{ position: 'bottomright' }}).addTo(map);

    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
        maxZoom: 17,
        subdomains: 'abcd'
    }}).addTo(map);

    // Route line
    var route = {route_json};
    L.polyline(route, {{
        color: '#8B5A3C',
        weight: 2.5,
        opacity: 0.4,
        dashArray: '8, 8',
        smoothFactor: 1.5
    }}).addTo(map);

    // Travelled route (entries we have so far)
    var markers = {map_markers_json};
    if (markers.length > 1) {{
        var travelled = markers.map(function(m) {{ return [m.lat, m.lng]; }});
        L.polyline(travelled, {{
            color: '#C94C3D',
            weight: 3,
            opacity: 0.7,
            smoothFactor: 1.5
        }}).addTo(map);
    }}

    // Custom marker icon
    var pinIcon = L.divIcon({{
        className: '',
        html: '<div style="width:16px;height:16px;background:#C94C3D;border:3px solid #F2EDE4;border-radius:50%;box-shadow:0 2px 10px rgba(0,0,0,0.35);"></div>',
        iconSize: [16, 16],
        iconAnchor: [8, 8],
        popupAnchor: [0, -12]
    }});

    // Route stop icon (not yet visited)
    var stopIcon = L.divIcon({{
        className: '',
        html: '<div style="width:10px;height:10px;background:rgba(139,90,60,0.3);border:2px solid #8B5A3C;border-radius:50%;"></div>',
        iconSize: [10, 10],
        iconAnchor: [5, 5]
    }});

    // Place hollow markers on future route stops
    var routeStops = {route_json};
    var visitedKeys = {{}};
    markers.forEach(function(m) {{ visitedKeys[m.lat + ',' + m.lng] = true; }});
    routeStops.forEach(function(coord) {{
        var key = coord[0] + ',' + coord[1];
        if (!visitedKeys[key]) {{
            visitedKeys[key] = true;
            L.marker(coord, {{ icon: stopIcon }}).addTo(map);
        }}
    }});

    // Entry markers with popups
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
</script>
</body>
</html>"""
    (DOCS_DIR / "index.html").write_text(landing_html)

    print(f"Built {len(entries)} entries + blog + gallery + landing → docs/")


if __name__ == "__main__":
    build()
