from __future__ import annotations

import typing
from typing import Any, ClassVar, SupportsIndex

from .comments import Comments
from .location import Location

if typing.TYPE_CHECKING:
    try:
        from typing import Self
    except ImportError:
        from typing_extensions import Self


class Token(str):
    """
    String with source loc information.

    Comparisons are case-insensitive.
    """

    __slots__ = ("_comments", "_hash", "_upper", "loc")
    loc: Location
    _comments: Comments | None
    _upper: str
    _hash: int

    _detailed_repr_: ClassVar[bool] = True

    def __new__(
        cls,
        content: str,
        loc: Location | None = None,
        comments: Comments | None = None,
    ):
        return super().__new__(cls, content)

    def __init__(
        self,
        content: str,
        loc: Location | None = None,
        comments: Comments | None = None,
    ):
        self.loc = loc or Location(end_column=len(content))
        self._comments = comments
        self._upper = str.upper(self)

    def __eq__(self, other) -> bool:
        if isinstance(other, Token):
            if self._upper != other._upper:
                return False
            ours, theirs = self._comments, other._comments
            if not ours:
                return not theirs
            if not theirs:
                return False
            return ours == theirs
        if isinstance(other, str):
            return self._upper == other or self._upper == other.upper()
        return NotImplemented

    def __ne__(self, other) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    @property
    def is_quoted_string(self) -> bool:
        return (self.startswith(_SQUOTE) and self.endswith(_SQUOTE)) or (
            self.startswith(_DQUOTE) and self.endswith(_DQUOTE)
        )

    def __hash__(self):
        # pydantic complains about mutable default otherwise
        return self._hash

    @property
    def comments(self) -> Comments:
        # Created lazily; most tokens never have comments attached.
        comments = self._comments
        if comments is None:
            comments = self._comments = Comments()
        return comments

    @comments.setter
    def comments(self, comments: Comments) -> None:
        self._comments = comments

    def remove_quotes(self) -> Token:
        if self.is_quoted_string:
            # TODO fix location
            return Token(self[1:-1], loc=self.loc, comments=self.comments)
        return self

    def __repr__(self) -> str:
        parts: list[Any]
        if self._detailed_repr_:
            parts = [super().__repr__(), self.loc]
        else:
            parts = [super().__repr__()]
        if bool(self.comments):
            parts.append(self.comments)
        desc = ", ".join(str(part) for part in parts if part)
        return f"{type(self).__name__}({desc})"

    def lstrip(self, chars: str | None = None) -> Self:
        return type(self)(
            str(self).lstrip(chars),
            loc=self.loc,
            comments=self._comments,
        )

    def strip(self, chars: str | None = None) -> Self:
        return type(self)(
            str(self).strip(chars),
            loc=self.loc,
            comments=self._comments,
        )

    def replace(self, old, new, count: SupportsIndex = -1) -> Self:
        return type(self)(
            str(self).replace(old, new, count),
            loc=self.loc,
            comments=self._comments,
        )

    def with_(
        self,
        *,
        loc: Location | None = None,
        comments: Comments | None = None,
    ):
        return type(self)(
            str(self),
            loc=loc or self.loc,
            comments=comments or self._comments,
        )

    def upper(self):
        return type(self)(
            self._upper,
            loc=self.loc,
            comments=self._comments,
        )

    def lower(self):
        return type(self)(
            super().lower(),
            loc=self.loc,
            comments=self._comments,
        )


class Delimiter(Token):
    __slots__ = ()


_DQUOTE = Delimiter('"')
_SQUOTE = Delimiter("'")
