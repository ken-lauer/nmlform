"""
Lossless, source-preserving Fortran-namelist reader/writer.

Unlike value-oriented readers, this keeps the source lines as the source of
truth and derives a location-tagged tree over them, so comments, spacing,
quoting, and layout survive a round trip. Positional array data is kept as raw,
un-typed tokens; the caller supplies the shape via `NamelistArrayEntry.FIELDS`
rather than the parser guessing it.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from functools import cached_property
from itertools import groupby
from typing import TYPE_CHECKING, ClassVar, NamedTuple, cast

from .location import Location
from .token import Token
from .types import NamelistFormatOptions

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Literal, Self


__all__ = [
    "Assignment",
    "KeyComponent",
    "KeyPath",
    "Namelist",
    "NamelistArrayEntry",
    "NamelistArrayGroup",
    "NamelistFile",
    "is_namelist_file",
    "quote_value",
    "unquote_value",
]

_NAMELIST_SUFFIXES = frozenset({".init", ".nml"})


def is_namelist_file(path: pathlib.Path | str) -> bool:
    """Whether ``path`` names a Fortran-namelist file (``*.init`` or ``*.nml``)."""
    return pathlib.Path(path).suffix.lower() in _NAMELIST_SUFFIXES


# '$' as the group sigil is a GNU extension accepted by gfortran.
_RE_GROUP_OPEN = re.compile(r"\s*(?P<sigil>[&$])(?P<name>\w+)")
# gfortran scans the character stream for the opener, so a group may open
# mid-line after arbitrary text.
_RE_GROUP_ANYWHERE = re.compile(r"[&$]\w+")
# A group terminator equivalent to '/': '&end' or '$end', case-insensitive.
_RE_GROUP_END = re.compile(r"[&$]end", re.IGNORECASE)
_RE_COMPONENT = re.compile(r"([^()%]+)(?:\((.*)\))?")  # one key-path segment: name(subscript)?
_RE_NORMALIZE_KEY = re.compile(r"\s+")
_RE_INT = re.compile(r"-?\d+")
# A 1-D array-section triplet: every part of start:stop:step is optional.
# Declared bounds are unknown here, so a missing start defaults to the
# Fortran default lower bound of 1; a missing stop makes the section
# open-ended (see KeyComponent.open_slice).
_RE_TRIPLET = re.compile(r"(-?\d+)?:(-?\d+)?(?::(-?\d+))?")
# A namelist value field is a quoted string or a bare token; fields are
# separated by whitespace/commas, which fall between the matches. Fortran
# escapes a quote inside a string by doubling it ('it''s').
_SINGLE_QUOTED_CLOSED = r"'(?:''|[^'])*'"
_DOUBLE_QUOTED_CLOSED = r'"(?:""|[^"])*"'
# The trailing ? tolerates a missing closing quote: the string continues on
# the next source line (or is simply unterminated).
_SINGLE_QUOTED = _SINGLE_QUOTED_CLOSED + "?"
_DOUBLE_QUOTED = _DOUBLE_QUOTED_CLOSED + "?"
_RE_CLOSED_STRING = re.compile(rf"{_SINGLE_QUOTED_CLOSED}|{_DOUBLE_QUOTED_CLOSED}")
_BARE_TOKEN = r"""[^ \t\r\n,'"]+"""  # runs until a separator or quote
_REPEAT_COUNT = r"(?:(?P<count>\d+)\*)?"  # optional Fortran repeat: 3*0 -> 0 0 0
_RE_VALUE_FIELD = re.compile(
    rf"{_REPEAT_COUNT}(?P<value>{_SINGLE_QUOTED}|{_DOUBLE_QUOTED}|{_BARE_TOKEN})"
)
_RE_REPEAT_PREFIX = re.compile(r"\d+\*")
# A bare (unquoted) run as the line lexers see it: stops at a whitespace/comma
# separator (an embedded newline acts as a blank), '=', '/', or a quote.
# Unlike _BARE_TOKEN, '=' and '/' stop it.
_LEX_BARE = r"""[^ \t\r\n,=/'"]+"""
# One coarse lexical token: a quoted string, a bare run, or an '='/'/'.
# Separators fall between matches. This deliberately ignores the stateful
# rules (paren depth, designator blanks, repeat merges); `_lex_line` detects
# those cases and defers to `_scan_line`.
_RE_LEX = re.compile(rf"{_SINGLE_QUOTED}|{_DOUBLE_QUOTED}|{_LEX_BARE}|[=/]")


# Spaces between the longest field in a run and its aligned inline comment.
_INLINE_COMMENT_GAP = 2
QUOTE_CHARS = "'\""


def _field_value_span(text: str) -> tuple[int, int, int]:
    """
    ``(start, end, count)`` of the value within one raw field.

    A Fortran repeat-count prefix (``3*0``) sets ``count`` and is excluded
    from the span; otherwise the span is the whole field and ``count`` is 1.
    """
    if "*" in text:
        match = _RE_VALUE_FIELD.fullmatch(text)
        if match is not None and match["count"]:
            start, end = match.span("value")
            return start, end, int(match["count"])
    return 0, len(text), 1


def _find_comment_index(line: str) -> int | None:
    """
    Index of the ``!`` that starts a trailing comment, or ``None``.

    A ``!`` inside a quoted string does not start a comment.
    """
    first = line.find("!")
    if first < 0:
        return None
    prefix = line[:first]
    if "'" not in prefix and '"' not in prefix:
        return first

    in_single_quote = False
    in_double_quote = False
    for i, char in enumerate(line):
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "!" and not in_single_quote and not in_double_quote:
            return i
    return None


def quote_value(text: str, quote: str = "'") -> str:
    """
    Quote ``text`` as a Fortran-namelist string literal.

    Embedded ``quote`` characters are escaped by doubling (``it's`` becomes
    ``'it''s'``); the other quote character passes through untouched.

    Parameters
    ----------
    text : str
        The string content to quote.
    quote : {"'", '"'}, optional
        The delimiter to use. Defaults to a single quote.
    """
    if quote not in {"'", '"'}:
        raise ValueError(f"quote must be a single or double quote character, got {quote!r}")
    escaped = quote * 2
    return "".join((quote, text.replace(quote, escaped), quote))


def unquote_value(token: Token) -> Token:
    """
    The string content of a namelist value token.

    Strips the outer quotes and undoubles the escaped delimiter quote
    character (``'it''s'`` becomes ``it's``); occurrences of the other quote
    character are literal and left untouched. Bare (unquoted) and unterminated
    tokens are returned unchanged.
    """
    if not token.is_quoted_string:
        return token
    text = str(token)
    quote = text[0]
    escaped = quote * 2
    return Token(text[1:-1].replace(escaped, quote), loc=token.loc, comments=token.comments)


def _split_comment(line: str) -> tuple[str, str]:
    """
    Split a line into its code part and its comment part (comment ``!`` dropped).

    Quote-aware; neither part is stripped. The comment part is empty when the
    line has no comment.
    """
    idx = _find_comment_index(line)
    if idx is None:
        return line, ""
    return line[:idx], line[idx + 1 :]


def _apply_field_case(key: str, case: str) -> str:
    """Case a namelist field name per ``case`` (``"lower"``/``"upper"``/other)."""
    if case == "lower":
        return key.lower()
    if case == "upper":
        return key.upper()
    return key


def _normalize_key(key: str) -> str:
    """Whitespace-insensitive, case-insensitive key form used for lookups."""
    return _RE_NORMALIZE_KEY.sub("", key).lower()


@dataclass(slots=True)
class _FieldRecord:
    """A ``key = value`` record being formatted, possibly spanning lines."""

    key: str
    chunks: list[str]  # value text per rendered row; chunks[0] follows "key = "
    comments: list[str]  # trailing comment per rendered row ("" when none)
    key_width: int = 0
    comment_column: int = 0

    def code_lines(self, indent: str) -> list[str]:
        """The rendered rows, without trailing comments."""
        key = self.key.ljust(self.key_width)
        first = f"{indent}{key} = {self.chunks[0]}"
        # Continuation values align under the first value character.
        continuation = " " * (len(first) - len(self.chunks[0]))
        return [first, *(f"{continuation}{chunk}" for chunk in self.chunks[1:])]

    def render_row(self, index: int, indent: str) -> str:
        code = self.code_lines(indent)[index]
        comment = self.comments[index]
        if not comment:
            return code.rstrip()
        padded = code.ljust(self.comment_column) if self.comment_column else f"{code} "
        return f"{padded}{comment}"


def _format_group_lines(lines: list[str], options: NamelistFormatOptions) -> list[str]:
    """
    Format the source lines of one ``&name ... /`` group.

    ``key = value`` records are re-indented, their names cased per
    ``options.field_case``, and the spacing around ``=`` normalized. A record
    whose value continues across lines keeps its wrapping, continuation values
    aligned under the first value character; several records sharing one source
    line are split onto separate lines. Within each blank-line-delimited run of
    records, the ``=`` (when ``align_equals``) and the trailing ``!`` comments
    (when ``align_comments``) are padded into columns. The opener and
    terminator stay at column zero, blank lines stay empty, and comment-only
    lines are indented but do not participate in a run's alignment. A record
    whose quoted string continues across lines is left completely verbatim:
    re-indenting its continuation would change the string's content.
    """
    indent = options.indent_char * options.indent_size
    scan = _scan_namelist(lines)

    # Lines of records kept byte-identical (multiline quoted strings).
    verbatim: set[int] = set()
    for assignment in scan.assignments:
        if any(token.kind == "strcont" for token in assignment.field_tokens):
            verbatim.update(range(assignment.span.line, assignment.span.end_line + 1))

    # anchors: physical line -> rows to emit there; line_rows: physical line ->
    # the (record, row) owning that line's trailing comment (last record wins);
    # consumed: lines whose code is re-rendered through a record.
    anchors: dict[int, list[tuple[_FieldRecord, int]]] = {}
    line_rows: dict[int, tuple[_FieldRecord, int]] = {}
    consumed: set[int] = set()

    for assignment in scan.assignments:
        start = assignment.span.line  # base_line=0: locations are line indices
        if any(ln in verbatim for ln in range(start, assignment.span.end_line + 1)):
            # This assignment shares lines with a verbatim record; formatting
            # it would splice those lines. Keep it verbatim too.
            continue
        # ``str(value)`` is the raw field-to-field slice per physical line
        # (including any repeat-count prefix), joined with newlines.
        chunk_lines = sorted({token.loc.line for token in assignment.values})
        chunks = []
        for part, ln in zip(str(assignment.value).split("\n"), chunk_lines):
            if ln != chunk_lines[-1]:
                # Keep a trailing comma marking the continuation.
                end = max(t.loc.end_column for t in assignment.values if t.loc.line == ln)
                rest = lines[ln][end:].lstrip(" \t")
                if rest.startswith(","):
                    part += ","
            chunks.append(part)
        chunks = chunks or [""]
        record = _FieldRecord(
            key=_apply_field_case(assignment.key, options.field_case),
            chunks=chunks,
            comments=[""] * len(chunks),
        )
        anchors.setdefault(start, []).append((record, 0))
        line_rows[start] = (record, 0)
        for row, ln in enumerate(chunk_lines):
            if row > 0:
                anchors.setdefault(ln, []).append((record, row))
            line_rows[ln] = (record, row)
        consumed.update(range(assignment.span.line, assignment.span.end_line + 1))

    for index, line in enumerate(lines):
        comment_index = _find_comment_index(line)
        if comment_index is None:
            continue
        comment = line[comment_index:].strip()
        owner = line_rows.get(index)
        if owner is not None:
            record, row = owner
            existing = record.comments[row]
            record.comments[row] = f"{existing} {comment}".strip() if existing else comment

    # A run is a maximal group of records uninterrupted by a blank line;
    # comment-only and unparsable lines neither join nor break it.
    runs: list[list[_FieldRecord]] = [[]]
    for index, line in enumerate(lines):
        if index in anchors:
            runs[-1].extend(record for record, row in anchors[index] if row == 0)
        elif not line.strip() and index not in consumed:
            runs.append([])

    for run in runs:
        if not run:
            continue
        if options.align_equals:
            width = max(len(r.key) for r in run)
            for r in run:
                r.key_width = width
        if options.align_comments:
            column = (
                max(len(code) for r in run for code in r.code_lines(indent)) + _INLINE_COMMENT_GAP
            )
            for r in run:
                r.comment_column = column

    terminator = scan.terminator
    opener = bool(lines) and lines[0].lstrip().startswith(("&", "$"))
    opener_text = lines[0].strip() if lines else ""
    if opener and (0 in anchors or (terminator is not None and terminator[0] == 0)):
        # Records and/or the terminator share the opener line: keep only &name.
        match = _RE_GROUP_OPEN.match(lines[0])
        if match is not None:
            opener_text = f"{match['sigil']}{match['name']}"

    out: list[str] = []
    for index, line in enumerate(lines):
        if index in verbatim:
            out.append(line)
            continue
        if index == 0 and opener:
            out.append(opener_text)
        for record, row in anchors.get(index, ()):
            out.append(record.render_row(row, indent))
        if terminator is not None and terminator[0] == index:
            out.append(line[terminator[1] :].rstrip())
            continue
        if (index == 0 and opener) or index in anchors:
            continue
        stripped = line.strip()
        if index in consumed:
            # Comment-only lines inside a record's span keep their place;
            # blank lines inside one are dropped.
            if stripped.startswith("!"):
                out.append(f"{indent}{stripped}")
            continue
        out.append("" if not stripped else f"{indent}{stripped}")
    return out


class _ScanToken(NamedTuple):
    """
    One lexical token of a group's comment-stripped source lines.

    A ``strcont`` token is the continuation of a quoted string left open by
    the previous line; it starts at column zero, so its leading whitespace
    (which is string content) is preserved. A ``slash`` token is any group
    terminator: a ``/`` or an ``&end``/``$end``. A ``null`` token spans the
    comma denoting a Fortran null value (an element to skip): a comma beyond
    the first in the separators after a value, or any comma directly after
    ``=``.
    """

    kind: Literal["open", "eq", "slash", "field", "strcont", "null"]
    text: str
    line: int  # index into the scanned lines, not the source file
    column: int
    end_column: int


def _read_quoted(code: str, start: int) -> int:
    """Index one past the quoted string starting at ``code[start]`` (a quote)."""
    quote = code[start]
    i = start + 1
    while i < len(code):
        if code[i] == quote:
            # doubled-quote escape, e.g. 'it''s'
            # slice handles end-of-string scenario
            if code[i + 1 : i + 2] == quote:
                i += 2
                continue
            return i + 1
        i += 1
    return len(code)  # unterminated: runs to the end of the line


def _read_string_close(line: str, quote: str) -> int | None:
    """
    Index one past the quote closing a string continued onto this line.

    ``None`` when the string does not close on this line. Doubled quotes are
    escapes, as in `_read_quoted`.
    """
    i = 0
    while i < len(line):
        if line[i] == quote:
            if line[i + 1 : i + 2] == quote:
                i += 2
                continue
            return i + 1
        i += 1
    return None


def _unterminated_quote(field_text: str) -> str | None:
    """
    The delimiter of a quoted field missing its closing quote, or ``None``.

    `_read_quoted` cannot distinguish a string closing exactly at the end of
    the line from an unterminated one, so this re-checks the token text. A
    repeat-count prefix (``3*'ab``) is stripped first.
    """
    match = _RE_REPEAT_PREFIX.match(field_text)
    if match is not None:
        field_text = field_text[match.end() :]
    quote = field_text[:1]
    if quote not in ("'", '"') or _RE_CLOSED_STRING.fullmatch(field_text):
        return None
    return quote


def _read_field(code: str, start: int) -> int:
    """
    Index one past the field token starting at ``start``.

    * A quoted string is a single token.
    * A bare token runs until a separator, ``=``, ``/``, or quote at
      parenthesis depth zero
    * Subscripts like ``datum( 1)`` and ``var(1 : 6)%x`` stay whole.
    * Fortran repeat count directly followed by a quote (``6*'x'``)
      continues into the string.
    """
    if code[start] in QUOTE_CHARS:
        return _read_quoted(code, start)

    paren_depth = 0
    i = start
    whitespace = frozenset(" \t\r\n")
    length = len(code)
    while i < length:
        char = code[i]
        if paren_depth == 0:
            if char in whitespace:
                j = i
                while j < length and code[j] in whitespace:
                    j += 1
                # skip to the next (%
                prev_ch = code[i - 1]
                if j < length and (code[j] in "(%" or prev_ch == "%"):
                    i = j
                    continue
                break
            if char in ",=/":
                break
            if char in QUOTE_CHARS:
                if _RE_REPEAT_PREFIX.fullmatch(code, start, i):
                    return _read_quoted(code, i)
                break

        if char == "(":
            paren_depth += 1
        elif char == ")" and paren_depth:
            paren_depth -= 1
        i += 1
    return i


def _scan_line(code: str) -> Iterator[tuple[str, int, int]]:
    """Yield ``(kind, start, end)`` lexical tokens of one comment-stripped line."""
    i = 0
    while i < len(code):
        char = code[i]
        if char in " \t\r\n,":
            i += 1
        elif char == "=":
            yield "eq", i, i + 1
            i += 1
        elif char == "/":
            yield "slash", i, i + 1
            return  # the group ends here; the rest of the line is not code
        else:
            end = _read_field(code, i)
            yield "field", i, end
            i = end


def _lex_line(code: str) -> list[tuple[str, int, int]]:
    """
    ``(kind, start, end)`` lexical tokens of one comment-stripped line.

    A regex pass covers the common shapes; a line whose bare tokens show signs
    of the stateful constructs (a blank inside ``(...)`` or around ``%``) is
    re-lexed with the character scanner, so the result is always identical to
    ``_scan_line``'s.
    """
    tokens: list[tuple[str, int, int]] = []
    matches = list(_RE_LEX.finditer(code))
    index = 0
    total = len(matches)
    while index < total:
        match = matches[index]
        text = match[0]
        first = text[0]
        if first == "=":
            tokens.append(("eq", match.start(), match.end()))
        elif first == "/":
            tokens.append(("slash", match.start(), match.end()))
            return tokens
        elif first in QUOTE_CHARS:
            tokens.append(("field", match.start(), match.end()))
        else:
            # Signs that the stateful rules apply: a token split inside
            # parens, or a designator blank ("datum (1)", "a % b").
            if first in "(%" or text[-1] == "%":
                return list(_scan_line(code))
            if "(" in text and text.count("(") != text.count(")"):
                return list(_scan_line(code))
            end = match.end()
            if text[-1] == "*" and _RE_REPEAT_PREFIX.fullmatch(text):
                # Repeat count directly followed by a quote: 6*'x' is one field.
                nxt = matches[index + 1] if index + 1 < total else None
                if nxt is not None and nxt.start() == end and nxt[0][0] in QUOTE_CHARS:
                    end = nxt.end()
                    index += 1
            tokens.append(("field", match.start(), end))
        index += 1
    return tokens


def _scan_line_state(line: str, open_quote: str | None) -> tuple[int | None, str | None]:
    """
    ``(terminator column, open-string state)`` after scanning one group line.

    ``open_quote`` is the delimiter of a quoted string the previous line left
    unterminated (its continuation is consumed first, so a ``/`` or ``!``
    inside it is content), or ``None``. The terminator is a ``/`` or an
    ``&end``/``$end``.
    """
    if open_quote is None:
        if not any(c in line for c in "/'\"&$"):
            return None, None
        offset = 0
    else:
        if open_quote not in line:
            return None, open_quote
        close = _read_string_close(line, open_quote)
        if close is None:
            return None, open_quote
        offset = close
    code, _ = _split_comment(line[offset:])
    last_field: str | None = None
    for kind, start, end in _lex_line(code):
        if kind == "slash":
            return offset + start, None
        if kind == "field":
            text = code[start:end]
            if text[0] in "&$" and _RE_GROUP_END.fullmatch(text):
                return offset + start, None
            last_field = text
        else:
            last_field = None
    if last_field is None:
        return None, None
    return None, _unterminated_quote(last_field)


def _scan_group(lines: list[str]) -> Iterator[_ScanToken]:
    """
    Lex a group's source lines into `_ScanToken`s.

    Comments are stripped per line. The first token, when it starts with
    ``&`` or ``$``, is the group opener. A quoted string left open at the
    end of a line continues onto the next: the continuation (through its
    closing quote) is yielded as a ``strcont`` token starting at column
    zero, and only the rest of the line is comment-stripped and lexed.
    Scanning stops at the group terminator -- a ``/`` or an ``&end``/``$end``
    (both yielded as ``slash``).

    Fortran null values are yielded as ``null`` tokens: within the separators
    following a value, every comma beyond the first denotes one skipped
    element, as does any comma directly after ``=``. The separator gap
    carries across lines, so ``x = 1,`` continued by ``,3`` holds a null.
    """
    first = True
    open_quote: str | None = None
    # What the current separator gap follows ("value"/"eq"/"none"), and
    # whether the gap's separating comma has been seen yet.
    gap_after = "none"
    gap_comma_seen = False

    def gap_nulls(code: str, lo: int, hi: int, index: int, offset: int) -> Iterator[_ScanToken]:
        nonlocal gap_comma_seen
        for i in range(lo, hi):
            if code[i] != ",":
                continue
            if gap_after == "eq" or (gap_after == "value" and gap_comma_seen):
                yield _ScanToken("null", ",", index, offset + i, offset + i + 1)
            gap_comma_seen = True

    for index, line in enumerate(lines):
        offset = 0
        if open_quote is not None:
            close = _read_string_close(line, open_quote)
            if close is None:
                yield _ScanToken("strcont", line, index, 0, len(line))
                continue
            yield _ScanToken("strcont", line[:close], index, 0, close)
            open_quote = None
            offset = close
            gap_after, gap_comma_seen = "value", False
        code, _ = _split_comment(line[offset:])
        last_field: str | None = None
        prev_end = 0
        for kind, start, end in _lex_line(code):
            yield from gap_nulls(code, prev_end, start, index, offset)
            prev_end = end
            text = code[start:end]
            if kind == "field" and text[0] in "&$":
                if first:
                    kind = "open"
                elif _RE_GROUP_END.fullmatch(text):
                    kind = "slash"
            first = False
            yield _ScanToken(kind, text, index, offset + start, offset + end)
            if kind == "slash":
                return
            if kind == "field":
                gap_after, last_field = "value", text
            else:
                gap_after, last_field = ("eq" if kind == "eq" else "none"), None
            gap_comma_seen = False
        yield from gap_nulls(code, prev_end, len(code), index, offset)
        if last_field is not None:
            open_quote = _unterminated_quote(last_field)


def _build_assignment(
    key: _ScanToken,
    eq: _ScanToken,
    fields: list[_ScanToken],
    lines: list[str],
    filename: pathlib.Path | None,
    base_line: int,
) -> Assignment:
    """Assemble an `Assignment` from its key/``=``/value tokens."""
    if fields:
        first, last = fields[0], fields[-1]
        if first.line == last.line:
            text = lines[first.line][first.column : last.end_column]
        else:
            parts: list[str] = []
            for index, group in groupby(fields, key=lambda token: token.line):
                row = list(group)
                parts.append(lines[index][row[0].column : row[-1].end_column])
            text = "\n".join(parts)
        value = Token(
            text,
            loc=Location(
                filename=filename,
                line=base_line + first.line,
                column=first.column,
                end_line=base_line + last.line,
                end_column=last.end_column,
            ),
        )
    else:
        # Empty right-hand side (``x =``): a zero-width token just after the '='.
        line = base_line + eq.line
        loc = Location(
            filename=filename,
            line=line,
            column=eq.end_column,
            end_line=line,
            end_column=eq.end_column,
        )
        value = Token("", loc=loc)

    key_text = key.text
    if " " in key_text or "\t" in key_text:
        key_text = _RE_NORMALIZE_KEY.sub("", key_text)
    return Assignment(
        key=key_text,
        value=value,
        key_loc=Location(
            filename=filename,
            line=base_line + key.line,
            column=key.column,
            end_line=base_line + key.line,
            end_column=key.end_column,
        ),
        field_tokens=tuple(fields),
        base_line=base_line,
    )


@dataclass
class _GroupScan:
    """Parsed content of one ``&name ... /`` group's source lines."""

    assignments: list[Assignment]
    # (line index, column) of the terminator ('/' or '&end'/'$end').
    terminator: tuple[int, int] | None


def _scan_namelist(
    lines: list[str],
    *,
    filename: pathlib.Path | None = None,
    base_line: int = 0,
) -> _GroupScan:
    """
    Parse a group's source lines into `Assignment`s with true source spans.

    Namelist input is free-form: values (including quoted strings) may
    continue across lines, several ``key = value`` pairs may share a line,
    assignments may sit on the ``&name`` opener line, and ``/`` (or
    ``&end``/``$end``) terminates the group anywhere outside a quoted
    string. Trailing comments attach to the last assignment whose span
    covers their line.
    """
    assignments: list[Assignment] = []
    pending: list[_ScanToken] = []
    key: _ScanToken | None = None
    eq: _ScanToken | None = None
    terminator: tuple[int, int] | None = None

    def finalize() -> None:
        if key is not None and eq is not None:
            assignments.append(_build_assignment(key, eq, pending, lines, filename, base_line))
        pending.clear()

    for token in _scan_group(lines):
        if token.kind in ("field", "strcont", "null"):
            pending.append(token)
        elif token.kind == "eq":
            # The token just before '=' keys the next assignment; the rest of
            # the pending fields close out the previous one. A stray '=' (no
            # preceding token, a quoted string, or a string continuation) is
            # ignored.
            if pending and pending[-1].kind == "field" and pending[-1].text[0] not in QUOTE_CHARS:
                next_key = pending.pop()
                finalize()
                key, eq = next_key, token
        elif token.kind == "slash":
            terminator = (token.line, token.column)
            break
    finalize()

    if assignments:
        # (start line, end line) span bounds, avoiding Location construction.
        bounds = [
            (a.key_loc.line if a.key_loc is not None else a.value.loc.line, a.value.loc.end_line)
            for a in assignments
        ]
        # A line beginning inside a continued string: comment scanning starts
        # after the string closes (a '!' inside it is content).
        cont_end = {
            token.line: token.end_column
            for a in assignments
            for token in a.field_tokens
            if token.kind == "strcont"
        }
        for index, line in enumerate(lines):
            if "!" not in line:
                continue
            _, comment = _split_comment(line[cont_end.get(index, 0) :])
            comment = comment.strip()
            if not comment:
                continue
            absolute = base_line + index
            for position in range(len(assignments) - 1, -1, -1):
                start, end = bounds[position]
                if start <= absolute <= end:
                    assignment = assignments[position]
                    assignment.comment = f"{assignment.comment} {comment}".strip()
                    break

    return _GroupScan(assignments=assignments, terminator=terminator)


@dataclass(frozen=True)
class KeyComponent:
    """One ``name`` or ``name(index)`` segment of a derived-type key path."""

    name: str
    index_text: str | None = None

    @property
    def index(self) -> int | None:
        """The integer index, or ``None`` for no index or a non-integer (e.g. a ``1:8`` range)."""
        if self.index_text is not None and self.index_text.isdigit():
            return int(self.index_text)
        return None

    @property
    def indices(self) -> list[int] | None:
        """
        The explicit integer indices this component designates.

        ``[i]`` for a single subscript ``name(i)``; the expanded, ``stop``-
        inclusive range for an array section ``name(a:b)`` or
        ``name(a:b:step)``. A missing ``a`` defaults to a lower bound of 1;
        a negative step descends (``5:1:-2`` gives ``[5, 3, 1]``). The list
        is empty when the section designates no elements (e.g. ``5:3``,
        which gfortran itself rejects as a bad range). ``None`` when there
        is no subscript or it cannot be enumerated: a non-integer or named
        bound, a zero step, an open-ended section (see `open_slice`), or a
        multi-dimensional subscript.
        """
        text = self.index_text
        if text is None:
            return None
        if _RE_INT.fullmatch(text):
            return [int(text)]
        match = _RE_TRIPLET.fullmatch(text)
        if match is None or match[2] is None:
            return None
        start = int(match[1]) if match[1] else 1
        stop = int(match[2])
        step = int(match[3]) if match[3] else 1
        if step == 0:
            return None
        return list(range(start, stop + (1 if step > 0 else -1), step))

    @property
    def open_slice(self) -> tuple[int, int] | None:
        """
        ``(start, step)`` of an open-ended array section, or ``None``.

        Open-ended means no stop bound: ``name(a:)``, ``name(:)``, or
        ``name(a::step)``; a missing ``a`` defaults to a lower bound of 1.
        ``None`` for a closed section, a non-section subscript, or a zero
        step.
        """
        text = self.index_text
        if text is None:
            return None
        match = _RE_TRIPLET.fullmatch(text)
        if match is None or match[2] is not None:
            return None
        start = int(match[1]) if match[1] else 1
        step = int(match[3]) if match[3] else 1
        return (start, step) if step else None

    @property
    def slice_start(self) -> int | None:
        """The start of an open-ended array section (see `open_slice`), or ``None``."""
        open_slice = self.open_slice
        return open_slice[0] if open_slice is not None else None

    def __str__(self) -> str:
        return self.name if self.index_text is None else f"{self.name}({self.index_text})"


@dataclass(frozen=True)
class KeyPath:
    """A decomposed derived-type assignment key, e.g. ``foo(3)%bar(2)%val``."""

    components: tuple[KeyComponent, ...]

    @classmethod
    def parse(cls, key: str) -> KeyPath:
        normalized = _RE_NORMALIZE_KEY.sub("", key)
        components: list[KeyComponent] = []
        for part in normalized.split("%"):
            match = _RE_COMPONENT.fullmatch(part)
            if match is None:
                components.append(KeyComponent(part))
            else:
                components.append(KeyComponent(match.group(1), match.group(2)))
        return cls(tuple(components))

    @property
    def names(self) -> tuple[str, ...]:
        """The component names in order, without indices."""
        return tuple(component.name.lower() for component in self.components)

    def __str__(self) -> str:
        return "%".join(str(component) for component in self.components)


@dataclass
class Assignment:
    """
    A single ``key = value`` assignment within a namelist group.

    Values are free-form: they may continue across lines and several
    assignments may share one line.

    Attributes
    ----------
    key : str
        The whitespace-normalized key (e.g. ``datum(1)%ele_name``).
    value : Token
        The value text. Its ``loc`` spans from the first character of the
        first value field through the last character of the last one
        (multi-line when the value continues across lines). Per physical
        line, ``str(value)`` is the raw source slice from that line's first
        field to its last, joined with newlines — so for single-line values
        ``str(value) == value.loc.get_string(source)`` exactly.
    values : list[Token]
        The individual value fields with per-field source locations; Fortran
        repeat counts (``3*0``) are expanded. Derived lazily from the scanned
        field tokens.
    comment : str
        Trailing ``!`` comments on the lines the assignment spans.
    key_loc : Location or None
        Source location of the key.
    """

    key: str
    value: Token
    comment: str = ""
    key_loc: Location | None = None
    # Raw value-field tokens (group-relative lines) that back ``values``.
    field_tokens: tuple[_ScanToken, ...] = field(default=(), repr=False)
    base_line: int = 0

    @cached_property
    def values(self) -> list[Token]:
        """
        The value fields, repeat counts expanded, with per-field locations.

        A quoted string continued across lines is one token, its per-line
        texts joined with newlines. A Fortran null value -- ``,,``, a comma
        directly after ``=``, or a bare repeat ``r*`` -- is an empty token
        per skipped element, so positional slots stay honest.
        """
        filename = self.value.loc.filename
        base_line = self.base_line

        def null_token(token: _ScanToken, count: int = 1) -> list[Token]:
            loc = Location(
                filename=filename,
                line=base_line + token.line,
                column=token.end_column,
                end_line=base_line + token.line,
                end_column=token.end_column,
            )
            return [Token("", loc=loc) for _ in range(count)]

        values: list[Token] = []
        for token in self.field_tokens:
            text = token.text
            if token.kind == "null":
                values.extend(null_token(token))
                continue
            if token.kind == "strcont" and values:
                prev = values[-1]
                values[-1] = Token(
                    f"{prev}\n{text}",
                    loc=Location(
                        filename=filename,
                        line=prev.loc.line,
                        column=prev.loc.column,
                        end_line=base_line + token.line,
                        end_column=token.end_column,
                    ),
                )
                continue
            if _RE_REPEAT_PREFIX.fullmatch(text):
                # A bare repeat count ("3*"): that many nulls.
                values.extend(null_token(token, int(text[:-1])))
                continue
            start, end, count = _field_value_span(text)
            loc = Location(
                filename=filename,
                line=base_line + token.line,
                column=token.column + start,
                end_line=base_line + token.line,
                end_column=token.column + end,
            )
            values.extend(Token(text[start:end], loc=loc) for _ in range(count))
        return values

    @property
    def loc(self) -> Location:
        """Source location of the value (``value.loc``)."""
        return self.value.loc

    @property
    def span(self) -> Location:
        """Source span from the start of the key through the last value character."""
        if self.key_loc is None:
            return self.value.loc
        return self.value.loc + self.key_loc

    @property
    def path(self) -> KeyPath:
        """The key decomposed into `KeyComponent` parts (any nesting depth)."""
        return KeyPath.parse(self.key)


@dataclass
class Namelist:
    """
    One ``&name ... /`` namelist group from a .nml file like `"tao.init"`.

    Attributes
    ----------
    lines : list[str]
        The verbatim source lines of the block, including the ``&name``
        opener and ``/`` terminator; the source of truth for rendering.
    assignments : list[Assignment]
        Derived from ``lines`` and refreshed after every edit.
    filename : pathlib.Path or None
        The source filename, if applicable.
    start_line : int
        The absolute, 0-indexed line of the ``&name`` opener in the source file.
    continues_line : bool
        The group opened mid-line: ``lines[0]`` is the source line from the
        opener onward, and rendering the file glues it onto the previous
        item's last line instead of starting a new one. Column locations on
        that first line are relative to the slice.
    """

    name: str
    # Warning: you must call `_reparse()` if this is edited in-place.
    lines: list[str] = field(default_factory=list)
    assignments: list[Assignment] = field(default_factory=list)
    filename: pathlib.Path | None = None
    start_line: int = 0
    continues_line: bool = False
    # (line index into ``lines``, column) of the terminator ('/' or
    # '&end'/'$end'), or None.
    _terminator: tuple[int, int] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._reparse()

    def _reparse(self) -> None:
        scan = _scan_namelist(self.lines, filename=self.filename, base_line=self.start_line)
        self.assignments = scan.assignments
        self._terminator = scan.terminator

    @property
    def loc(self) -> Location:
        """Source location spanning the whole ``&name ... /`` block."""
        end_line = self.start_line + max(len(self.lines) - 1, 0)
        end_column = len(self.lines[-1]) if self.lines else 0
        return Location(
            filename=self.filename,
            line=self.start_line,
            column=0,
            end_line=end_line,
            end_column=end_column,
        )

    def get(self, key: str) -> Assignment | None:
        """Return the assignment matching ``key`` (case/space-insensitive)."""
        target = _normalize_key(key)
        for assignment in self.assignments:
            # Assignment keys are whitespace-normalized at parse time.
            if assignment.key.lower() == target:
                return assignment
        return None

    def _indent(self) -> str:
        """Indentation to use for inserted lines, mirroring existing entries."""
        for assignment in self.assignments:
            line = self.lines[assignment.span.line - self.start_line]
            if line.lstrip().startswith(("&", "$")):
                continue  # assignments on the opener line carry no useful indent
            return line[: len(line) - len(line.lstrip())]
        return "  "

    def _insert_before_terminator(self, new_line: str) -> None:
        if self._terminator is None:
            self.lines.append(new_line)
            return
        index, column = self._terminator
        line = self.lines[index]
        if line[:column].strip():
            # One-line group: split the code before the terminator onto its
            # own line.
            self.lines[index : index + 1] = [line[:column].rstrip(), new_line, line[column:]]
        else:
            self.lines.insert(index, new_line)

    def set(self, key: str, value: str, *, comment: str = "") -> Assignment:
        """
        Update ``key``'s value in place, or append it before the terminator.

        A value that continues across several lines is collapsed onto its
        first line (interior comments on those lines are dropped with them).
        When appending a new key, embedded newlines in ``value`` insert the
        continuation lines verbatim (e.g. a follow-on comment-only line).
        """
        existing = self.get(key)
        if existing is not None:
            loc = existing.value.loc
            first = loc.line - self.start_line
            last = loc.end_line - self.start_line
            spliced = self.lines[first][: loc.column] + value + self.lines[last][loc.end_column :]
            self.lines[first : last + 1] = spliced.split("\n")
        else:
            new_line = f"{self._indent()}{key} = {value}"
            if comment:
                if not comment.lstrip().startswith("!"):
                    comment = f"!{comment}"
                new_line = f"{new_line} {comment}"
            for line in reversed(new_line.split("\n")):
                self._insert_before_terminator(line)

        self._reparse()
        return cast(Assignment, self.get(key))

    def remove(self, key: str) -> None:
        """
        Remove ``key``'s assignment, including continuation lines (no-op if absent).

        Lines the assignment shares with the opener, the terminator, or another
        assignment are spliced rather than deleted.
        """
        existing = self.get(key)
        if existing is None:
            return
        span = existing.span
        first = span.line - self.start_line
        last = span.end_line - self.start_line
        others = [a for a in self.assignments if a is not existing]

        def shared(index: int) -> bool:
            absolute = index + self.start_line
            return any(a.span.line <= absolute <= a.span.end_line for a in others)

        for index in range(last, first - 1, -1):
            line = self.lines[index]
            protected = (
                index == 0
                or (self._terminator is not None and self._terminator[0] == index)
                or shared(index)
            )
            if not protected:
                del self.lines[index]
                continue
            start = span.column if index == first else 0
            end = span.end_column if index == last else len(line)
            while end < len(line) and line[end] in " \t,":
                end += 1
            remainder = (line[:start] + line[end:]).rstrip()
            if remainder:
                self.lines[index] = remainder
            else:
                del self.lines[index]
        self._reparse()

    def render(self, options: NamelistFormatOptions | None = None) -> str:
        """
        Render the group's source lines.

        With ``options`` given, fields are re-indented, cased, and aligned per
        those options; otherwise the verbatim source lines are returned.
        """
        if options is None:
            return "\n".join(self.lines)
        return "\n".join(_format_group_lines(self.lines, options))


@dataclass
class NamelistFile:
    """A parsed namelist file: an ordered list of groups and raw text chunks."""

    # Namelists and strings between those namelists:
    items: list[Namelist | str] = field(default_factory=list)

    filename: pathlib.Path | None = None

    @classmethod
    def parse(cls, text: str, filename: pathlib.Path | str | None = None) -> Self:
        path = pathlib.Path(filename) if filename is not None else None
        items: list[Namelist | str] = []
        raw: list[str] = []
        current: Namelist | None = None

        def flush_raw() -> None:
            if raw:
                items.append("\n".join(raw))
                raw.clear()

        def close() -> None:
            nonlocal current
            if current is not None:
                current._reparse()
                items.append(current)
                current = None

        open_quote: str | None = None
        for idx, line in enumerate(text.split("\n")):
            # A line may host raw text, several groups, or both (gfortran
            # scans the character stream): consume it left to right.
            pos = 0  # column where the unconsumed text begins
            line_origin = 0  # slice origin of the active group's line here
            closed: Namelist | None = None  # group closed earlier on this line
            closed_origin = 0
            while True:
                if current is None:
                    rest = line[pos:]
                    # Outside a group, '!' comments out the rest of the line
                    # (no quote semantics apply out here).
                    match = _RE_GROUP_ANYWHERE.search(rest.split("!", 1)[0])
                    if match is None:
                        if closed is None and pos == 0:
                            raw.append(line)
                        # Otherwise the remainder stays verbatim in the
                        # closed group's last line.
                        break
                    col = pos + match.start()
                    continues = True
                    if closed is not None:
                        # A new group follows on the same line: the closed
                        # group keeps the line only up to this opener. Its
                        # parse is unaffected (scanning stopped at its
                        # terminator), so no reparse is needed.
                        closed.lines[-1] = line[closed_origin:col]
                    elif line[:col].strip():
                        raw.append(line[:col])  # junk before a mid-line opener
                    else:
                        continues = False  # only whitespace precedes: own the line
                    flush_raw()
                    line_origin = col if continues else 0
                    current = Namelist(
                        name=match.group()[1:],
                        lines=[line[line_origin:]],
                        filename=path,
                        start_line=idx,
                        continues_line=continues,
                    )
                    # Skip the opener token so a group named "end" is not
                    # read as its own terminator.
                    scan_start = pos + match.end()
                else:
                    current.lines.append(line)
                    line_origin = 0
                    scan_start = 0
                # '/' or '&end'/'$end' terminates the group anywhere outside
                # a quoted string -- including one continued from a previous
                # line -- even on the opener line.
                terminator, open_quote = _scan_line_state(line[scan_start:], open_quote)
                if terminator is None:
                    break
                closed, closed_origin = current, line_origin
                close()
                pos = scan_start + terminator + 1
        close()
        flush_raw()
        return cls(items=items, filename=path)

    @classmethod
    def from_file(cls, path: pathlib.Path | str) -> Self:
        path = pathlib.Path(path)
        return cls.parse(path.read_text(), filename=path)

    def _render_with_options(self, options: NamelistFormatOptions) -> str:
        out: list[str] = []
        for index, item in enumerate(self.items):
            if isinstance(item, Namelist):
                out.append(item.render(options))
                if options.blank_line_after_group and index < len(self.items) - 1:
                    out.append("")
                continue
            lines = item.split("\n")
            if (
                options.blank_line_after_group
                and index > 0
                and isinstance(self.items[index - 1], Namelist)
            ):
                # The separating blank was just added above; drop the source's
                # own leading blanks so runs collapse to one.
                while lines and not lines[0].strip():
                    lines.pop(0)
            out.extend(lines)
        text = "\n".join(out)
        if text and not text.endswith("\n"):
            text += "\n"
        return text

    def render(self, options: NamelistFormatOptions | None = None) -> str:
        """
        Render the whole Namelist file.

        Without ``options`` the source is reproduced verbatim. When specified,
        the output Namelist file will be formatted according to the provided
        options.
        """
        if options is None:
            parts: list[str] = []
            for item in self.items:
                if parts and not (isinstance(item, Namelist) and item.continues_line):
                    parts.append("\n")
                parts.append(item.render() if isinstance(item, Namelist) else item)
            return "".join(parts)
        return self._render_with_options(options)

    @property
    def namelists(self) -> list[Namelist]:
        return [item for item in self.items if isinstance(item, Namelist)]

    @property
    def namelists_by_name(self) -> dict[str, list[Namelist]]:
        """Namelist groups keyed by (lowercased) name; a name may repeat."""
        result: dict[str, list[Namelist]] = {}
        for namelist in self.namelists:
            result.setdefault(namelist.name.lower(), []).append(namelist)
        return result

    def get_namelist(self, name: str, index: int = 0) -> Namelist | None:
        """The ``index``-th namelist named ``name`` (case-insensitive), or ``None``."""
        matches = self.namelists_by_name.get(name.lower(), [])
        if -len(matches) <= index < len(matches):
            return matches[index]
        return None

    def update_namelist(
        self,
        name: str,
        assignments: dict[str, str],
        *,
        index: int = 0,
    ) -> Namelist:
        """
        Add/update a namelist section.

        Parameters
        ----------
        name : str
            The namelist group name.
        assignments : dict[str, str]
            ``key -> raw value`` entries to set. Existing keys are updated in
            place; missing keys are appended before the terminator.
        index : int, optional
            When several groups share ``name``, which one to update. Ignored
            when creating a new group. Defaults to the first.

        Returns
        -------
        Namelist
            The updated or newly created group.
        """
        name = name.removeprefix("&").removeprefix("$")
        target = self.get_namelist(name, index)
        if target is None:
            target = Namelist(name=name, lines=[f"&{name}", "/"])

            if self.items:
                last_item = self.items[-1]
                if isinstance(last_item, Namelist) or last_item.strip():
                    self.items.append("")

            self.items.append(target)
        for key, value in assignments.items():
            target.set(key, value)
        return target


@dataclass
class NamelistArrayEntry:
    """
    One indexed entry of a namelist array-of-derived-type.

    Tao packs an array such as ``datum`` or ``var`` two ways, and both are
    merged here:

    * anonymously/positionally --- ``datum(1) = 'orbit.x' '' '' 'END\\2' ...``,
      whose values fill :data:`FIELDS` in declaration order;
    * by component --- ``datum(1)%ele_name = 'END\\2'``.

    An explicit component takes precedence over the same positional slot.

    Attributes
    ----------
    index : int or None
        The ``i`` in ``name(i)``. ``0`` is the conventional slot Tao reads for
        ``SEARCH:``/``SAME:`` element specifications; ``None`` for a
        non-integer subscript (e.g. a range).
    positional : list[Token]
        Values from an anonymous ``name(i) = ...`` assignment, in field order.
    components : dict[str, Token]
        Values from ``name(i)%field = ...`` assignments, keyed by field name.
    comment : str
        Trailing comment on the anonymous assignment, if any.
    """

    #: Component names, in declaration order, that a positional assignment fills.
    FIELDS: ClassVar[tuple[str, ...]] = ()

    index: int | None
    positional: list[Token] = field(default_factory=list)
    components: dict[str, Token] = field(default_factory=dict)
    comment: str = ""

    def get(self, name: str) -> Token | None:
        """The raw (quoted, if a string) value token for ``name``, or ``None``."""
        name = name.lower()
        if name in self.components:
            return self.components[name]
        if name in self.FIELDS:
            position = self.FIELDS.index(name)
            if position < len(self.positional):
                token = self.positional[position]
                # A null value (``,,`` or ``r*``) leaves the field unset;
                # an explicitly blank string is the distinct token ``''``.
                return token if str(token) else None
        return None

    def value(self, name: str) -> Token | None:
        """
        The value token for ``name``, unquoted.

        ``None`` if unset; an empty (``''``) token if explicitly blank. The
        returned token keeps its source `Location`.
        """
        token = self.get(name)
        return unquote_value(token.strip()) if token is not None else None


@dataclass
class NamelistArrayGroup:
    """
    Base for a namelist group that carries an indexed array of derived types.

    Subclasses wrap a single `latform._namelist.Namelist` (e.g. a
    ``&tao_d1_data`` or ``&tao_var`` block), exposing its scalar settings and
    the parsed array entries.
    """

    namelist: Namelist

    def _scalar(self, key: str) -> Token | None:
        assignment = self.namelist.get(key)
        return unquote_value(assignment.value.strip()) if assignment is not None else None

    def _entries(self, array_name: str, entry_cls: type[NamelistArrayEntry]) -> list:
        """
        Parse ``array_name(i)`` positional/component assignments into entries.

        A Fortran array-section component assignment,
        ``array_name(a:b)%field = v_a, v_b, ...``, is expanded: the values are
        distributed across ``field`` of entries ``a`` through ``b`` in order.
        """
        array_name = array_name.lower()
        by_index: dict[object, NamelistArrayEntry] = {}

        def entry_for(key: object, index: int | None) -> NamelistArrayEntry:
            existing = by_index.get(key)
            if existing is None:
                existing = entry_cls(index=index)
                by_index[key] = existing
            return existing

        for assignment in self.namelist.assignments:
            path = assignment.path
            if path.names[0] != array_name:
                continue
            component = path.components[0]
            indices = component.indices

            # An open-ended section ``name(a:)`` or ``name(:)`` takes its
            # extent from the number of supplied values.
            if indices is None and len(path.components) > 1:
                open_slice = component.open_slice
                if open_slice is not None:
                    start, step = open_slice
                    indices = [start + i * step for i in range(len(assignment.values))]

            # An empty array section (e.g. an ascending ``5:3`` slice) designates
            # no elements, so the assignment is a no-op.
            if indices is not None and not indices:
                continue

            # Array-section component assignment: distribute the values across
            # the designated indices (e.g. ``var(1:6)%ele_name = a, b, ...``).
            if len(path.components) > 1 and indices is not None and len(indices) > 1:
                field_name = path.names[1]
                for value, index in zip(assignment.values, indices):
                    entry_for(index, index).components[field_name] = value
                continue

            # Single element (``name(i)`` or a one-index section), else a
            # non-enumerable subscript (or none) keyed by its raw text.
            if indices is not None and len(indices) == 1:
                key = index = indices[0]
            else:
                index = None
                key = component.index_text
            entry = entry_for(key, index)
            if len(path.components) == 1:
                entry.positional = list(assignment.values)
                entry.comment = assignment.comment
            else:
                entry.components[path.names[1]] = assignment.value

        def sort_key(key: object) -> tuple[int, object]:
            return (0, key) if isinstance(key, int) else (1, str(key))

        return [by_index[key] for key in sorted(by_index, key=sort_key)]
