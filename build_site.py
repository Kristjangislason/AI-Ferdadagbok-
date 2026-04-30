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

GEOCACHE_PATH = Path(__file__).parent / ".geocache.json"
YOUTUBE_CACHE_PATH = Path(__file__).parent / ".youtube-cache.json"


_geocache = None
_youtube_cache = None


def _load_youtube_cache():
    global _youtube_cache
    if _youtube_cache is None:
        _youtube_cache = json.loads(YOUTUBE_CACHE_PATH.read_text()) if YOUTUBE_CACHE_PATH.exists() else {}
    return _youtube_cache


def _save_youtube_cache():
    if _youtube_cache is not None:
        YOUTUBE_CACHE_PATH.write_text(json.dumps(_youtube_cache, indent=2, ensure_ascii=False))


def fetch_youtube_meta(video_id):
    """Look up a YouTube video's title via oEmbed, with disk cache."""
    cache = _load_youtube_cache()
    if video_id in cache:
        return cache[video_id]
    meta = {"title": "", "author": ""}
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=10,
        )
        if resp.status_code == 200:
            j = resp.json()
            meta = {"title": j.get("title", ""), "author": j.get("author_name", "")}
    except Exception:
        pass
    cache[video_id] = meta
    return meta


YOUTUBE_SENTINEL_RE = re.compile(r"(?:<p>\s*)?<!--youtube:([\w-]{11})-->(?:\s*</p>)?")


def youtube_iframe(video_id):
    return (
        '<div class="video-embed">'
        f'<iframe src="https://www.youtube.com/embed/{video_id}" '
        'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
        'allowfullscreen loading="lazy"></iframe>'
        '</div>'
    )


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


LOCATION_LINE_RE = re.compile(
    r"^\s*Sta[ðd][iu]r\s*:\s*(.+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def extract_locations_from_body(md_text):
    """Pull a 'Staðir: A, B, C' (or 'Staður: A') line out of the body.

    Returns (places_list, cleaned_md). The line is removed from the body
    so it doesn't render on the page.
    """
    m = LOCATION_LINE_RE.search(md_text)
    if not m:
        return [], md_text
    places = [p.strip() for p in m.group(1).split(",") if p.strip()]
    cleaned = LOCATION_LINE_RE.sub("", md_text, count=1).strip()
    return places, cleaned


def extract_place_from_title(title):
    """Title-based fallback when the body has no Staðir: line."""
    text = title.strip()
    # Drop a leading date or dash prefix if present
    m = re.search(r"[—-]\s*(.+)$", text)
    if m:
        text = m.group(1).strip()

    # Look for a place after a preposition: in/at/to/from (en) or í/til/frá (is)
    place_match = re.search(
        r"\b(?:in|at|to|from|near|around|í|til|frá)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if place_match:
        return place_match.group(1).strip().rstrip(".,;:")

    # Fallback: trailing capitalized word(s)
    words = text.split()
    place_words = []
    for word in reversed(words):
        if word and (word[0].isupper() or (place_words and word.lower() in ("the", "of", "el", "la"))):
            place_words.insert(0, word)
        else:
            break
    if place_words:
        return " ".join(place_words).rstrip(".,;:")
    return None


def locate_entry_places(entry):
    """Geocode every place declared in the entry. Returns a list of locations."""
    places = list(entry.get("locations") or [])
    if not places:
        guess = extract_place_from_title(entry["title"])
        if guess:
            places = [guess]

    locations = []
    seen = set()
    for p in places:
        loc = geocode(p)
        if not loc:
            continue
        key = (round(loc["lat"], 4), round(loc["lng"], 4))
        if key in seen:
            continue
        seen.add(key)
        locations.append(loc)
    return locations

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
    --max-w-wide: 1180px;
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
    padding: 56px 28px 100px;
    animation: fadeUp 0.5s ease both;
}

.container--wide {
    max-width: var(--max-w-wide);
}

/* --- Site header (full-width banded bar) --- */

.site-header {
    background: var(--surface);
    border-bottom: 1px solid rgba(196, 148, 74, 0.12);
}

.site-header-inner {
    max-width: var(--max-w-wide);
    margin: 0 auto;
    padding: 16px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 32px;
}

.site-title,
.site-title:visited {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 17px;
    font-style: italic;
    font-weight: 400;
    letter-spacing: 0.01em;
    color: var(--text);
    text-decoration: none;
    transition: opacity 0.2s;
    line-height: 1.3;
}

.site-title:hover {
    opacity: 0.7;
}

.site-header nav {
    display: flex;
    gap: 24px;
    flex-shrink: 0;
}

.site-header nav a,
.site-header nav a:visited {
    font-size: 11px;
    color: var(--text-dim);
    text-decoration: none;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 4px 0;
    border-bottom: 1.5px solid transparent;
    transition: color 0.2s, border-color 0.2s;
}

.site-header nav a:hover {
    color: var(--text);
}

.site-header nav a.active {
    color: var(--text);
    border-color: var(--accent);
}

@media (max-width: 600px) {
    .site-header-inner {
        flex-direction: column;
        align-items: flex-start;
        gap: 10px;
        padding: 14px 20px;
    }
    .site-title { font-size: 15px; }
    .site-header nav { gap: 16px; }
    .site-header nav a { font-size: 10px; }
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

.back-link,
.back-link:visited {
    display: inline-block;
    color: var(--text-dim);
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    text-decoration: none;
    margin-bottom: 40px;
    transition: color 0.2s;
}

.back-link:hover {
    color: var(--text);
}

.entry-pager {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-top: 64px;
    padding-top: 32px;
    border-top: 1px solid rgba(196, 148, 74, 0.15);
}

.entry-pager-prev,
.entry-pager-next,
.entry-pager-prev:visited,
.entry-pager-next:visited {
    display: flex;
    flex-direction: column;
    gap: 6px;
    text-decoration: none;
    color: var(--text);
    min-width: 0;
    transition: opacity 0.2s;
}

.entry-pager-prev { grid-column: 1; }

.entry-pager-next {
    grid-column: 2;
    text-align: right;
    align-items: flex-end;
}

.entry-pager-prev:hover,
.entry-pager-next:hover {
    opacity: 0.7;
}

.entry-pager .pager-direction {
    font-size: 11px;
    color: var(--text-dim);
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.entry-pager .pager-title {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 18px;
    line-height: 1.3;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}

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

/* --- Landing: compact hero + map/accordion layout --- */

.hero-compact {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 17px;
    font-style: italic;
    color: var(--text-dim);
    text-align: center;
    margin: -16px 0 32px;
}

.hero-compact .sep {
    margin: 0 10px;
    opacity: 0.4;
}

.dagbok-layout {
    display: grid;
    grid-template-columns: 1fr 42%;
    grid-template-areas: "journal map";
    gap: 56px;
    align-items: start;
    position: relative;
    transition: grid-template-columns 0.35s ease;
}

.dagbok-layout.map-hidden {
    grid-template-columns: 1fr;
    grid-template-areas: "journal";
}

.dagbok-layout.map-hidden .map-pane {
    display: none;
}

.map-pane {
    grid-area: map;
    position: sticky;
    top: 24px;
    align-self: start;
}

.journal-pane {
    grid-area: journal;
    min-width: 0;
}

.map-toggle {
    position: absolute;
    top: -8px;
    right: 0;
    background: rgba(196, 148, 74, 0.08);
    color: var(--text-dim);
    border: 1px solid rgba(196, 148, 74, 0.2);
    border-radius: 999px;
    padding: 7px 14px 7px 12px;
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background 0.2s, color 0.2s, border-color 0.2s;
    z-index: 5;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: inherit;
}

.map-toggle:hover {
    background: rgba(196, 148, 74, 0.18);
    color: var(--text);
    border-color: rgba(196, 148, 74, 0.4);
}

.map-toggle .map-toggle-icon {
    font-size: 13px;
    line-height: 1;
}

/* --- Map --- */

.map-wrap {
    position: relative;
}

.map-container {
    width: 100%;
    height: 70vh;
    min-height: 480px;
    max-height: 720px;
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
    transition: transform 0.2s ease, background 0.2s, border-color 0.2s;
}

.map-pin.highlighted .pin-dot {
    transform: scale(1.5);
    background: #E8806E;
}

.map-pin.selected .pin-dot {
    transform: scale(1.6);
    background: var(--accent);
    border-color: var(--accent-light);
}

.map-pin.selected .pin-pulse {
    background: var(--accent);
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

/* --- Dagbók accordion (homepage) --- */

.dagbok-accordion {
    list-style: none;
}

.entry-row {
    border-bottom: 1px solid rgba(196, 148, 74, 0.1);
    scroll-margin-top: 24px;
}

.entry-row:first-child {
    border-top: 1px solid rgba(196, 148, 74, 0.1);
}

.entry-row > summary {
    list-style: none;
    cursor: pointer;
    display: grid;
    grid-template-columns: 110px 1fr auto 16px;
    gap: 18px;
    align-items: baseline;
    padding: 22px 4px;
    border-radius: 8px;
    margin: 0 -4px;
    transition: background 0.2s;
}

.entry-row > summary::-webkit-details-marker { display: none; }
.entry-row > summary::marker { display: none; }

.entry-row > summary:hover,
.entry-row.highlighted > summary {
    background: rgba(196, 148, 74, 0.05);
}

.entry-row[open] > summary {
    background: rgba(196, 148, 74, 0.07);
}

.entry-row-date {
    font-size: 13px;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}

.entry-row-title {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 22px;
    font-weight: 500;
    line-height: 1.35;
    color: var(--text);
}

.entry-row-places {
    font-size: 11px;
    color: var(--accent);
    opacity: 0.75;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    white-space: nowrap;
    padding: 2px 10px;
    border: 1px solid rgba(196, 148, 74, 0.25);
    border-radius: 999px;
}

.entry-row-chevron {
    font-size: 14px;
    color: var(--text-dim);
    line-height: 1;
    transition: transform 0.25s ease;
}

.entry-row[open] .entry-row-chevron {
    transform: rotate(90deg);
}

.entry-row-body {
    padding: 8px 4px 48px;
    animation: fadeUp 0.35s ease both;
}

.entry-row-body article h1,
.entry-row-body article > .entry-date {
    display: none;
}

.entry-row-body article p:first-of-type {
    margin-top: 0;
}

.entry-row-body article img,
.entry-row-body article figure {
    margin: 28px 0;
}

.entry-row-permalink {
    display: inline-block;
    margin-top: 24px;
    font-size: 11px;
    color: var(--text-dim);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    text-decoration: none;
    transition: color 0.2s;
}

.entry-row-permalink:hover {
    color: var(--accent);
}

/* --- Gallery --- */

.gallery-grid {
    columns: 3;
    column-gap: 18px;
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
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
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

.video-meta .video-location,
.video-meta a.video-location:visited {
    color: var(--accent);
    text-decoration: none;
}

.video-meta a.video-location:hover {
    text-decoration: underline;
}

/* --- Responsive --- */

@media (max-width: 900px) {
    .dagbok-layout {
        grid-template-columns: 1fr;
        grid-template-areas: "map" "journal";
        gap: 28px;
    }
    .dagbok-layout.map-hidden { grid-template-areas: "journal"; }
    .map-pane { position: static; }
    .map-container { height: 320px; min-height: 0; max-height: none; }
    .gallery-grid { columns: 2; }
    .video-grid { grid-template-columns: 1fr; }
    .entry-row > summary { grid-template-columns: 90px 1fr auto 14px; gap: 14px; }
    .entry-row-title { font-size: 19px; }
    .map-toggle { top: -36px; font-size: 10px; }
}

@media (max-width: 600px) {
    .container { padding: 40px 20px 80px; }
    .topbar { flex-direction: column; align-items: flex-start; gap: 12px; }
    .topbar nav { gap: 16px; }
    .topbar nav a { font-size: 11px; }
    .section-heading { font-size: 28px; }
    article h1 { font-size: 32px; }
    .entry-list a { flex-direction: column; gap: 4px; }
    .entry-title { font-size: 19px; }
    .hero-compact { font-size: 14px; margin-top: -8px; }
    .hero-compact .sep { margin: 0 6px; }
    .map-stats { gap: 20px; }
    .map-stats span { font-size: 11px; }
    .gallery-grid { columns: 1; }
    .map-container { height: 260px; }
    .entry-pager { grid-template-columns: 1fr; gap: 20px; }
    .entry-pager-next {
        grid-column: 1;
        text-align: left;
        align-items: flex-start;
    }
    .back-link { margin-bottom: 28px; }
    .entry-row > summary {
        grid-template-columns: 1fr 14px;
        grid-template-areas:
            "date chevron"
            "title chevron"
            "places chevron";
        gap: 6px 14px;
        padding: 18px 4px;
    }
    .entry-row-date { grid-area: date; }
    .entry-row-title { grid-area: title; }
    .entry-row-places { grid-area: places; justify-self: start; }
    .entry-row-chevron { grid-area: chevron; align-self: center; }
}

/* --- Lightbox --- */

.lightbox {
    position: fixed;
    inset: 0;
    background: rgba(8, 14, 10, 0.96);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    display: none;
    z-index: 10000;
    align-items: center;
    justify-content: center;
    animation: lightboxIn 0.2s ease;
}

.lightbox.open { display: flex; }

@keyframes lightboxIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

.lightbox-figure {
    position: relative;
    max-width: 92vw;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
}

.lightbox-img {
    max-width: 92vw;
    max-height: 82vh;
    width: auto;
    height: auto;
    object-fit: contain;
    border-radius: 6px;
    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.6);
}

.lightbox-caption {
    color: var(--text-dim);
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: 15px;
    font-style: italic;
    text-align: center;
    max-width: 720px;
    line-height: 1.5;
    min-height: 1em;
}

.lightbox-counter {
    position: absolute;
    top: 24px;
    left: 50%;
    transform: translateX(-50%);
    color: var(--text-dim);
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-variant-numeric: tabular-nums;
    background: rgba(19, 30, 23, 0.6);
    padding: 6px 14px;
    border-radius: 999px;
    pointer-events: none;
}

.lightbox-close,
.lightbox-prev,
.lightbox-next {
    position: absolute;
    background: rgba(237, 232, 223, 0.06);
    color: var(--text);
    border: 1px solid rgba(237, 232, 223, 0.15);
    cursor: pointer;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s, border-color 0.2s, transform 0.15s;
    font-family: inherit;
    -webkit-tap-highlight-color: transparent;
}

.lightbox-close:hover,
.lightbox-prev:hover,
.lightbox-next:hover {
    background: rgba(237, 232, 223, 0.16);
    border-color: rgba(237, 232, 223, 0.35);
}

.lightbox-prev:active,
.lightbox-next:active { transform: scale(0.92); }

.lightbox-close {
    top: 20px;
    right: 20px;
    width: 44px;
    height: 44px;
    font-size: 26px;
    line-height: 1;
}

.lightbox-prev,
.lightbox-next {
    top: 50%;
    transform: translateY(-50%);
    width: 52px;
    height: 52px;
    font-size: 22px;
}

.lightbox-prev { left: 24px; }
.lightbox-next { right: 24px; }

.lightbox.is-single .lightbox-prev,
.lightbox.is-single .lightbox-next,
.lightbox.is-single .lightbox-counter { display: none; }

body.lightbox-open { overflow: hidden; }

/* Make article and gallery images clickable */
article img,
.gallery-item img {
    cursor: zoom-in;
}

@media (max-width: 600px) {
    .lightbox-prev, .lightbox-next {
        width: 44px;
        height: 44px;
        font-size: 18px;
    }
    .lightbox-prev { left: 12px; }
    .lightbox-next { right: 12px; }
    .lightbox-close { top: 12px; right: 12px; }
    .lightbox-counter { top: 16px; font-size: 10px; }
    .lightbox-caption { font-size: 13px; padding: 0 16px; }
}
"""


NAV_PAGES = [
    ("index.html", "Dagbók"),
    ("gallery.html", "Myndir"),
    ("videos.html", "Myndbönd"),
]

ICELANDIC_MONTHS = {
    1: "janúar", 2: "febrúar", 3: "mars", 4: "apríl",
    5: "maí", 6: "júní", 7: "júlí", 8: "ágúst",
    9: "september", 10: "október", 11: "nóvember", 12: "desember",
}


def format_date_is(date_str):
    """Render YYYY-MM-DD as Icelandic '8. maí 2026'."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_str.strip())
    if not m:
        return date_str
    y, mo, d = m.groups()
    month = ICELANDIC_MONTHS.get(int(mo), mo)
    return f"{int(d)}. {month} {y}"


def pluralize_is(count, singular, plural):
    """Pick Icelandic singular/plural based on count (n == 1 → singular)."""
    return f"{count} {singular if count == 1 else plural}"


def lazyfy_iframes(html):
    """Replace iframe src with data-src so iframes don't load until JS injects them.
    Used for the homepage accordion to avoid loading every YouTube embed up front.
    """
    return re.sub(r'<iframe\s+src="([^"]+)"', r'<iframe data-src="\1"', html)


def render_entry_row(entry):
    """One <details> accordion row for the homepage Dagbók."""
    date_is = format_date_is(entry["date"])
    place_chip = ""
    place_names = entry.get("place_names") or []
    if place_names:
        chip = " &middot; ".join(place_names)
        place_chip = f'<span class="entry-row-places">{chip}</span>'
    body_html = lazyfy_iframes(entry["body_html"])
    return (
        f'<details class="entry-row" id="{entry["slug"]}">'
        f'<summary>'
        f'<span class="entry-row-date">{date_is}</span>'
        f'<span class="entry-row-title">{entry["title"]}</span>'
        f'{place_chip}'
        f'<span class="entry-row-chevron">&rsaquo;</span>'
        f'</summary>'
        f'<div class="entry-row-body">'
        f'<article>{body_html}</article>'
        f'<a class="entry-row-permalink" href="{entry["slug"]}.html">'
        f'Opna sem s&iacute;&eth;u &rarr;'
        f'</a>'
        f'</div>'
        f'</details>'
    )


def render_entry_pager(prev_entry, next_entry):
    """Prev/next links shown at the bottom of an entry page."""
    if not prev_entry and not next_entry:
        return ""
    parts = ['<nav class="entry-pager">']
    if prev_entry:
        parts.append(
            f'<a class="entry-pager-prev" href="{prev_entry["slug"]}.html">'
            f'<span class="pager-direction">&larr; Fyrri f&aelig;rsla</span>'
            f'<span class="pager-title">{prev_entry["title"]}</span>'
            f'</a>'
        )
    if next_entry:
        parts.append(
            f'<a class="entry-pager-next" href="{next_entry["slug"]}.html">'
            f'<span class="pager-direction">N&aelig;sta f&aelig;rsla &rarr;</span>'
            f'<span class="pager-title">{next_entry["title"]}</span>'
            f'</a>'
        )
    parts.append('</nav>')
    return "".join(parts)


LIGHTBOX_SCRIPT = """\
<script>
(function() {
    var imgs = Array.prototype.slice.call(
        document.querySelectorAll('article img, .gallery-item img')
    );
    if (!imgs.length) return;

    var overlay = document.createElement('div');
    overlay.className = 'lightbox';
    overlay.innerHTML = ''
        + '<button type="button" class="lightbox-close" aria-label="Loka">&times;</button>'
        + '<button type="button" class="lightbox-prev" aria-label="Fyrri mynd">&larr;</button>'
        + '<div class="lightbox-counter"></div>'
        + '<figure class="lightbox-figure">'
        +   '<img class="lightbox-img" alt="">'
        +   '<figcaption class="lightbox-caption"></figcaption>'
        + '</figure>'
        + '<button type="button" class="lightbox-next" aria-label="N&aelig;sta mynd">&rarr;</button>';
    document.body.appendChild(overlay);
    if (imgs.length < 2) overlay.classList.add('is-single');

    var imgEl = overlay.querySelector('.lightbox-img');
    var capEl = overlay.querySelector('.lightbox-caption');
    var counterEl = overlay.querySelector('.lightbox-counter');
    var current = 0;

    function update() {
        var src = imgs[current];
        imgEl.src = src.src;
        imgEl.alt = src.alt || '';
        capEl.textContent = src.alt || '';
        counterEl.textContent = (current + 1) + ' / ' + imgs.length;
    }

    function open(i) {
        current = i;
        update();
        overlay.classList.add('open');
        document.body.classList.add('lightbox-open');
    }

    function close() {
        overlay.classList.remove('open');
        document.body.classList.remove('lightbox-open');
    }

    function prev() { current = (current - 1 + imgs.length) % imgs.length; update(); }
    function next() { current = (current + 1) % imgs.length; update(); }

    imgs.forEach(function(img, i) {
        img.addEventListener('click', function(e) {
            e.preventDefault();
            open(i);
        });
    });

    overlay.querySelector('.lightbox-close').addEventListener('click', close);
    overlay.querySelector('.lightbox-prev').addEventListener('click', function(e) {
        e.stopPropagation(); prev();
    });
    overlay.querySelector('.lightbox-next').addEventListener('click', function(e) {
        e.stopPropagation(); next();
    });
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay || e.target.classList.contains('lightbox-figure')) close();
    });

    document.addEventListener('keydown', function(e) {
        if (!overlay.classList.contains('open')) return;
        if (e.key === 'Escape') close();
        else if (e.key === 'ArrowLeft') prev();
        else if (e.key === 'ArrowRight') next();
    });
})();
</script>
"""


def html_page(title, body, active_page=None, head_extra="", scripts="", wide=False):
    nav_links = ""
    for href, label in NAV_PAGES:
        cls = ' class="active"' if href == active_page else ""
        nav_links += f'<a href="{href}"{cls}>{label}</a>'
    site_header = f"""\
<header class="site-header">
<div class="site-header-inner">
<a class="site-title" href="index.html">Kristj&aacute;n og India Br&iacute;et &mdash; Fer&eth; um Ind&oacute;nes&iacute;u</a>
<nav>{nav_links}</nav>
</div>
</header>"""

    container_class = "container container--wide" if wide else "container"
    return f"""\
<!DOCTYPE html>
<html lang="is">
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
{site_header}
<div class="{container_class}">
{body}
</div>
{scripts}{LIGHTBOX_SCRIPT}</body>
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
    # Pull "Staðir: A, B" out of the body — used for map pins, hidden from the page
    locations, body_md = extract_locations_from_body(body_md)
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
    # Replace YouTube sentinels with embedded iframes, and remember the IDs
    youtube_ids = YOUTUBE_SENTINEL_RE.findall(body_html)
    body_html = YOUTUBE_SENTINEL_RE.sub(lambda m: youtube_iframe(m.group(1)), body_html)

    return {
        "title": title,
        "date": date_str,
        "body_html": body_html,
        "slug": filepath.stem,
        "locations": locations,
        "youtube_ids": youtube_ids,
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

    # Resolve coordinates for each entry up front — used for both the map markers
    # and the JS map↔accordion sync.
    for entry in entries:
        resolved = locate_entry_places(entry)
        entry["resolved_locations"] = resolved
        entry["location_keys"] = [
            f"{round(loc['lat'], 4)},{round(loc['lng'], 4)}" for loc in resolved
        ]
        entry["place_names"] = [loc["name"] for loc in resolved]

    # Per-entry standalone pages (narrow reading column)
    for i, entry in enumerate(entries):
        date_is = format_date_is(entry["date"])
        prev_entry = entries[i - 1] if i > 0 else None
        next_entry = entries[i + 1] if i + 1 < len(entries) else None
        body = (
            f'<a class="back-link" href="index.html#{entry["slug"]}">'
            f'&larr; Til baka &iacute; Dagb&oacute;k'
            f'</a>'
            f'<article><h1>{entry["title"]}</h1>'
            f'<div class="entry-date">{date_is}</div>'
            f'{entry["body_html"]}</article>'
            f'{render_entry_pager(prev_entry, next_entry)}'
        )
        page = html_page(entry["title"], body, active_page="index.html")
        (DOCS_DIR / f'{entry["slug"]}.html').write_text(page)

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
        gallery_body = '<p class="gallery-empty">Engar myndir ennþá — þær birtast hér eftir því sem ferðin þróast.</p>'
    else:
        gallery_body = f'<h2 class="section-heading">Myndir</h2>\n<div class="gallery-grid">{chr(10).join(gallery_items)}</div>'
    gallery_page = html_page("Ferðadagbók — Myndir", gallery_body, active_page="gallery.html", wide=True)
    (DOCS_DIR / "gallery.html").write_text(gallery_page)

    # Videos page: merge curated videos.json with YouTube embeds discovered in entries
    videos_path = Path(__file__).parent / "videos.json"
    if videos_path.exists():
        manual_videos = json.loads(videos_path.read_text())
        manual_videos = [v for v in manual_videos if v.get("id") and not v["id"].startswith("YOUR_")]
    else:
        manual_videos = []

    auto_videos = []
    for entry in entries:
        for vid in entry.get("youtube_ids", []):
            meta = fetch_youtube_meta(vid)
            auto_videos.append({
                "id": vid,
                "title": meta.get("title") or "&Aacute;n titils",
                "date": entry["date"],
                "entry_slug": entry["slug"],
                "entry_title": entry["title"],
            })

    seen_ids = set()
    all_videos = []
    for v in list(manual_videos) + auto_videos:
        if v["id"] in seen_ids:
            continue
        seen_ids.add(v["id"])
        all_videos.append(v)
    all_videos.sort(key=lambda v: v.get("date", ""), reverse=True)

    if not all_videos:
        videos_body = '<h2 class="section-heading">Myndbönd</h2>\n<p class="video-empty">Drónamyndefni á leiðinni — fylgist með.</p>'
    else:
        video_items = ""
        for v in all_videos:
            if v.get("entry_slug"):
                location_html = (
                    f' &middot; <a class="video-location" href="{v["entry_slug"]}.html">{v["entry_title"]}</a>'
                )
            elif v.get("location"):
                location_html = f' &middot; <span class="video-location">{v["location"]}</span>'
            else:
                location_html = ""
            date_is = format_date_is(v.get("date", ""))
            video_items += (
                f'<div class="video-item">'
                f'{youtube_iframe(v["id"])}'
                f'<div class="video-info">'
                f'<div class="video-title">{v.get("title", "&Aacute;n titils")}</div>'
                f'<div class="video-meta">{date_is}{location_html}</div>'
                f'</div></div>\n'
            )
        videos_body = f'<h2 class="section-heading">Myndbönd</h2>\n<div class="video-grid">{video_items}</div>'

    videos_page = html_page("Ferðadagbók — Myndbönd", videos_body, active_page="videos.html", wide=True)
    (DOCS_DIR / "videos.html").write_text(videos_page)
    video_count = len(all_videos)

    # Build map data — one pin per location, listing every entry that mentions it
    location_groups = {}
    for entry in entries:
        for loc in entry["resolved_locations"]:
            key = (round(loc["lat"], 4), round(loc["lng"], 4))
            if key not in location_groups:
                location_groups[key] = {
                    "name": loc["name"],
                    "lat": loc["lat"],
                    "lng": loc["lng"],
                    "entries": [],
                }
            if not any(e["slug"] == entry["slug"] for e in location_groups[key]["entries"]):
                location_groups[key]["entries"].append({
                    "title": entry["title"],
                    "date": format_date_is(entry["date"]),
                    "slug": entry["slug"],
                })

    map_markers_json = json.dumps(list(location_groups.values()), ensure_ascii=False)
    entry_locations_json = json.dumps(
        {entry["slug"]: entry["location_keys"] for entry in entries},
        ensure_ascii=False,
    )

    # Homepage: compact hero + sticky map + accordion of entries (newest first)
    entry_count = len(entries)
    image_count = len(seen_srcs)

    accordion_html = "".join(render_entry_row(e) for e in reversed(entries))
    if not accordion_html:
        accordion_html = (
            '<p class="gallery-empty">Engar f&aelig;rslur ennt&thorn;&aacute; '
            '&mdash; &thorn;&aelig;r birtast h&eacute;r eftir &thorn;v&iacute; '
            'sem fer&eth;in &thorn;r&oacute;ast.</p>'
        )

    landing_body = f"""\
<div class="hero-compact">
1. ma&iacute; &ndash; 6. j&uacute;n&iacute; 2026<span class="sep">&middot;</span>{pluralize_is(entry_count, 'f&aelig;rsla', 'f&aelig;rslur')}<span class="sep">&middot;</span>{pluralize_is(image_count, 'mynd', 'myndir')}<span class="sep">&middot;</span>{pluralize_is(video_count, 'myndband', 'myndb&ouml;nd')}
</div>
<div class="dagbok-layout" id="dagbok-layout">
<button type="button" class="map-toggle" id="map-toggle" aria-label="Skipta um sýnileika korts">
<span class="map-toggle-icon" aria-hidden="true">&#x25B8;</span>
<span class="map-toggle-text">Fela kort</span>
</button>
<main class="journal-pane">
<div class="dagbok-accordion">
{accordion_html}
</div>
</main>
<aside class="map-pane">
<div class="map-wrap">
<div id="map" class="map-container"></div>
<div class="map-hint">Smelltu &aacute; punktana til a&eth; opna f&aelig;rslur</div>
</div>
</aside>
</div>"""

    map_script = f"""\
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function() {{
    // --- Leaflet map ---
    var map = L.map('map', {{
        zoomControl: false,
        attributionControl: false
    }});
    window._dagbokMap = map;

    L.control.zoom({{ position: 'bottomright' }}).addTo(map);

    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
        maxZoom: 13
    }}).addTo(map);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
        maxZoom: 13
    }}).addTo(map);

    var markers = {map_markers_json};
    var entryLocations = {entry_locations_json};

    var pinIcon = L.divIcon({{
        className: 'map-pin',
        html: '<div class="pin-dot"></div><div class="pin-pulse"></div>',
        iconSize: [20, 20],
        iconAnchor: [10, 10],
        popupAnchor: [0, -14]
    }});

    var markersByKey = {{}};

    function setKeysClass(keys, cls, on) {{
        keys.forEach(function(k) {{
            var m = markersByKey[k];
            if (!m) return;
            var el = m.getElement();
            if (!el) return;
            el.classList.toggle(cls, !!on);
        }});
    }}

    function entriesAtKey(key) {{
        var slugs = [];
        Object.keys(entryLocations).forEach(function(slug) {{
            if (entryLocations[slug].indexOf(key) !== -1) slugs.push(slug);
        }});
        return slugs;
    }}

    function setRowsClass(slugs, cls, on) {{
        slugs.forEach(function(slug) {{
            var d = document.getElementById(slug);
            if (d) d.classList.toggle(cls, !!on);
        }});
    }}

    function openEntry(slug, scroll) {{
        var d = document.getElementById(slug);
        if (!d) return;
        if (!d.open) d.open = true;
        if (scroll) {{
            // Wait one frame for layout, then scroll
            requestAnimationFrame(function() {{
                d.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }});
        }}
    }}

    markers.forEach(function(loc) {{
        var key = (Math.round(loc.lat * 10000) / 10000) + ',' + (Math.round(loc.lng * 10000) / 10000);
        var marker = L.marker([loc.lat, loc.lng], {{ icon: pinIcon }}).addTo(map);
        var popup = '<div class="popup-title">' + loc.name + '</div>';
        loc.entries.forEach(function(e) {{
            popup += '<a href="#' + e.slug + '" data-slug="' + e.slug + '"><span class="popup-date">' + e.date + '</span> ' + e.title + '</a><br>';
        }});
        marker.bindPopup(popup, {{ maxWidth: 260 }});
        marker.on('click', function() {{
            if (loc.entries.length > 0) openEntry(loc.entries[0].slug, true);
        }});
        marker.on('mouseover', function() {{
            setRowsClass(loc.entries.map(function(e) {{ return e.slug; }}), 'highlighted', true);
        }});
        marker.on('mouseout', function() {{
            setRowsClass(loc.entries.map(function(e) {{ return e.slug; }}), 'highlighted', false);
        }});
        markersByKey[key] = marker;
    }});

    // Wire entry rows → pin highlight + selected state on open
    document.querySelectorAll('.entry-row').forEach(function(row) {{
        var slug = row.id;
        var keys = entryLocations[slug] || [];
        var summary = row.querySelector('summary');

        summary.addEventListener('mouseenter', function() {{
            setKeysClass(keys, 'highlighted', true);
        }});
        summary.addEventListener('mouseleave', function() {{
            setKeysClass(keys, 'highlighted', false);
        }});

        row.addEventListener('toggle', function() {{
            if (row.open) {{
                // Lazy-load any iframes inside this entry
                row.querySelectorAll('iframe[data-src]').forEach(function(f) {{
                    f.src = f.dataset.src;
                    f.removeAttribute('data-src');
                }});
                if (history.replaceState) {{
                    history.replaceState(null, '', '#' + slug);
                }}
                setKeysClass(keys, 'selected', true);
            }} else {{
                setKeysClass(keys, 'selected', false);
                if (location.hash === '#' + slug && history.replaceState) {{
                    history.replaceState(null, '', location.pathname);
                }}
            }}
        }});
    }});

    // Popup links → open entry instead of navigating away
    document.addEventListener('click', function(e) {{
        var a = e.target.closest('.leaflet-popup-content a[data-slug]');
        if (!a) return;
        e.preventDefault();
        var slug = a.getAttribute('data-slug');
        map.closePopup();
        openEntry(slug, true);
    }});

    // Open from URL hash on load + on hashchange
    function openFromHash() {{
        var slug = location.hash.replace(/^#/, '');
        if (slug && document.getElementById(slug)) {{
            openEntry(slug, true);
        }}
    }}
    if (location.hash) requestAnimationFrame(openFromHash);
    window.addEventListener('hashchange', openFromHash);

    // Initial map view
    if (markers.length === 0) {{
        map.setView([-4.5, 115.5], 5);
    }} else if (markers.length === 1) {{
        map.setView([markers[0].lat, markers[0].lng], 7);
    }} else {{
        var bounds = L.latLngBounds(markers.map(function(m) {{ return [m.lat, m.lng]; }}));
        map.fitBounds(bounds, {{ padding: [60, 60], maxZoom: 8 }});
    }}

    // --- Map toggle (open/close map column) ---
    var layout = document.getElementById('dagbok-layout');
    var toggleBtn = document.getElementById('map-toggle');
    var toggleText = toggleBtn ? toggleBtn.querySelector('.map-toggle-text') : null;
    var toggleIcon = toggleBtn ? toggleBtn.querySelector('.map-toggle-icon') : null;
    var STORAGE_KEY = 'dagbok-map-hidden';

    function applyMapHidden(hidden) {{
        if (!layout) return;
        layout.classList.toggle('map-hidden', hidden);
        if (toggleText) toggleText.textContent = hidden ? 'S\\u00FDna kort' : 'Fela kort';
        if (toggleIcon) toggleIcon.innerHTML = hidden ? '&#x25C2;' : '&#x25B8;';
        try {{ localStorage.setItem(STORAGE_KEY, hidden ? '1' : '0'); }} catch (e) {{}}
        if (!hidden) {{
            setTimeout(function() {{ map.invalidateSize(); }}, 360);
        }}
    }}

    if (toggleBtn) {{
        toggleBtn.addEventListener('click', function() {{
            var nowHidden = !layout.classList.contains('map-hidden');
            applyMapHidden(nowHidden);
        }});
    }}

    // Restore saved state (after map fully initialized)
    try {{
        if (localStorage.getItem(STORAGE_KEY) === '1') applyMapHidden(true);
    }} catch (e) {{}}
}})();
</script>"""

    leaflet_css = '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />\n'
    landing_html = html_page(
        "Ferðadagbók",
        landing_body,
        active_page="index.html",
        head_extra=leaflet_css,
        scripts=map_script,
        wide=True,
    )
    (DOCS_DIR / "index.html").write_text(landing_html)

    _save_geocache()
    _save_youtube_cache()
    print(f"Built {len(entries)} entries + gallery + videos + dagbók home → docs/")


if __name__ == "__main__":
    build()
