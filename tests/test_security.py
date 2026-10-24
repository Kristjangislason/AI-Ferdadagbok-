from html.parser import HTMLParser
import pytest

import build_site
import process_journal
from content_security import validate_slug


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def entry(tmp_path, content, metadata=""):
    path = tmp_path / "2026-01-01-test.md"
    path.write_text("---\ntitle: Test\ndate: 2026-01-01\n" + metadata + "---\n\n" + content)
    return path


@pytest.mark.parametrize("content", [
    '<a href="javascript:alert(1)">click</a>',
    '<a href="jav&#x61;script:alert(1)">click</a>',
    "<p onclick='alert(1)'>click</p>",
    '<svg onload=alert(1)></svg>',
    '<iframe srcdoc="&lt;script&gt;alert(1)&lt;/script&gt;"></iframe>',
    '<img src="x" ONERROR=alert(1)>',
    '<a href="data:text/html,hello">click</a>',
])
def test_entry_removes_active_html(tmp_path, content):
    html = build_site.parse_entry(entry(tmp_path, content))["body_html"]
    for tag, attrs in Elements(html).elements:
        assert tag not in {"script", "svg", "iframe", "object", "style"}
        assert not any(key.lower().startswith("on") for key in attrs)
        assert not any(value.lower().startswith(("javascript:", "data:")) for value in attrs.values())


def test_entry_keeps_formatting_images_links_and_validated_video(tmp_path):
    parsed = build_site.parse_entry(entry(tmp_path,
        '**Bold** and <u>underlined</u>. [Link](https://example.com)\n\n'
        '![A & B](../images/photo.jpg)\n\n<!--youtube:dQw4w9WgXcQ-->'))
    assert '<strong>Bold</strong>' in parsed["body_html"]
    assert '<u>underlined</u>' in parsed["body_html"]
    assert '<figcaption>A &amp; B</figcaption>' in parsed["body_html"]
    assert 'src="images/photo.jpg"' in parsed["body_html"]
    assert 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ' in parsed["body_html"]
    assert parsed["youtube_ids"] == ["dQw4w9WgXcQ"]


@pytest.mark.parametrize("slug", ["../outside", "/tmp/outside", "..", "x/y", "x\\y", "", 'x"onclick="bad'])
def test_rejects_unsafe_slugs(slug):
    with pytest.raises(ValueError):
        validate_slug(slug)


def test_invalid_slug_does_not_replace_existing_output(tmp_path, monkeypatch):
    entries = tmp_path / "entries"
    entries.mkdir()
    entry(entries, "body", "slug: ../outside\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    marker = docs / "index.html"
    marker.write_text("previous site")
    monkeypatch.setattr(build_site, "ENTRIES_DIR", entries)
    monkeypatch.setattr(build_site, "DOCS_DIR", docs)
    with pytest.raises(ValueError):
        build_site.build()
    assert marker.read_text() == "previous site"
    assert not (tmp_path / "outside.html").exists()


def test_title_cannot_inject_front_matter():
    date, title = process_journal.parse_title_and_date(
        "Title\nslug: ../outside\r\n---", {"created_time": "2026-01-01T00:00:00Z"})
    assert date == "2026-01-01"
    assert "\n" not in title and "\r" not in title


def test_date_output_is_escaped():
    html = build_site.render_entry_row({"slug": "test", "title": "Test", "body_html": "", "date": "<img onerror=bad>"})
    assert '<img' not in html


@pytest.mark.parametrize("video_id", ['bad" onload="bad', "../bad", "not-an-id"])
def test_youtube_iframe_rejects_invalid_ids(video_id):
    with pytest.raises(ValueError):
        build_site.youtube_iframe(video_id)


@pytest.mark.parametrize("url", [
    "http://images.unsplash.com/photo.jpg", "https://127.0.0.1/photo.jpg",
    "https://169.254.169.254/latest/meta-data/", "file:///etc/passwd",
    "https://images.unsplash.com.attacker.example/photo.jpg",
    "https://user:password@images.unsplash.com/photo.jpg",
    "https://images.unsplash.com:8443/photo.jpg",
])
def test_image_urls_are_restricted(url, monkeypatch):
    monkeypatch.delenv("IMAGE_DOWNLOAD_HOSTS", raising=False)
    with pytest.raises(ValueError):
        process_journal.validate_image_url(url)


class Response:
    def __init__(self, data=b"\xff\xd8\xffimage", redirect=None):
        self.data = data
        self.is_redirect = redirect is not None
        self.headers = {"Location": redirect} if redirect else {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield self.data


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.trust_env = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def test_redirect_is_checked_before_request(monkeypatch):
    session = Session([Response(redirect="https://169.254.169.254/metadata")])
    monkeypatch.setattr(process_journal.requests, "Session", lambda: session)
    with pytest.raises(ValueError):
        process_journal.fetch_image_bytes("https://images.unsplash.com/photo.jpg")
    assert len(session.calls) == 1
    assert session.trust_env is False
    assert session.calls[0][1]["allow_redirects"] is False


@pytest.mark.parametrize("data,limit", [(b"<html>not an image</html>", 100), (b"\xff\xd8\xfftoolarge", 3)])
def test_bad_download_is_never_written(tmp_path, monkeypatch, data, limit):
    monkeypatch.setattr(process_journal, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(process_journal, "MAX_IMAGE_BYTES", limit)
    monkeypatch.setattr(process_journal.requests, "Session", lambda: Session([Response(data)]))
    with pytest.raises(ValueError):
        process_journal.download_image("https://images.unsplash.com/photo.jpg")
    assert list(tmp_path.iterdir()) == []


def test_valid_download_and_cache(tmp_path, monkeypatch):
    data = b"\xff\xd8\xffimage"
    session = Session([Response(data)])
    monkeypatch.setattr(process_journal, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(process_journal.requests, "Session", lambda: session)
    filename = process_journal.download_image("https://images.unsplash.com/photo.jpg", "2026-01-01-")
    assert (tmp_path / filename).read_bytes() == data
    assert process_journal.download_image("https://images.unsplash.com/photo.jpg", "2026-01-01-") == filename
    assert len(session.calls) == 1


def exif_image(tiff):
    segment = b"Exif\x00\x00" + tiff
    return b"\xff\xd8\xff\xe1" + (len(segment) + 2).to_bytes(2, "big") + segment + b"\xff\xd9"


def test_exif_rejects_out_of_bounds_rational_count(tmp_path):
    import struct
    # IFD0 points at a GPS IFD with a count larger than the available bytes.
    tiff = b"II" + struct.pack("<HI", 42, 8)
    tiff += struct.pack("<H", 1) + struct.pack("<HHII", 0x8825, 4, 1, 26) + b"\x00" * 4
    tiff += struct.pack("<H", 1) + struct.pack("<HHII", 2, 5, 0xffffffff, 44) + b"\x00" * 4
    image = tmp_path / "malformed.jpg"
    image.write_bytes(exif_image(tiff))
    assert build_site._read_jpeg_exif_gps(image) == (None, None)


@pytest.mark.parametrize("data", [b"\xff\xd8\xff\xe1\x00\x01x", exif_image(b"II\x2a\x00\xff\xff\xff\xff")])
def test_exif_rejects_invalid_segment_or_ifd_offset(tmp_path, data):
    image = tmp_path / "malformed.jpg"
    image.write_bytes(data)
    assert build_site._read_jpeg_exif_gps(image) == (None, None)


def test_exif_preserves_valid_gps(tmp_path):
    import struct
    tiff = b"II" + struct.pack("<HI", 42, 8)
    tiff += struct.pack("<H", 1) + struct.pack("<HHII", 0x8825, 4, 1, 26) + b"\x00" * 4
    tiff += struct.pack("<H", 4)
    tiff += struct.pack("<HHI", 1, 2, 2) + b"N\x00\x00\x00"
    tiff += struct.pack("<HHII", 2, 5, 3, 80)
    tiff += struct.pack("<HHI", 3, 2, 2) + b"W\x00\x00\x00"
    tiff += struct.pack("<HHII", 4, 5, 3, 104) + b"\x00" * 4
    tiff += struct.pack("<IIIIII", 64, 1, 0, 1, 0, 1)
    tiff += struct.pack("<IIIIII", 21, 1, 0, 1, 0, 1)
    image = tmp_path / "valid.jpg"
    image.write_bytes(exif_image(tiff))
    assert build_site._read_jpeg_exif_gps(image) == (64.0, -21.0)
