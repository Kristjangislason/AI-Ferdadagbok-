from pathlib import Path

import build_site
from build_site import lazyfy_iframes, parse_entry, youtube_iframe


def test_youtube_iframe_privacy_domain_and_title():
    html = youtube_iframe("dQw4w9WgXcQ", "Test")
    assert "youtube-nocookie.com" in html
    assert 'title="Test"' in html


def test_lazy_iframe():
    html = '<iframe src="https://x"></iframe>'
    assert 'data-src=' in lazyfy_iframes(html)


def test_parse_entry_front_matter_strips_metadata_and_keeps_human_title(tmp_path):
    md = tmp_path / "2026-05-20-bad-13-16-mai.md"
    md.write_text(
        """---
title: Bað (13.-16. maí)
date: 2026-05-20
notion_page_id: abc
slug: 2026-05-20-bad-13-16-mai
created_time: 2026-05-20T13:12:00.000Z
last_edited_time: 2026-05-21T00:00:00.000Z
---

Dagbókartexti.
""",
        encoding="utf-8",
    )

    parsed = parse_entry(md)

    assert parsed["title"] == "Bað (13.-16. maí)"
    assert parsed["date"] == "2026-05-20"
    assert parsed["slug"] == "2026-05-20-bad-13-16-mai"
    assert "notion_page_id:" not in parsed["body_html"]
    assert "created_time:" not in parsed["body_html"]
    assert "last_edited_time:" not in parsed["body_html"]
    assert "slug:" not in parsed["body_html"]
    assert "---" not in parsed["body_html"]
    assert "Dagbókartexti." in parsed["body_html"]


def test_build_homepage_uses_human_titles_and_hides_front_matter(tmp_path, monkeypatch):
    entries_dir = tmp_path / "entries"
    images_dir = tmp_path / "images"
    docs_dir = tmp_path / "docs"
    entries_dir.mkdir()
    images_dir.mkdir()

    (entries_dir / "2026-05-20-bad-13-16-mai.md").write_text(
        """---
title: Bað (13.-16. maí)
date: 2026-05-20
slug: 2026-05-20-bad-13-16-mai
notion_page_id: abc
created_time: 2026-05-20T13:12:00.000Z
last_edited_time: 2026-05-20T13:40:00.000Z
---

Texti.
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(build_site, "ENTRIES_DIR", entries_dir)
    monkeypatch.setattr(build_site, "IMAGES_DIR", images_dir)
    monkeypatch.setattr(build_site, "DOCS_DIR", docs_dir)

    build_site.build()

    index = (docs_dir / "index.html").read_text(encoding="utf-8")
    assert "Bað (13.-16. maí)" in index
    assert "2026-05-20-bad-13-16-mai" in index
    assert "notion_page_id:" not in index
    assert "created_time:" not in index
    assert "last_edited_time:" not in index
    assert "slug:" not in index
    assert "\n---\n" not in index
