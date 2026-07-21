from __future__ import annotations

import enum
import typing
from typing import Any, ClassVar, SupportsIndex

from .comments import Comments
from .location import Location

if typing.TYPE_CHECKING:
    try:
        from typing import Self
    except ImportError:
        from typing_extensions import Self


class Role(str, enum.Enum):
    name_ = "name"
    builtin = "builtin"
    kind = "kind"
    attribute_name = "attribute_name"
    env_var = "env_var"
    statement_definition = "statement_definition"
    filename = "filename"
    controller_variable = "controller_variable"


class Token(str):
    """
    String with source loc information.

    Comparisons are case-insensitive.
    """

    loc: Location
    comments: Comments
    role: Role | None = None
    _upper: str
    _hash: int

    _detailed_repr_: ClassVar[bool] = True

    def __new__(
        cls,
        content: str,
        loc: Location | None = None,
        comments: Comments | None = None,
        role: Role | None = None,
    ):
        return super().__new__(cls, content)

    def __init__(
        self,
        content: str,
        loc: Location | None = None,
        comments: Comments | None = None,
        role: Role | None = None,
    ):
        self.loc = loc or Location(end_column=len(content))
        self.comments = comments or Comments()
        self.role = role
        self._upper = str.upper(self)
        # self._hash = hash(self._upper)
        self._hash = super().__hash__()

        # internal error
        if not isinstance(self.loc, Location):
            raise ValueError(type(self.loc))
        if not isinstance(self.comments, Comments):
            raise ValueError(type(self.comments))
        if role and not isinstance(self.role, Role):
            raise ValueError(type(self.role))

    def __hash__(self):
        # pydantic complains about mutable default otherwise
        return self._hash

    def __eq__(self, other) -> bool:
        if isinstance(other, Token):
            return self._upper == other._upper and self.comments == other.comments
        if self._upper == other:
            return True
        if isinstance(other, str):
            return self._upper == other.upper()
        return self._upper == str(other).upper()

    def __ne__(self, other) -> bool:
        return not (self == other)

    @property
    def is_quoted_string(self) -> bool:
        return (self.startswith(_SQUOTE) and self.endswith(_SQUOTE)) or (
            self.startswith(_DQUOTE) and self.endswith(_DQUOTE)
        )

    def remove_quotes(self) -> Token:
        if self.is_quoted_string:
            # TODO fix location
            return Token(self[1:-1], loc=self.loc, comments=self.comments)
        return self

    def __repr__(self) -> str:
        if self._detailed_repr_:
            parts = [super().__repr__(), self.role, self.loc]
        else:
            parts = [super().__repr__()]
        if bool(self.comments):
            parts.append(self.comments)
        desc = ", ".join(str(part) for part in parts if part)
        return f"{type(self).__name__}({desc})"

    def annotate(self, named: dict[Token, Any]):
        if self.upper() in named and self.role not in {
            Role.attribute_name,
            Role.env_var,
            Role.filename,
        }:
            self.role = Role.name_

    def quoted(self) -> Self:
        if self.is_quoted_string:
            return self

        value = str(self).strip()
        if '"' in value:
            quote_char = "'"
        else:
            quote_char = '"'
        if quote_char in value:
            # Sorry, but why use both quote types and not quote your string to begin with?
            # I don't think there's an escape character we can use
            value = value.replace(quote_char, " ")

        return type(self)(
            f"{quote_char}{value}{quote_char}",
            loc=self.loc,
            comments=self.comments,
            role=self.role,
        )

    def lstrip(self, chars: str | None = None) -> Self:
        return type(self)(
            str(self).lstrip(chars),
            loc=self.loc,
            comments=self.comments,
            role=self.role,
        )

    def strip(self, chars: str | None = None) -> Self:
        return type(self)(
            str(self).strip(chars),
            loc=self.loc,
            comments=self.comments,
            role=self.role,
        )

    def replace(self, old, new, count: SupportsIndex = -1) -> Self:
        return type(self)(
            str(self).replace(old, new, count),
            loc=self.loc,
            comments=self.comments,
            role=self.role,
        )

    def with_(
        self,
        *,
        loc: Location | None = None,
        comments: Comments | None = None,
        role: Role | None = None,
    ):
        return type(self)(
            str(self),
            loc=loc or self.loc,
            comments=comments or self.comments,
            role=role or self.role,
        )

    def upper(self):
        return type(self)(
            self._upper,
            loc=self.loc,
            comments=self.comments,
            role=self.role,
        )

    def lower(self):
        return type(self)(
            super().lower(),
            loc=self.loc,
            comments=self.comments,
            role=self.role,
        )


class Delimiter(Token):
    pass


_DQUOTE = Delimiter('"')
_SQUOTE = Delimiter("'")
