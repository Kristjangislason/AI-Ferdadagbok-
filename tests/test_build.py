from build_site import youtube_iframe, lazyfy_iframes


def test_youtube_iframe_privacy_domain_and_title():
    html = youtube_iframe("dQw4w9WgXcQ", "Test")
    assert "youtube-nocookie.com" in html
    assert 'title="Test"' in html


def test_lazy_iframe():
    html = '<iframe src="https://x"></iframe>'
    assert 'data-src=' in lazyfy_iframes(html)
