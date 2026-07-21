"""nmlform: a lossless, source-preserving parser and formatter for Fortran namelists."""

from __future__ import annotations

from .apply import apply_namelist_values, interpolate_namelist, split_namelist_key
from .location import Location
from .namelist import (
    Assignment,
    KeyComponent,
    KeyPath,
    Namelist,
    NamelistArrayEntry,
    NamelistArrayGroup,
    NamelistFile,
    is_namelist_file,
    quote_value,
    unquote_value,
)
from .token import Token
from .types import NamelistFormatOptions

try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0.0.dev0"

__all__ = [
    "Assignment",
    "KeyComponent",
    "KeyPath",
    "Location",
    "Namelist",
    "NamelistArrayEntry",
    "NamelistArrayGroup",
    "NamelistFile",
    "NamelistFormatOptions",
    "Token",
    "__version__",
    "apply_namelist_values",
    "interpolate_namelist",
    "is_namelist_file",
    "quote_value",
    "split_namelist_key",
    "unquote_value",
]
