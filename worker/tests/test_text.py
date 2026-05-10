import json
from worker.handlers import text


def test_text_passthrough():
    out, meta, att = text.extract(json.dumps({"text": "hello"}))
    assert out == "hello"
    assert meta == {"length": 5}
    assert att is None


def test_text_missing_field_defaults():
    out, meta, _ = text.extract(json.dumps({}))
    assert out == ""
    assert meta == {"length": 0}


def test_text_non_string_coerced():
    out, _, _ = text.extract(json.dumps({"text": 123}))
    assert out == "123"
