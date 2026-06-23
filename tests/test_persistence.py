"""Tests for the shared persistence helpers (app/persistence.py)."""

from __future__ import annotations

import json
import re

import pytest

from app.persistence import (
    dumps_canonical,
    iter_jsonl,
    read_json,
    utc_now_iso,
    write_json_atomic,
)


def test_utc_now_iso_format():
    value = utc_now_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value)


def test_dumps_canonical_is_sorted_and_unicode_preserving():
    text = dumps_canonical({"b": 1, "a": "café"})
    # Keys sorted, non-ASCII preserved (ensure_ascii=False), two-space indent.
    assert text == '{\n  "a": "café",\n  "b": 1\n}'


def test_write_json_atomic_round_trip_and_trailing_newline(tmp_path):
    target = tmp_path / "nested" / "out.json"
    payload = {"z": [3, 2, 1], "a": "value"}

    returned = write_json_atomic(target, payload)

    assert returned == target
    raw = target.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert raw == dumps_canonical(payload) + "\n"
    assert read_json(target) == payload


def test_write_json_atomic_overwrites_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "out.json"
    write_json_atomic(target, {"v": 1})
    write_json_atomic(target, {"v": 2})

    assert read_json(target) == {"v": 2}
    # The temp file (".out.json.*.tmp") must be replaced, not left behind.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "out.json"]
    assert leftovers == []


def test_write_json_atomic_failure_cleans_up_temp(tmp_path):
    target = tmp_path / "out.json"

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        write_json_atomic(target, {"bad": Unserializable()})

    # No artifact and no stray temp file should remain after a failed write.
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_iter_jsonl_skips_blank_lines(tmp_path):
    path = tmp_path / "records.jsonl"
    path.write_text(
        json.dumps({"i": 1}) + "\n\n" + json.dumps({"i": 2}) + "\n",
        encoding="utf-8",
    )
    assert list(iter_jsonl(path)) == [{"i": 1}, {"i": 2}]


def test_iter_jsonl_raises_on_malformed_line(tmp_path):
    path = tmp_path / "records.jsonl"
    path.write_text('{"ok": 1}\nnot json\n', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        list(iter_jsonl(path))
