from __future__ import annotations

import pathlib
from typing import NamedTuple


class Location(NamedTuple):
    filename: pathlib.Path | None = None
    # Internally, 0 indexed.  Inclusive end_column.
    # In repr, 1 indexed as all editors start from line 1, col 1. Inclusive end_column.
    # *crowd, in unison: ew*
    line: int = 0
    column: int = 0
    end_line: int = 0
    end_column: int = 0

    def get_string(self, source: str) -> str:
        lines = source.splitlines()[self.line : self.end_line + 1]
        if lines:
            lines[-1] = lines[-1][: self.end_column]
            lines[0] = lines[0][self.column :]
        return "\n".join(lines)

    def __add__(self, other):
        if not isinstance(other, Location):
            raise ValueError(type(other))
        assert self.filename == other.filename
        start_line, start_col = min((loc.line, loc.column) for loc in (self, other))
        end_line, end_col = max((loc.end_line, loc.end_column) for loc in (self, other))
        return type(self)(
            filename=self.filename,
            line=start_line,
            column=start_col,
            end_line=end_line,
            end_column=end_col,
        )

    @classmethod
    def from_items(cls, items) -> Location:
        locations: list[Location] = []
        for item in items:
            if item is None:
                continue
            if isinstance(item, Location):
                loc = item
            else:
                loc = item.loc

            if loc is not None:
                locations.append(loc)

        if not locations:
            raise ValueError("No items with location found")

        start_line, start_col = min((loc.line, loc.column) for loc in locations)
        end_line, end_col = max((loc.end_line, loc.end_column) for loc in locations)
        fn = locations[0].filename
        return Location(
            filename=fn, line=start_line, column=start_col, end_line=end_line, end_column=end_col
        )

    def __str__(self) -> str:
        user_line = self.line + 1
        user_end_line = self.end_line
        user_col = self.column + 1
        user_end_col = self.end_column
        start = f"{self.filename}:{user_line}:{user_end_col}"

        if self.line == self.end_line:
            if user_col == user_end_col:
                return start
            return f"{start}-{user_end_col}"

        return f"{start}-{user_end_line}:{user_end_col}"
