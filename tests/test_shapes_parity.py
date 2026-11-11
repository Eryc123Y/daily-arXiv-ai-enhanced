"""The record shapes in summaries/shapes.py and js/types.js name the same fields.

The pipeline writes the records and the page reads them, so a field added on
one side only is a contract the other side does not know about. Each shape
that crosses the data branch is paired below; shapes that stay on one side
are listed as such, so a new shape must be placed before the test passes.
"""

import re
from pathlib import Path
from typing import is_typeddict

from summaries import shapes

TYPES_JS = Path(__file__).resolve().parent.parent / "js" / "types.js"

# Python TypedDict -> JS @typedef for the records on the data branch.
PAIRS = {
    "AISummary": "AiSummary",
    "ArxivRecord": "ArxivRecord",
    "FeedRecord": "VenueRecord",
    "VenueSummary": "VenueSummary",
}

# Pipeline-only shapes (feed command output, cursor, full watch list).
PYTHON_ONLY = {"FeedLine", "FeedCursor", "Venue"}
# Page-only shapes, derived in the browser (Sources.venueIndex, Streams.venueGroups).
JS_ONLY = {"VenueInfo", "VenueGroup"}

# Fields one side models differently: Python puts the summary file's `AI`
# on the record; js/types.js adds it in `SummaryRecord` and `PageRecord`.
NOT_COMPARED = {"ArxivRecord": {"AI"}}

TYPEDEF = re.compile(r"@typedef \{object\} (\w+)(.*?)\*/", re.DOTALL)
PROPERTY = re.compile(r"@property \{[^}]*\} \[?(\w+)\]?")


def js_shapes(text: str) -> dict[str, set[str]]:
    """Each `@typedef {object}` in the text with its `@property` names."""
    return {name: set(PROPERTY.findall(body)) for name, body in TYPEDEF.findall(text)}


def python_shapes() -> dict[str, set[str]]:
    return {
        name: set(value.__required_keys__ | value.__optional_keys__)
        for name, value in vars(shapes).items()
        if is_typeddict(value)
    }


def test_the_parser_reads_optional_and_required_properties():
    text = """
/**
 * @typedef {object} Thing
 * @property {string} id      the key
 * @property {string | null} [note]
 */"""
    assert js_shapes(text) == {"Thing": {"id", "note"}}


def test_every_shape_is_paired_or_marked_one_sided():
    assert set(python_shapes()) == set(PAIRS) | PYTHON_ONLY
    assert set(js_shapes(TYPES_JS.read_text())) == set(PAIRS.values()) | JS_ONLY


def test_paired_shapes_name_the_same_fields():
    python, js = python_shapes(), js_shapes(TYPES_JS.read_text())
    for py_name, js_name in PAIRS.items():
        skip = NOT_COMPARED.get(py_name, set())
        only_python = python[py_name] - js[js_name] - skip
        only_js = js[js_name] - python[py_name] - skip
        assert not only_python, f"{py_name} has {sorted(only_python)} that js/types.js {js_name} lacks"
        assert not only_js, f"js/types.js {js_name} has {sorted(only_js)} that shapes.py {py_name} lacks"
