from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

NameCase = Literal["upper", "lower", "same"]


@dataclass
class NamelistFormatOptions:
    """
    Formatting options for Fortran-namelist (``*.init``/``*.nml``) files.

    These control only the field section between a ``&name`` opener and its ``/``
    terminator; the opener and terminator are always emitted at column zero and
    values are never modified.
    """

    indent_size: int = 2
    indent_char: str = " "
    blank_line_after_group: bool = True
    field_case: NameCase = "lower"
    align_equals: bool = True
    align_comments: bool = True
