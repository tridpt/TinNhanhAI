"""Tests for news RSS thumbnail extraction."""

from __future__ import annotations


def _entry(**kwargs):
    """Build a feedparser-like entry object supporting .get and attribute access."""

    data = {
        "title": "",
        "summary": "",
        "link": "",
        "enclosures": [],
    }
    data.update(kwargs)

    class Entry(dict):
        def __getattr__(self, name):
            return self.get(name)

    return Entry(data)


def test_thumbnail_from_enclosure():
    from services.news import _extract_thumbnail

    entry = _entry(enclosures=[{"href": "https://img.com/a.jpg", "type": "image/jpeg"}])
    assert _extract_thumbnail(entry) == "https://img.com/a.jpg"


def test_thumbnail_from_media_content():
    from services.news import _extract_thumbnail

    entry = _entry(media_content=[{"url": "https://img.com/b.png"}])
    assert _extract_thumbnail(entry) == "https://img.com/b.png"


def test_thumbnail_from_img_in_description():
    from services.news import _extract_thumbnail

    entry = _entry(summary='<p>Text <img src="https://img.com/c.webp" /></p>')
    assert _extract_thumbnail(entry) == "https://img.com/c.webp"


def test_thumbnail_none_when_absent():
    from services.news import _extract_thumbnail

    entry = _entry(summary="Plain text with no image")
    assert _extract_thumbnail(entry) == ""


def test_thumbnail_skips_non_image_enclosure():
    from services.news import _extract_thumbnail

    entry = _entry(
        enclosures=[{"href": "https://site.com/audio.mp3", "type": "audio/mpeg"}],
        media_content=[{"url": "https://img.com/fallback.jpg"}],
    )
    # Audio enclosure ignored, falls through to media_content.
    assert _extract_thumbnail(entry) == "https://img.com/fallback.jpg"
