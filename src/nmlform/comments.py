from __future__ import annotations

import typing
from dataclasses import dataclass, field

if typing.TYPE_CHECKING:
    from .token import Token


@dataclass
class Comments:
    pre: list[Token] = field(default_factory=list)
    inline: Token | None = None

    def __bool__(self):
        return any((self.pre, self.inline))

    def clear(self) -> None:
        self.pre = []
        self.inline = None

    def clone(self) -> Comments:
        return Comments(pre=list(self.pre), inline=self.inline)

    def __repr__(self):
        parts = []
        if self.pre:
            parts.append(f"pre={self.pre}")
        if self.inline:
            parts.append(f"inline={self.inline!r}")

        return f"{type(self).__name__}({', '.join(parts)})"

    # def wrap_code(self, code: str, indent: str = "") -> str:
    #     out = ""
    #     for line in self.pre:
    #         out += f"{indent}! {line}\n"
    #     out += indent + code
    #     if self.inline:
    #         out += f"  ! {self.inline}\n"
    #     return out
