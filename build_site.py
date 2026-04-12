"""
Build a minimal static blog from Markdown journal entries.
Reads entries/ and outputs a complete site to docs/.
"""

import re
import shutil
from pathlib import Path

import markdown

ENTRIES_DIR = Path(__file__).parent / "entries"
DOCS_DIR = Path(__file__).parent / "docs"

BASE_STYLE = """\
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --text: #1d1d1f;
    --muted: #6e6e73;
    --bg: #fff;
    --max-width: 640px;
}

body {
    font-family: 'Iowan Old Style', 'Palatino Linotype', Palatino, Georgia, serif;
    color: var(--text);
    background: var(--bg);
    line-height: 1.9;
    font-size: 18px;
    -webkit-font-smoothing: antialiased;
}

.container {
    max-width: var(--max-width);
    margin: 0 auto;
    padding: 80px 24px;
}

header {
    margin-bottom: 80px;
}

header a {
    text-decoration: none;
    color: inherit;
}

header h1 {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: var(--text);
}

header p {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 13px;
    color: var(--muted);
    margin-top: 4px;
}

article h1 {
    font-size: 32px;
    line-height: 1.3;
    margin-bottom: 40px;
    letter-spacing: -0.01em;
}

article p {
    margin-bottom: 24px;
}

.entry-list {
    list-style: none;
}

.entry-list li {
    margin-bottom: 32px;
}

.entry-list a {
    text-decoration: none;
    color: var(--text);
    display: block;
}

.entry-list a:hover .entry-title {
    color: var(--muted);
}

.entry-title {
    font-size: 22px;
    line-height: 1.4;
    transition: color 0.2s;
}

.entry-date {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 13px;
    color: var(--muted);
    margin-top: 4px;
}

nav.back {
    margin-bottom: 60px;
}

nav.back a {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 14px;
    color: var(--muted);
    text-decoration: none;
}

nav.back a:hover {
    color: var(--text);
}

@media (max-width: 600px) {
    .container { padding: 48px 20px; }
    header { margin-bottom: 48px; }
    article h1 { font-size: 26px; margin-bottom: 32px; }
    .entry-title { font-size: 19px; }
}
"""


def html_page(title, body, is_index=False):
    back_nav = "" if is_index else '<nav class="back"><a href="index.html">&larr; Back</a></nav>'
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{BASE_STYLE}</style>
</head>
<body>
<div class="container">
<header><a href="index.html"><h1>Fer&eth;adagb&oacute;k</h1><p>Indonesia 2025</p></a></header>
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
    date_match = re.match(r"(\d{4}-\d{2}-\d{2})", filepath.name)
    date_str = date_match.group(1) if date_match else filepath.name[:10]

    # Convert to HTML (skip the title line, we render it separately)
    body_md = text[title_match.end():].strip() if title_match else text
    body_html = markdown.markdown(body_md)

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

    # Gather and sort entries by filename (date)
    entry_files = sorted(ENTRIES_DIR.glob("*.md"))
    entries = [parse_entry(f) for f in entry_files]

    # Build individual entry pages
    for entry in entries:
        body = f'<article><h1>{entry["title"]}</h1><div class="entry-date">{entry["date"]}</div>{entry["body_html"]}</article>'
        page = html_page(entry["title"], body)
        (DOCS_DIR / f'{entry["slug"]}.html').write_text(page)

    # Build index
    items = ""
    for entry in reversed(entries):  # newest first
        items += (
            f'<li><a href="{entry["slug"]}.html">'
            f'<div class="entry-title">{entry["title"]}</div>'
            f'<div class="entry-date">{entry["date"]}</div>'
            f'</a></li>\n'
        )
    index_body = f'<ul class="entry-list">{items}</ul>'
    index_page = html_page("Ferðadagbók", index_body, is_index=True)
    (DOCS_DIR / "index.html").write_text(index_page)

    print(f"Built {len(entries)} entries → docs/")


if __name__ == "__main__":
    build()
