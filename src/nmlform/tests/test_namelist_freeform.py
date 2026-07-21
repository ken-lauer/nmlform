"""Free-form namelist input: continued values, shared lines, inline terminators, quoting."""

from __future__ import annotations

import pathlib
from typing import ClassVar

import pytest

from ..namelist import (
    Namelist,
    NamelistArrayEntry,
    NamelistArrayGroup,
    NamelistFile,
    _find_comment_index,
    _scan_line_state,
    _scan_namelist,
    quote_value,
    unquote_value,
)
from ..token import Token
from ..types import NamelistFormatOptions

FILES = pathlib.Path(__file__).resolve().parent / "files" / "tao_init"
FREEFORM = FILES / "freeform.init"


# A minimal, domain-neutral schema exercising the positional/component array
# hook (`NamelistArrayEntry.FIELDS` + `NamelistArrayGroup._entries`).
class _Datum(NamelistArrayEntry):
    FIELDS: ClassVar[tuple[str, ...]] = (
        "data_type",
        "ele_ref_name",
        "ele_start_name",
        "ele_name",
        "merit_type",
        "meas",
        "weight",
    )


class _Var(NamelistArrayEntry):
    FIELDS: ClassVar[tuple[str, ...]] = ("ele_name", "attribute")


class _D1Data(NamelistArrayGroup):
    @property
    def name(self) -> Token | None:
        return self._scalar("d1_data%name")

    @property
    def datums(self) -> list[_Datum]:
        return self._entries("datum", _Datum)


class _VarGroup(NamelistArrayGroup):
    @property
    def variables(self) -> list[_Var]:
        return self._entries("var", _Var)


def _d1_data(path: pathlib.Path) -> _D1Data:
    return _D1Data(NamelistFile.from_file(path).get_namelist("tao_d1_data"))


def _var_group(path: pathlib.Path) -> _VarGroup:
    return _VarGroup(NamelistFile.from_file(path).get_namelist("tao_var"))


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("/", 0),
        ("  /", 2),
        ("  x = 1 /", 8),
        ("&g x = 1 /", 9),
        ("'a / b' /", 8),
        ("  file = 'a/b'", None),
        ("  ! a comment with a /", None),
        ("  x = 1 ! /", None),
        ("  x = a(1/2)", None),  # '/' inside a subscript does not terminate
    ],
)
def test_find_terminator(line: str, expected: int | None):
    assert _scan_line_state(line, None)[0] == expected


@pytest.mark.parametrize(
    "code",
    [
        "  datum(1) = 'orbit.x' '' '' 'END\\2' 'target' 0 1e1",
        "  var(1 : 6)%ele_name = 'a', 'b'",
        "  datum (1) = 'x'",
        "  a % b = 1",
        "  a %b = 1  c% d = 2",
        "  x = 6*'beginning' 3*0 2*'a','b'",
        "  x = a(1/2) / ignored",
        "  s = 'it''s' \"d\"\"q\" 'unterminated",
        "  file='sub/c.lat.bmad'",
        "&g x = 1 /",
        "  x = 1, 2,",
        "      3",
        "  a*'q' 12* 'q' -1.5e-3",
        "",
        "   ",
        "  x = (1.0, 2.0)",
        "  x = 1,\n, 2",  # an embedded newline acts as a blank
    ],
)
def test_lex_line_matches_scan_line(code: str):
    from ..namelist import _lex_line, _scan_line

    assert _lex_line(code) == list(_scan_line(code))


def test_lex_line_matches_scan_line_on_corpus():
    from ..namelist import _lex_line, _scan_line, _split_comment

    for path in FILES.glob("**/*.init"):
        for line in path.read_text().splitlines():
            code, _ = _split_comment(line)
            assert _lex_line(code) == list(_scan_line(code)), line


def test_scan_multiple_pairs_per_line():
    scan = _scan_namelist(["&g", "  y = 2  z = 3", "/"])
    assert [(a.key, str(a.value)) for a in scan.assignments] == [("y", "2"), ("z", "3")]


def test_scan_repeat_count_merges_with_quote():
    scan = _scan_namelist(["&g", "  x = 2*'a' 'b'", "/"])
    (assignment,) = scan.assignments
    assert [str(v) for v in assignment.values] == ["'a'", "'a'", "'b'"]


def test_scan_doubled_quote_escape():
    scan = _scan_namelist(["&g", "  s = 'it''s'", "/"])
    (assignment,) = scan.assignments
    assert str(assignment.value) == "'it''s'"
    assert [str(v) for v in assignment.values] == ["'it''s'"]


def test_continuation_values_joined_and_located():
    source = "&g\n  x = 4, 5,\n      6\n/\n"
    (group,) = NamelistFile.parse(source).namelists
    (assignment,) = group.assignments
    assert assignment.key == "x"
    assert [str(v) for v in assignment.values] == ["4", "5", "6"]
    assert str(assignment.value) == "4, 5\n6"
    assert assignment.value.loc.line == 1
    assert assignment.value.loc.end_line == 2
    for value in assignment.values:
        assert value.loc.get_string(source) == str(value)


def test_continued_quoted_string_is_not_a_phantom_assignment():
    (group,) = NamelistFile.parse("&g\n  s = 'a',\n      'x = y'\n/\n").namelists
    (assignment,) = group.assignments
    assert assignment.key == "s"
    assert [str(v) for v in assignment.values] == ["'a'", "'x = y'"]


def test_interior_comment_on_continuation_line():
    (group,) = NamelistFile.parse("&g\n  x = 1, ! part one\n      2\n/\n").namelists
    (assignment,) = group.assignments
    assert assignment.comment == "part one"
    assert [str(v) for v in assignment.values] == ["1", "2"]


def test_multiline_string_keeps_continuation_whitespace():
    scan = _scan_namelist(["&g", "  a = 'abc", "       def'", "/"])
    (assignment,) = scan.assignments
    assert str(assignment.value) == "'abc\n       def'"
    (value,) = assignment.values
    assert str(value) == "'abc\n       def'"
    assert value.loc.line == 1
    assert value.loc.end_line == 2
    assert scan.terminator == (3, 0)


def test_multiline_string_spanning_three_lines():
    scan = _scan_namelist(["&g", "  a = 'one", "two", "  three'", "/"])
    (assignment,) = scan.assignments
    assert str(assignment.value) == "'one\ntwo\n  three'"
    assert [str(v) for v in assignment.values] == ["'one\ntwo\n  three'"]


def test_multiline_string_bang_is_content_not_comment():
    scan = _scan_namelist(["&g", "  a = 'abc", "  d!ef' ! note", "/"])
    (assignment,) = scan.assignments
    assert str(assignment.value) == "'abc\n  d!ef'"
    assert assignment.comment == "note"


def test_multiline_string_slash_is_content_not_terminator():
    source = "&g\n  a = 'abc\n  d/ef'\n/\n"
    nml = NamelistFile.parse(source)
    (group,) = nml.namelists
    (assignment,) = group.assignments
    assert str(assignment.value) == "'abc\n  d/ef'"
    assert group._terminator == (3, 0)
    assert nml.render() == source


def test_multiline_string_followed_by_assignment_on_close_line():
    scan = _scan_namelist(["&g", "a = 'one", "two' b = 3", "/"])
    a, b = scan.assignments
    assert (a.key, str(a.value)) == ("a", "'one\ntwo'")
    assert (b.key, str(b.value)) == ("b", "3")


def test_format_keeps_multiline_string_record_verbatim():
    source = "&g\n  x=1\n  a = 'abc\n       def'\n/"
    (group,) = NamelistFile.parse(source).namelists
    rendered = group.render(NamelistFormatOptions())
    assert "  a = 'abc\n       def'" in rendered
    assert "x = 1" in rendered


@pytest.mark.parametrize("terminator", ["&end", "&END", "$end", "$End"])
def test_amp_end_terminates_group(terminator: str):
    source = f"&g\n  x = 1\n{terminator}\n&h\n  y = 2\n/\n"
    nml = NamelistFile.parse(source)
    assert [n.name for n in nml.namelists] == ["g", "h"]
    assert str(nml.namelists[0].get("x").value) == "1"
    assert nml.render() == source


def test_amp_end_inline_after_values():
    scan = _scan_namelist(["&g", "  x = 1 &end"])
    assert [(a.key, str(a.value)) for a in scan.assignments] == [("x", "1")]
    assert scan.terminator == (1, 8)


def test_amp_endx_is_not_a_terminator():
    assert _scan_line_state("  x = &endx", None) == (None, None)


def test_amp_end_inside_strings_is_content():
    (group,) = NamelistFile.parse("&g\n  s = 'a &end b'\n/\n").namelists
    assert str(group.get("s").value) == "'a &end b'"

    (group,) = NamelistFile.parse("&g\n  s = 'one\n &end two'\n/\n").namelists
    assert str(group.get("s").value) == "'one\n &end two'"


def test_group_named_end_is_not_self_terminating():
    (group,) = NamelistFile.parse("&end\n  x = 1\n/\n").namelists
    assert group.name == "end"
    assert str(group.get("x").value) == "1"


def test_set_inserts_before_amp_end_terminator():
    (group,) = NamelistFile.parse("&g\n  x = 1\n&end\n").namelists
    group.set("y", "2")
    assert group.render() == "&g\n  x = 1\n  y = 2\n&end"


def test_midline_opener_after_raw_text():
    source = "leading junk &g\n  x = 1\n/\n"
    nml = NamelistFile.parse(source)
    (group,) = nml.namelists
    assert group.name == "g"
    assert group.continues_line
    assert group.lines[0] == "&g"
    assert str(group.get("x").value) == "1"
    raw = [item for item in nml.items if isinstance(item, str)]
    assert raw[0] == "leading junk "
    assert nml.render() == source


def test_two_groups_on_one_line():
    source = "&a x = 1 / &b y = 2 /\n"
    nml = NamelistFile.parse(source)
    assert [n.name for n in nml.namelists] == ["a", "b"]
    assert str(nml.namelists[0].get("x").value) == "1"
    assert str(nml.namelists[1].get("y").value) == "2"
    assert nml.render() == source


def test_junk_after_terminator_stays_with_closed_group():
    source = "&a x = 1 / junk &b\n  y = 2\n/\n"
    nml = NamelistFile.parse(source)
    a, b = nml.namelists
    assert a.lines == ["&a x = 1 / junk "]
    assert str(b.get("y").value) == "2"
    assert nml.render() == source


def test_amp_end_then_new_group_on_one_line():
    source = "&a x = 1 &end &b y = 2 /\n"
    nml = NamelistFile.parse(source)
    assert [n.name for n in nml.namelists] == ["a", "b"]
    assert nml.render() == source


@pytest.mark.parametrize(
    "source",
    [
        "! &g\ntext\n",  # opener inside a comment outside any group
        "&a x = 1 / ! &b\n",  # ...or after a close on the same line
    ],
)
def test_opener_inside_comment_does_not_open(source: str):
    nml = NamelistFile.parse(source)
    assert [n.name for n in nml.namelists] == ([] if source.startswith("!") else ["a"])
    assert nml.render() == source


def test_set_on_midline_group():
    nml = NamelistFile.parse("&a x = 1 / &b y = 2 /\n")
    nml.namelists[1].set("z", "3")
    assert nml.render() == "&a x = 1 / &b y = 2\n  z = 3\n/\n"


def test_format_promotes_midline_group_to_own_line():
    out = NamelistFile.parse("junk &g x=1 /\n").render(NamelistFormatOptions())
    assert out == "junk \n&g\n  x = 1\n/\n"


def test_dollar_group_opener_and_format_preserves_sigil():
    source = "$g\n  x = 1\n$END\n"
    nml = NamelistFile.parse(source)
    (group,) = nml.namelists
    assert group.name == "g"
    assert nml.render() == source

    (group,) = NamelistFile.parse("$g x=1 $end\n").namelists
    assert group.render(NamelistFormatOptions()) == "$g\n  x = 1\n$end"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("  x = 1,,3", ["1", "", "3"]),
        ("  x = ,5", ["", "5"]),
        ("  x = 1,,", ["1", ""]),
        ("  x = 1,\n,", ["1", ""]),
        ("  x = 1, 2", ["1", "2"]),  # single commas are plain separators
        ("  x = 3* 5", ["", "", "", "5"]),  # bare repeat count: that many nulls
        ("  x = 2*, 7", ["", "", "7"]),
        ("  s = 'a,,b'", ["'a,,b'"]),  # commas inside strings are content
    ],
)
def test_null_values(line: str, expected: list[str]):
    scan = _scan_namelist(["&g", line, "/"])
    (assignment,) = scan.assignments
    assert [str(v) for v in assignment.values] == expected


# Expectations verified against gfortran 15 (element positions observed via
# sentinel arrays): the separator gap carries across record boundaries, so
# an end-of-record between commas acts as a blank and does not cancel a null.
@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (["  x = 1,", "      ,3"], ["1", "", "3"]),
        (["  x = 1,", "      2"], ["1", "2"]),  # plain continuation: no null
        (["  x = ,", ","], ["", ""]),  # both commas in the '='-gap are nulls
        (["  x = ,", ", 5"], ["", "", "5"]),
        (["  x = ,", ",", "5"], ["", "", "5"]),
        (["  x = 1,", ", ,4"], ["1", "", "", "4"]),
    ],
)
def test_null_values_across_lines(lines: list[str], expected: list[str]):
    scan = _scan_namelist(["&g", *lines, "/"])
    (assignment,) = scan.assignments
    assert [str(v) for v in assignment.values] == expected


def test_null_belongs_to_previous_assignment():
    scan = _scan_namelist(["&g", "  x = 1,, y = 2", "/"])
    assert [(a.key, [str(v) for v in a.values]) for a in scan.assignments] == [
        ("x", ["1", ""]),
        ("y", ["2"]),
    ]


def test_null_values_round_trip_and_format():
    source = "&g\n  x = ,,3\n  y = 1,,\n/\n"
    nml = NamelistFile.parse(source)
    assert nml.render() == source
    rendered = nml.namelists[0].render(NamelistFormatOptions())
    assert "x = ,,3" in rendered
    assert "y = 1,," in rendered


class _Entry(NamelistArrayEntry):
    FIELDS = ("f1", "f2", "f3")


def test_null_positional_slot_leaves_field_unset():
    group = NamelistArrayGroup(Namelist(name="t", lines=["&t", "  d(1) = 'a',,'c'", "/"]))
    (entry,) = group._entries("d", _Entry)
    assert str(entry.get("f1")) == "'a'"
    assert entry.get("f2") is None
    assert str(entry.get("f3")) == "'c'"


def test_open_section_defaults_and_step_expand_entries():
    group = NamelistArrayGroup(
        Namelist(
            name="t",
            lines=["&t", "  d(:)%f1 = 'a' 'b' 'c'", "  d(2::2)%f2 = 'p' 'q'", "/"],
        )
    )
    entries = group._entries("d", _Entry)
    assert [e.index for e in entries] == [1, 2, 3, 4]
    assert [str(e.components["f1"]) for e in entries if "f1" in e.components] == [
        "'a'",
        "'b'",
        "'c'",
    ]
    assert [(e.index, str(e.components["f2"])) for e in entries if "f2" in e.components] == [
        (2, "'p'"),
        (4, "'q'"),
    ]


def test_empty_rhs_keeps_following_assignment():
    (group,) = NamelistFile.parse("&g\n  x =\n  y = 1\n/\n").namelists
    assert [(a.key, str(a.value)) for a in group.assignments] == [("x", ""), ("y", "1")]


def test_group_ends_at_inline_terminator_rest_is_raw():
    source = "&g\n  x = 1 /\nafter_group_text\n"
    nml = NamelistFile.parse(source)
    (group,) = nml.namelists
    assert [(a.key, str(a.value)) for a in group.assignments] == [("x", "1")]
    raw = [item for item in nml.items if isinstance(item, str)]
    assert any("after_group_text" in chunk for chunk in raw)
    assert nml.render() == source


def test_opener_line_assignments_parsed():
    source = "&g x = 1 /\nafter\n"
    nml = NamelistFile.parse(source)
    (group,) = nml.namelists
    assert [(a.key, str(a.value)) for a in group.assignments] == [("x", "1")]
    assert nml.render() == source


def test_set_collapses_multiline_value_without_orphans():
    nml = NamelistFile.parse("&g\n  x = 1, 2, 3,\n      4, 5, 6\n  y = 7\n/\n")
    (group,) = nml.namelists
    group.set("x", "99")
    assert group.render() == "&g\n  x = 99\n  y = 7\n/"
    # A reparse of the rendered text reads back exactly one value.
    (reparsed,) = NamelistFile.parse(nml.render()).namelists
    assert [str(v) for v in reparsed.get("x").values] == ["99"]


def test_set_single_line_value_is_unchanged_behavior():
    nml = NamelistFile.parse("&g\n  x = 1  ! keep me\n/\n")
    (group,) = nml.namelists
    group.set("x", "42")
    assert group.render() == "&g\n  x = 42  ! keep me\n/"


def test_set_appends_into_one_line_group():
    nml = NamelistFile.parse("&g x = 1 /\n")
    (group,) = nml.namelists
    group.set("y", "2")
    assert group.render() == "&g x = 1\n  y = 2\n/"
    assert str(group.get("x").value) == "1"
    assert str(group.get("y").value) == "2"


def test_set_multiline_replacement_value():
    nml = NamelistFile.parse("&g\n  x = 1\n/\n")
    (group,) = nml.namelists
    group.set("x", "'a',\n      'b'")
    assert group.render() == "&g\n  x = 'a',\n      'b'\n/"
    assert [str(v) for v in group.get("x").values] == ["'a'", "'b'"]


def test_remove_multiline_value_removes_all_lines():
    nml = NamelistFile.parse("&g\n  x = 1, 2,\n      3\n  y = 7\n/\n")
    (group,) = nml.namelists
    group.remove("x")
    assert group.render() == "&g\n  y = 7\n/"


def test_remove_one_pair_from_shared_line_keeps_other():
    nml = NamelistFile.parse("&g\n  y = 2  z = 3\n/\n")
    (group,) = nml.namelists
    group.remove("z")
    assert group.render() == "&g\n  y = 2\n/"

    nml = NamelistFile.parse("&g\n  y = 2, z = 3\n/\n")
    (group,) = nml.namelists
    group.remove("y")
    assert group.render() == "&g\n  z = 3\n/"


def test_remove_assignment_from_one_line_group_keeps_group():
    nml = NamelistFile.parse("&g a = 1 /\n")
    (group,) = nml.namelists
    group.remove("a")
    assert group.render() == "&g /"
    assert group.assignments == []


def test_interpolate_namelist_on_wrapped_value():
    from ..apply import interpolate_namelist

    source = "&g\n  x = 1, 2,\n      3\n/\n"
    out = interpolate_namelist(source, values={"g": {"x": "9"}})
    assert out == "&g\n  x = 9\n/\n"


def test_freeform_wrapped_positional_datum():
    datums = _d1_data(FREEFORM).datums
    assert [d.index for d in datums] == [1, 2]
    first = datums[0]
    assert first.value("data_type") == "orbit.x"
    assert first.value("ele_ref_name") == ""
    assert first.value("ele_name") == "END\\2"
    assert first.value("merit_type") == "target"
    assert first.value("meas") == "0"
    assert first.value("weight") == "1e1"
    assert first.comment == "continues below"
    assert datums[1].value("data_type") == "orbit.y"


def test_freeform_slice_distribution_across_wrapped_values():
    variables = _var_group(FREEFORM).variables
    assert [v.index for v in variables] == [1, 2, 3]
    assert [str(v.value("ele_name")) for v in variables] == ["Q1", "Q2", "Q3"]
    assert [str(v.value("attribute")) for v in variables] == ["k1", "k1", "k1"]


def test_freeform_pairs_on_one_line():
    nml = NamelistFile.from_file(FREEFORM)
    group = nml.get_namelist("tao_var")
    assert str(group.get("default_weight").value) == "1e1"
    assert str(group.get("default_step").value) == "1e-4"


def test_freeform_one_liner_and_raw_text():
    nml = NamelistFile.from_file(FREEFORM)
    group = nml.get_namelist("one_liner")
    assert group is not None
    assert [(a.key, str(a.value)) for a in group.assignments] == [
        ("a", "1"),
        ("b", "'has = / chars'"),
    ]
    raw = [item for item in nml.items if isinstance(item, str)]
    assert any("raw text after the one-liner group" in chunk for chunk in raw)


def test_freeform_strings_group():
    nml = NamelistFile.from_file(FREEFORM)
    group = nml.get_namelist("strings")
    values = {a.key: str(a.value) for a in group.assignments}
    assert values == {"s1": "'it''s'", "s2": "'a / b'", "s3": "'x'\n'x = y'"}


def test_format_wrapped_record_keeps_wrapping():
    from ..apply import interpolate_namelist
    from ..types import NamelistFormatOptions

    src = "&g\n  x = 1, 2,\n        3\n  yy = 4\n/\n"
    out = interpolate_namelist(src, options=NamelistFormatOptions())
    # Continuation values re-align under the first value character.
    assert out == "&g\n  x = 1, 2,\n      3\n  yy = 4\n/\n"


def test_format_one_line_group_expands():
    from ..apply import interpolate_namelist
    from ..types import NamelistFormatOptions

    out = interpolate_namelist("&one a = 1  b = 2 /\n", options=NamelistFormatOptions())
    assert out == "&one\n  a = 1\n  b = 2\n/\n"


def test_format_never_rewrites_quoted_equals():
    from ..apply import interpolate_namelist
    from ..types import NamelistFormatOptions

    src = "&g\n  s = 'a',\n      'x=y'\n/\n"
    out = interpolate_namelist(src, options=NamelistFormatOptions())
    assert out == src  # 'x=y' is string content, not an assignment


def test_format_aligns_continuation_comments():
    from ..apply import interpolate_namelist
    from ..types import NamelistFormatOptions

    src = "&g\n  x = 1, ! one\n      2  ! two\n/\n"
    out = interpolate_namelist(src, options=NamelistFormatOptions())
    assert out == "&g\n  x = 1,  ! one\n      2   ! two\n/\n"


def test_format_preserves_text_after_terminator():
    from ..apply import interpolate_namelist
    from ..types import NamelistFormatOptions

    out = interpolate_namelist("&g x = 1 / trailing\n", options=NamelistFormatOptions())
    assert out == "&g\n  x = 1\n/ trailing\n"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("'it''s'", "it's"),
        ('"say ""hi"""', 'say "hi"'),
        ("''''", "'"),
        ("''", ""),
        ('"don\'t"', "don't"),
        ("'a''''b'", "a''b"),
        ("'a\"\"b'", 'a""b'),  # non-delimiter quotes are literal, not escapes
        ("'abc", "'abc"),  # unterminated: returned unchanged
        ("bare", "bare"),
        ("1.5e-3", "1.5e-3"),
    ],
)
def test_unquote_value(text: str, expected: str):
    assert str(unquote_value(Token(text))) == expected


def test_unquote_value_keeps_location_and_comments():
    from ..comments import Comments
    from ..location import Location

    token = Token(
        "'it''s'",
        loc=Location(filename=pathlib.Path("x.init"), line=3, column=7),
        comments=Comments(inline=Token("c")),
    )
    unquoted = unquote_value(token)
    assert unquoted.loc == token.loc
    assert unquoted.comments == token.comments


@pytest.mark.parametrize(
    ("text", "quote", "expected"),
    [
        ("it's", "'", "'it''s'"),
        ('say "hi"', '"', '"say ""hi"""'),
        ("plain", "'", "'plain'"),
        ("", "'", "''"),
        ("'", "'", "''''"),
        ('say "hi"', "'", "'say \"hi\"'"),
    ],
)
def test_quote_value(text: str, quote: str, expected: str):
    assert quote_value(text, quote) == expected


def test_quote_value_rejects_bad_quote():
    with pytest.raises(ValueError):
        quote_value("x", quote="`")


@pytest.mark.parametrize("quote", ["'", '"'])
@pytest.mark.parametrize("text", ["", "plain", "it's", 'say "hi"', "both ' and \" here", "''"])
def test_quote_unquote_round_trip(text: str, quote: str):
    assert str(unquote_value(Token(quote_value(text, quote)))) == text


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("x = 1 ! c", 6),  # fast path: no quotes before the '!'
        ("s = 'it''s ! x' ! real", 16),
        ("x = '''' ! c", 9),
        ('t = "say ""hi!"" " ! c', 19),
        ("x = 'abc ! unterminated", None),
        ("no comment here", None),
    ],
)
def test_find_comment_index_with_escaped_quotes(line: str, expected: int | None):
    assert _find_comment_index(line) == expected


ESCAPED_QUOTES_INIT = '''\
&tao_d1_data
  d1_data%name = 'it\'\'s'
  datum(1)%ele_name = "say ""hi"""
  datum(2) = 'orbit.x' \'\' \'\' 'Q\'\'1' 'target' 0 1e1
/
'''


def test_group_values_unescape_quotes():
    (namelist,) = NamelistFile.parse(ESCAPED_QUOTES_INIT).namelists
    group = _D1Data(namelist)
    assert str(group.name) == "it's"
    first, second = group.datums
    assert str(first.value("ele_name")) == 'say "hi"'
    assert str(second.value("ele_name")) == "Q'1"
    assert str(second.value("ele_ref_name")) == ""


def test_render_preserves_escaped_quotes():
    nml = NamelistFile.parse(ESCAPED_QUOTES_INIT)
    assert nml.render() == ESCAPED_QUOTES_INIT


def test_format_freeform_is_idempotent():
    from ..apply import interpolate_namelist
    from ..types import NamelistFormatOptions

    options = NamelistFormatOptions(align_equals=True)
    once = interpolate_namelist(FREEFORM.read_text(), options=options)
    twice = interpolate_namelist(once, options=options)
    assert once == twice
    # The formatted output still reads back with identical field values.
    before = NamelistFile.parse(FREEFORM.read_text())
    after = NamelistFile.parse(once)
    key = lambda nml: [  # noqa: E731
        [str(v) for v in a.values] for group in nml.namelists for a in group.assignments
    ]
    assert key(after) == key(before)
