import json

import pytest

from worker.handlers import url_article
from worker.handlers.exceptions import PermanentHandlerError, TransientHandlerError


def test_is_youtube_classifies_hosts():
    assert url_article.is_youtube("https://youtu.be/abc")
    assert url_article.is_youtube("https://www.youtube.com/watch?v=x")
    assert not url_article.is_youtube("https://example.com/x")


def test_extract_calls_trafilatura(monkeypatch):
    fake = type("F", (), {})()

    def fetch_url(url):
        assert url == "https://example.com/post"
        return "<html>body</html>"

    def extract(html, **kw):
        return "Article body."

    fake.fetch_url = fetch_url
    fake.extract = extract
    monkeypatch.setitem(__import__("sys").modules, "trafilatura", fake)

    payload = json.dumps({"url": "https://example.com/post", "user_note": "n"})
    text, meta, att = url_article.extract(payload)
    assert text == "Article body."
    assert meta["url"] == "https://example.com/post"
    assert meta["user_note"] == "n"
    assert att is None


def test_extract_trafilatura_empty_fetch_transient(monkeypatch):
    fake = type("F", (), {})()
    fake.fetch_url = lambda url: None
    fake.extract = lambda *a, **kw: ""
    monkeypatch.setitem(__import__("sys").modules, "trafilatura", fake)
    with pytest.raises(TransientHandlerError):
        url_article.extract(json.dumps({"url": "https://example.com"}))


def test_extract_trafilatura_empty_extract_permanent(monkeypatch):
    fake = type("F", (), {})()
    fake.fetch_url = lambda url: "<html/>"
    fake.extract = lambda html, **kw: ""
    monkeypatch.setitem(__import__("sys").modules, "trafilatura", fake)
    with pytest.raises(PermanentHandlerError):
        url_article.extract(json.dumps({"url": "https://example.com"}))


def test_extract_youtube_dispatches(monkeypatch):
    called = {}

    def fake_yt_extract(payload, **kw):
        called["yes"] = True
        return "transcript", {"url": json.loads(payload)["url"]}, None

    monkeypatch.setattr(url_article.url_youtube, "extract", fake_yt_extract)
    text, meta, att = url_article.extract(
        json.dumps({"url": "https://youtu.be/abc", "user_note": "watch"})
    )
    assert text == "transcript"
    assert called["yes"]
    assert meta["user_note"] == "watch"


def test_extract_missing_url_permanent():
    with pytest.raises(PermanentHandlerError):
        url_article.extract(json.dumps({}))
