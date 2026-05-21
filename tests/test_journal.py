from process_journal import slugify, extract_youtube_id, rich_text_to_md, md_escape


def test_slugify_icelandic():
    assert slugify("Báturinn Prince 5-8 maí") == "baturinn-prince-5-8-mai"


def test_extract_youtube_query_url():
    assert extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=20s") == "dQw4w9WgXcQ"


def test_rich_text_formatting_and_escape():
    rt = [{"plain_text": "A&B [x]", "annotations": {"bold": True}, "href": "https://example.com"}]
    out = rich_text_to_md(rt)
    assert "[**A&B" in out
    assert "https://example.com" in out
    assert md_escape("[]()") == "\\[\\]\\(\\)"
