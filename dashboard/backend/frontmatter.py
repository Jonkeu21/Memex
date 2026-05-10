"""Lightweight YAML front-matter reader / mutator for vault notes.

The worker writes front-matter via ``worker/vault_writer.py``; the dashboard
only ever reads it (for the inbox + captures browsers) and clears the
``needs_review`` flag when an inbox item is routed to a real folder. We do
not re-render the entire front-matter from scratch on mutation — that risks
losing fields the worker may add in a future contract revision. Instead, we
patch values in place with a focused regex-aware replacement.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_FENCE = "---\n"


@dataclass
class ParsedNote:
    front_matter: dict[str, Any]
    body: str
    raw_front_matter: str  # the YAML between the fences, no fences
    has_front_matter: bool


def parse_text(text: str) -> ParsedNote:
    if not text.startswith("---"):
        return ParsedNote({}, text, "", has_front_matter=False)
    # Find the closing fence; allow the file to start with "---\n" or "---\r\n".
    after_open = text.split("\n", 1)
    if len(after_open) != 2:
        return ParsedNote({}, text, "", has_front_matter=False)
    rest = after_open[1]
    if "\n---\n" not in rest and not rest.startswith("---\n"):
        # Could still be a doc that starts with "---\n---\n..." — check that
        # case explicitly.
        if rest.startswith("---\n"):
            yaml_block = ""
            body = rest[len("---\n"):]
        elif rest.endswith("\n---") or rest == "---":
            yaml_block = rest[: -len("---")] if rest.endswith("---") else ""
            body = ""
        else:
            return ParsedNote({}, text, "", has_front_matter=False)
    else:
        yaml_block, _, body = rest.partition("\n---\n")
    try:
        loaded = yaml.safe_load(yaml_block) if yaml_block.strip() else {}
    except yaml.YAMLError:
        return ParsedNote({}, text, "", has_front_matter=False)
    if not isinstance(loaded, dict):
        loaded = {}
    return ParsedNote(
        front_matter=loaded,
        body=body,
        raw_front_matter=yaml_block,
        has_front_matter=True,
    )


def parse_file(path: Path) -> ParsedNote:
    return parse_text(path.read_text(encoding="utf-8"))


def patch_field(text: str, field: str, new_value: Any) -> str:
    """Replace ``<field>: ...`` inside the front-matter, preserving everything else.

    If the field is absent, it is appended just before the closing ``---`` line.
    Only handles scalar / boolean / numeric / quoted-string values; lists and
    nested mappings should be patched by re-rendering the whole front-matter.
    """
    parsed = parse_text(text)
    if not parsed.has_front_matter:
        # Cannot patch a note that has no front-matter. Caller should produce one.
        raise ValueError("note has no front-matter to patch")
    rendered_value = _render_scalar(new_value)
    lines = parsed.raw_front_matter.split("\n")
    field_prefix = f"{field}:"
    replaced = False
    new_lines: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if not replaced and stripped.startswith(field_prefix):
            indent = line[: len(line) - len(stripped)]
            new_lines.append(f"{indent}{field}: {rendered_value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        # Append at the bottom of the front-matter block.
        if new_lines and new_lines[-1] == "":
            new_lines.insert(-1, f"{field}: {rendered_value}")
        else:
            new_lines.append(f"{field}: {rendered_value}")
    new_yaml = "\n".join(new_lines)
    return f"---\n{new_yaml}\n---\n{parsed.body}"


def _render_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if s == "" or s in {"null", "true", "false"} or s != s.strip():
        return f'"{s}"'
    if any(ch in s for ch in (":", "#", "\n", "[", "]", "{", "}", ",")):
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s
