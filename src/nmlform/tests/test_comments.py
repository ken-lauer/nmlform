"""Tests for :class:`nmlform.comments.Comments`."""

from __future__ import annotations

from ..comments import Comments
from ..token import Token


def test_bool() -> None:
    assert not Comments()
    assert Comments(pre=[Token("a")])
    assert Comments(inline=Token("a"))


def test_clear() -> None:
    comments = Comments(pre=[Token("a")], inline=Token("b"))
    comments.clear()
    assert comments == Comments()
    assert not comments


def test_clone_copies_pre_list() -> None:
    original = Comments(pre=[Token("a")], inline=Token("b"))
    clone = original.clone()
    assert clone == original
    clone.pre.append(Token("c"))
    assert original.pre == [Token("a")]


def test_repr() -> None:
    assert repr(Comments()) == "Comments()"
    assert "pre=" in repr(Comments(pre=[Token("a")]))
    assert "inline=" in repr(Comments(inline=Token("b")))
