"""Tests for :class:`nmlform.location.Location`."""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest

from ..location import Location
from ..token import Token


def test_add_merges_spans() -> None:
    a = Location(line=0, column=2, end_line=0, end_column=5)
    b = Location(line=1, column=0, end_line=1, end_column=3)
    merged = Location(line=0, column=2, end_line=1, end_column=3)
    assert a + b == merged
    assert b + a == merged


def test_add_non_location_raises() -> None:
    with pytest.raises(ValueError):
        Location() + "abc"


def test_from_items_merges_locations_and_loc_attributes() -> None:
    loc = Location(line=0, column=2, end_line=0, end_column=5)
    token = Token("abc", loc=Location(line=2, column=0, end_line=2, end_column=3))
    merged = Location.from_items([None, loc, token])
    assert merged == Location(line=0, column=2, end_line=2, end_column=3)


def test_from_items_takes_first_filename() -> None:
    filename = pathlib.Path("a.nml")
    loc = Location(filename=filename, line=1, column=0, end_line=1, end_column=4)
    merged = Location.from_items([loc, Location(line=0, column=0, end_line=0, end_column=2)])
    assert merged.filename == filename


@pytest.mark.parametrize(
    "items",
    [
        [],
        [None],
        [SimpleNamespace(loc=None)],
    ],
)
def test_from_items_without_locations_raises(items: list) -> None:
    with pytest.raises(ValueError):
        Location.from_items(items)


@pytest.mark.parametrize(
    "loc, expected",
    [
        # Single point: line:column only.
        (Location(line=0, column=0, end_line=0, end_column=1), "None:1:1"),
        # Span within one line.
        (Location(line=0, column=0, end_line=0, end_column=3), "None:1:1-3"),
        # Span across lines.
        (Location(line=0, column=0, end_line=2, end_column=5), "None:1:1-3:5"),
        (
            Location(filename=pathlib.Path("x.nml"), line=0, column=0, end_line=0, end_column=1),
            "x.nml:1:1",
        ),
    ],
)
def test_str(loc: Location, expected: str) -> None:
    assert str(loc) == expected
