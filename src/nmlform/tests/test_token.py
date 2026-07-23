"""Tests for :class:`nmlform.token.Token`."""

from __future__ import annotations

import pytest

from ..comments import Comments
from ..location import Location
from ..token import Delimiter, Token


def test_default_location_spans_content() -> None:
    token = Token("abc")
    assert token.loc == Location(end_column=3)


def test_explicit_location_kept() -> None:
    loc = Location(line=2, column=4, end_line=2, end_column=7)
    assert Token("abc", loc=loc).loc == loc


@pytest.mark.parametrize(
    "a, b",
    [
        ("abc", "abc"),
        ("abc", "ABC"),
        ("ABC", "abc"),
        ("MiXeD", "mIxEd"),
    ],
)
def test_eq_case_insensitive(a: str, b: str) -> None:
    assert Token(a) == Token(b)
    assert Token(a) == b
    assert not Token(a) != Token(b)


@pytest.mark.parametrize(
    "a, b",
    [
        ("abc", "abd"),
        ("abc", "abcd"),
        ("", "a"),
    ],
)
def test_ne(a: str, b: str) -> None:
    assert Token(a) != Token(b)
    assert Token(a) != b


def test_eq_non_string() -> None:
    assert Token("1") != 1
    assert Token("1") != None  # noqa: E711


def test_eq_ignores_location() -> None:
    loc = Location(line=5, column=1, end_line=5, end_column=4)
    assert Token("abc", loc=loc) == Token("abc")


def test_eq_empty_comments_matches_no_comments() -> None:
    assert Token("abc", comments=Comments()) == Token("abc")
    assert Token("abc") == Token("abc", comments=Comments())


def test_eq_compares_comments() -> None:
    commented = Token("abc", comments=Comments(inline=Token("note")))
    assert commented != Token("abc")
    assert Token("abc") != commented
    assert commented == Token("ABC", comments=Comments(inline=Token("note")))
    assert commented != Token("abc", comments=Comments(inline=Token("other")))


def test_hash_matches_plain_str() -> None:
    assert hash(Token("abc")) == hash("ABC")
    assert {"ABC": 1}[Token("abc")] == 1


@pytest.mark.parametrize(
    "content, quoted",
    [
        ("'abc'", True),
        ('"abc"', True),
        ("''", True),
        ("abc", False),
        ("'abc", False),
        ("abc'", False),
        ("'abc\"", False),
        ("", False),
    ],
)
def test_is_quoted_string(content: str, quoted: bool) -> None:
    assert Token(content).is_quoted_string is quoted


@pytest.mark.parametrize("content", ["'abc'", '"abc"'])
def test_remove_quotes(content: str) -> None:
    loc = Location(line=1, end_line=1, end_column=5)
    unquoted = Token(content, loc=loc).remove_quotes()
    assert str(unquoted) == "abc"
    assert unquoted.loc == loc


def test_remove_quotes_unquoted_returns_self() -> None:
    token = Token("abc")
    assert token.remove_quotes() is token


def test_comments_created_lazily() -> None:
    token = Token("abc")
    assert token._comments is None
    assert token.comments == Comments()
    assert token._comments is not None
    assert token.comments is token._comments


def test_comments_setter() -> None:
    token = Token("abc")
    comments = Comments(inline=Token("note"))
    token.comments = comments
    assert token.comments is comments


@pytest.mark.parametrize(
    "method, args, expected",
    [
        ("lstrip", (), "abc  "),
        ("strip", (), "abc"),
        ("lstrip", (" a",), "bc  "),
        ("strip", (" c",), "ab"),
        ("replace", ("b", "x"), "  axc  "),
        ("upper", (), "  ABC  "),
        ("lower", (), "  abc  "),
    ],
)
def test_str_methods_preserve_token(method: str, args: tuple, expected: str) -> None:
    loc = Location(line=3, end_line=3, end_column=7)
    comments = Comments(inline=Token("note"))
    token = Token("  abc  ", loc=loc, comments=comments)
    result = getattr(token, method)(*args)
    assert type(result) is Token
    assert str(result) == expected
    assert result.loc == loc
    assert result._comments is comments


def test_replace_count() -> None:
    assert str(Token("aaa").replace("a", "b", 2)) == "bba"


def test_with_() -> None:
    token = Token("abc")
    loc = Location(line=1, end_line=1, end_column=3)
    comments = Comments(inline=Token("note"))
    updated = token.with_(loc=loc, comments=comments)
    assert str(updated) == "abc"
    assert updated.loc == loc
    assert updated._comments is comments
    # Omitted fields fall back to the original's.
    assert updated.with_(loc=None)._comments is comments
    assert updated.with_(comments=None).loc == loc


def test_repr() -> None:
    token = Token("abc", loc=Location(line=0, end_line=0, end_column=3))
    assert repr(token).startswith("Token('abc'")
    assert "abc" in repr(token)


def test_repr_without_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Token, "_detailed_repr_", False)
    token = Token("abc", loc=Location(line=3, end_line=3, end_column=6))
    assert repr(token) == "Token('abc')"


def test_repr_with_comments() -> None:
    token = Token("abc", comments=Comments(inline=Token("note")))
    assert "note" in repr(token)


def test_delimiter_methods_preserve_subclass() -> None:
    delim = Delimiter(" , ")
    assert type(delim.strip()) is Delimiter
    assert type(delim.upper()) is Delimiter
    assert delim.strip() == ","
