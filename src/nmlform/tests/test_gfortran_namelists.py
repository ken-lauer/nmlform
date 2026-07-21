"""
Parser tests ported from GCC's ``gfortran.dg/namelist_*.f90`` regression suite.

Brought over to nmlform by way of Claude, as you might have expected.

Each case feeds the namelist *input text* embedded in a gfortran regression
test to :meth:`NamelistFile.parse` and checks the parsed groups, keys, and
value tokens. Only gfortran tests that carry reusable input text are ported:
compile-only diagnostics, runtime error-reporting checks, and pure
write-then-read round trips (where the input is produced by gfortran's own
namelist *writer*, not present literally) have nothing for a parser to consume
and are catalogued in :data:`SKIPPED` for the record.

Value tokens are compared exactly as the parser yields them: quoted strings
keep their quotes, Fortran repeat counts (``3*0``) are expanded, and complex
literals ``(re,im)`` are single tokens.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from ..namelist import NamelistFile

# gfortran tests with no input text a parser can consume, kept for traceability.
# Skipped tests:
# SKIPPED = {
#     "compile-error": [
#         "namelist_1",
#         "namelist_2",
#         "namelist_3",
#         "namelist_4",
#         "namelist_5",
#         "namelist_25",
#         "namelist_30",
#         "namelist_31",
#         "namelist_32",
#         "namelist_33",
#         "namelist_34",
#         "namelist_35",
#         "namelist_36",
#         "namelist_62",
#         "namelist_63",
#         "namelist_74",
#         "namelist_75",
#         "namelist_76",
#         "namelist_83",
#         "namelist_83_2",
#         "namelist_91",
#         "namelist_92",
#         "namelist_93",
#         "namelist_94",
#         "namelist_98",
#         "namelist_args",
#         "namelist_assumed_char",
#     ],
#     "roundtrip-writer": [
#         "namelist_13",
#         "namelist_14",
#         "namelist_18",
#         "namelist_29",
#         "namelist_38",
#         "namelist_53",
#         "namelist_57",
#         "namelist_65",
#         "namelist_69",
#         "namelist_70",
#         "namelist_84",
#         "namelist_95",
#         "namelist_internal",
#     ],
#     "runtime-error-report": [
#         "namelist_19",
#         "namelist_40",
#         "namelist_47",
#         "namelist_68",
#         "namelist_89",
#         "namelist_97",
#         "namelist_100",
#         "namelist_101",
#     ],
# }

# The 61-character namelist object name from namelist_39.f90.
_LONG = "b01234567890123456789012345678901234567890123456789012345678901"


class Case(NamedTuple):
    """One ported gfortran namelist input and its expected parse."""

    origin: str
    source: str
    # (group name, [(assignment key, [value token, ...]), ...]) per group, in order.
    groups: list[tuple[str, list[tuple[str, list[str]]]]]
    xfail: str | None = None


CASES: list[Case] = [
    # namelist_16: complex scalars, space-separated assignments, inline terminator.
    Case(
        "namelist_16",
        "&mynml z(1)=(5.,6.) z(2)=(7.,8.) /\n",
        [("mynml", [("z(1)", ["(5.,6.)"]), ("z(2)", ["(7.,8.)"])])],
    ),
    # namelist_17: logical values.
    Case(
        "namelist_17",
        "&mynml l = F T /\n",
        [("mynml", [("l", ["F", "T"])])],
    ),
    # namelist_20: explicit-shape array with negative subscripts; four groups, one stream.
    Case(
        "namelist_20",
        "&a x(-5)=0 /\n&a x(-1)=0 /\n&a x(1:2)=0 /\n&a x(-4:-2)= -4,-3,-2 /\n",
        [
            ("a", [("x(-5)", ["0"])]),
            ("a", [("x(-1)", ["0"])]),
            ("a", [("x(1:2)", ["0"])]),
            ("a", [("x(-4:-2)", ["-4", "-3", "-2"])]),
        ],
    ),
    # namelist_21: char array filled across lines; legacy '&end' terminator.
    Case(
        "namelist_21",
        "&ccsopr\n"
        "    namea='spi01h','spi02o','spi03h','spi04o','spi05h',\n"
        "          'spi07o','spi08h','spi09h',\n"
        "    nameb='spi01h','spi03h','spi05h','spi06h','spi08h',\n"
        "&end\n",
        [
            (
                "ccsopr",
                [
                    (
                        "namea",
                        [
                            "'spi01h'",
                            "'spi02o'",
                            "'spi03h'",
                            "'spi04o'",
                            "'spi05h'",
                            "'spi07o'",
                            "'spi08h'",
                            "'spi09h'",
                        ],
                    ),
                    ("nameb", ["'spi01h'", "'spi03h'", "'spi05h'", "'spi06h'", "'spi08h'"]),
                ],
            )
        ],
    ),
    # namelist_22: same as _21 but space-separated values.
    Case(
        "namelist_22",
        "&ccsopr\n"
        "    namea='spi01h' 'spi02o' 'spi03h' 'spi04o' 'spi05h'\n"
        "          'spi07o' 'spi08h' 'spi09h'\n"
        "    nameb='spi01h' 'spi03h' 'spi05h' 'spi06h' 'spi08h'\n"
        "&end\n",
        [
            (
                "ccsopr",
                [
                    (
                        "namea",
                        [
                            "'spi01h'",
                            "'spi02o'",
                            "'spi03h'",
                            "'spi04o'",
                            "'spi05h'",
                            "'spi07o'",
                            "'spi08h'",
                            "'spi09h'",
                        ],
                    ),
                    ("nameb", ["'spi01h'", "'spi03h'", "'spi05h'", "'spi06h'", "'spi08h'"]),
                ],
            )
        ],
    ),
    # namelist_23: incomplete logical/int arrays. Two of the file's three streams.
    Case(
        "namelist_23:stream1",
        " &mynml\n"
        " truely       = trouble,    traffic .true\n"
        " truely_a_very_long_variable_name  = 4,      4,      4\n"
        " /\n",
        [
            (
                "mynml",
                [
                    ("truely", ["trouble", "traffic", ".true"]),
                    ("truely_a_very_long_variable_name", ["4", "4", "4"]),
                ],
            )
        ],
    ),
    Case(
        "namelist_23:stream2",
        " &mynml\n"
        " truely       = .true., .true.,\n"
        " truely_a_very_long_variable_name  = 4,      4,      4\n"
        " /\n",
        [
            (
                "mynml",
                [
                    ("truely", [".true.", ".true."]),
                    ("truely_a_very_long_variable_name", ["4", "4", "4"]),
                ],
            )
        ],
    ),
    # namelist_24: repeat counts, multi-dim subscripts, strided sections, repeated key.
    Case(
        "namelist_24",
        "&MYNML\n"
        "NAMES = 25*'0'\n"
        "NAMES2 = 25*'0'\n"
        "NAMES3 = 25*'0'\n"
        "NAMES(2,2) = 'frogger'\n"
        "NAMES(1,1) = 'E123' 'E456' 'D789' 'P135' 'P246'\n"
        "NAMES2(1:5:2,2) = 'abcde' 'fghij' 'klmno'\n"
        "NAMES3 = 'E123' 'E456' 'D789' 'P135' 'P246' '0' 'frogger'\n"
        "/\n",
        [
            (
                "mynml",
                [
                    ("NAMES", ["'0'"] * 25),
                    ("NAMES2", ["'0'"] * 25),
                    ("NAMES3", ["'0'"] * 25),
                    ("NAMES(2,2)", ["'frogger'"]),
                    ("NAMES(1,1)", ["'E123'", "'E456'", "'D789'", "'P135'", "'P246'"]),
                    ("NAMES2(1:5:2,2)", ["'abcde'", "'fghij'", "'klmno'"]),
                    (
                        "NAMES3",
                        ["'E123'", "'E456'", "'D789'", "'P135'", "'P246'", "'0'", "'frogger'"],
                    ),
                ],
            )
        ],
    ),
    # namelist_26: a commented-out group must not be parsed.
    Case(
        "namelist_26",
        "!================\n"
        "! Namelist REPORT\n"
        "!================\n"
        "!      &REPORT use      = 'ignore'   / ! Comment\n"
        "!\n"
        " &REPORT type     = 'SYNOP'\n"
        "         use      = 'active'\n"
        "         max_proc = 20\n"
        " /\n",
        [
            (
                "report",
                [
                    ("type", ["'SYNOP'"]),
                    ("use", ["'active'"]),
                    ("max_proc", ["20"]),
                ],
            )
        ],
    ),
    # namelist_27: two groups in one stream separated by a comment line.
    Case(
        "namelist_27",
        "!================\n"
        "! Namelist REPORT\n"
        "!================\n"
        " &REPORT type     = 'SYNOP' \n"
        "         use      = 'active'\n"
        "         max_proc = 20\n"
        " /\n"
        "! Other namelists...\n"
        " &OTHER  i = 1 /\n",
        [
            (
                "report",
                [("type", ["'SYNOP'"]), ("use", ["'active'"]), ("max_proc", ["20"])],
            ),
            ("other", [("i", ["1"])]),
        ],
    ),
    # namelist_28: two consecutive groups of the same name.
    Case(
        "namelist_28",
        "&REPORT type='report1' /\n&REPORT type='report2' /\n!\n",
        [
            ("report", [("type", ["'report1'"])]),
            ("report", [("type", ["'report2'"])]),
        ],
    ),
    # namelist_37: select group by name (the six '&'-delimited groups; the file's
    # two trailing legacy '$CODE' groups are omitted — see namelist_80 for that form).
    Case(
        "namelist_37",
        "File with test NAMELIST inputs\n"
        " &CODVJS  char='VJS-Not a proper nml name', X=-0.5/\n"
        " &CODEone char='CODEone input', X=-1.0 /\n"
        " &CODEtwo char='CODEtwo inputs', X=-2.0/\n"
        " &code    char='Lower case name',X=-3.0/\n"
        " &CODE    char='Desired namelist sel', X=44./\n"
        " &CODEx   char='Should not read CODEx nml', X=-5./\n",
        [
            ("codvjs", [("char", ["'VJS-Not a proper nml name'"]), ("X", ["-0.5"])]),
            ("codeone", [("char", ["'CODEone input'"]), ("X", ["-1.0"])]),
            ("codetwo", [("char", ["'CODEtwo inputs'"]), ("X", ["-2.0"])]),
            ("code", [("char", ["'Lower case name'"]), ("X", ["-3.0"])]),
            ("code", [("char", ["'Desired namelist sel'"]), ("X", ["44."])]),
            ("codex", [("char", ["'Should not read CODEx nml'"]), ("X", ["-5."])]),
        ],
    ),
    # namelist_39: long object name with array subscripts, one value per line.
    Case(
        "namelist_39",
        "&NAM\n"
        f" {_LONG}(1)=' AAP NOOT MIES WIM ZUS JET',\n"
        f" {_LONG}(2)='SURF.PRESSURE',\n"
        f" {_LONG}(3)='APEKOOL',\n"
        " /\n",
        [
            (
                "nam",
                [
                    (f"{_LONG}(1)", ["' AAP NOOT MIES WIM ZUS JET'"]),
                    (f"{_LONG}(2)", ["'SURF.PRESSURE'"]),
                    (f"{_LONG}(3)", ["'APEKOOL'"]),
                ],
            )
        ],
    ),
    # namelist_41: legacy '&end' and '$end' terminators over two streams.
    Case(
        "namelist_41",
        " &inx\n var(1)='hello'\n &end\n $inx\n var(1)='hello'\n $end\n",
        [
            ("inx", [("var(1)", ["'hello'"])]),
            ("inx", [("var(1)", ["'hello'"])]),
        ],
    ),
    # namelist_42: 'infinity' is both a special value and the next object name; the
    # name immediately before '=' wins, so foo takes five values.
    Case(
        "namelist_42",
        " &nl foo = 5, 5, 5, nan, infinity, infinity \n\n       = 1, /\n",
        [
            (
                "nl",
                [
                    ("foo", ["5", "5", "5", "nan", "infinity"]),
                    ("infinity", ["1"]),
                ],
            )
        ],
    ),
    # namelist_43: same, with the value list spanning many blank/whitespace lines.
    Case(
        "namelist_43",
        " &nl foo(1:6) = 5, 5, 5, nan, infinity\n\n\ninfinity\n\n         \n\n=1/\n",
        [
            (
                "nl",
                [
                    ("foo(1:6)", ["5", "5", "5", "nan", "infinity"]),
                    ("infinity", ["1"]),
                ],
            )
        ],
    ),
    # namelist_44: a full comment line inside the group is skipped.
    Case(
        "namelist_44",
        " &blacklist \n"
        "   ! This is a comment within the namelist\n"
        "   file    = 'myfile'\n"
        "   default = F\n"
        " /\n",
        [("blacklist", [("file", ["'myfile'"]), ("default", ["F"])])],
    ),
    # namelist_45: blank and comment lines before the only assignment.
    Case(
        "namelist_45",
        "&nbdrive_naml\n"
        "\n"
        "!nstep_stop = 2  ! uncomment to bar\n"
        "!nstep_start = 2 ! uncomment to foo\n"
        " mhdpath = 'mypath.dat'\n"
        "/\n",
        [("nbdrive_naml", [("mhdpath", ["'mypath.dat'"])])],
    ),
    # namelist_46: repeat counts on logicals and integers.
    Case(
        "namelist_46",
        "&nbdrive_naml\nnlco = 4*T,\nxlbtna = 802.8, 802.8, 802.8, 802.8\nnbshapa = 4*1\n/\n",
        [
            (
                "nbdrive_naml",
                [
                    ("nlco", ["T", "T", "T", "T"]),
                    ("xlbtna", ["802.8", "802.8", "802.8", "802.8"]),
                    ("nbshapa", ["1", "1", "1", "1"]),
                ],
            )
        ],
    ),
    # namelist_48: tabs preceding the object name (-fbackslash -> literal tabs).
    Case(
        "namelist_48",
        "&CASEIN\n\t\tx = 1\n/\n",
        [("casein", [("x", ["1"])])],
    ),
    # namelist_49: tabs as leading and separating whitespace.
    Case(
        "namelist_49",
        "&CASEDAT\n\t\tA = 1.0,\t\tB = 2.0,\n\t\tC = 3.0,\n /\n",
        [("casedat", [("A", ["1.0"]), ("B", ["2.0"]), ("C", ["3.0"])])],
    ),
    # namelist_50: '!' comment right after the group name and right after a value.
    Case(
        "namelist_50",
        " &nml! This is a just comment\n   model='foo'! This is a just comment\n /\n",
        [("nml", [("model", ["'foo'"])])],
    ),
    # namelist_51: blank/comment lines then a value; legacy '&END' terminator.
    Case(
        "namelist_51",
        "&INPUT\n\n!\n!\n!\nnxc = 100\n&END\n",
        [("input", [("nxc", ["100"])])],
    ),
    # namelist_52: nested derived-type component keys.
    Case(
        "namelist_52",
        "&info_adjoint\nadjoint%solver_type = 'direct'\nadjoint%screen_io_fs_ntime%begin = 42\n/\n",
        [
            (
                "info_adjoint",
                [
                    ("adjoint%solver_type", ["'direct'"]),
                    ("adjoint%screen_io_fs_ntime%begin", ["42"]),
                ],
            )
        ],
    ),
    # namelist_54: array of derived type via a single-line internal file.
    Case(
        "namelist_54",
        " &namlis a%m=1,2, a%n=5,6, /\n",
        [("namlis", [("a%m", ["1", "2"]), ("a%n", ["5", "6"])])],
    ),
    # namelist_55: many component/array assignments on one (source-continued) line.
    Case(
        "namelist_55",
        " &NAMINTERP atmkey%ppp = 076,058,062,079, atmkey%nnn = 000,000,000,000,"
        " atmkey%name ='LIQUID_WATER','SOLID_WATER','SNOW','RAIN', OUTGEO%NLEV=10,"
        " AHALF=0.,1.,2.,3.,4.,5.,6.,7.,8.,9., BHALF=0.,1.,2.,3.,4.,5.,6.,7.,8.,9., /\n",
        [
            (
                "naminterp",
                [
                    ("atmkey%ppp", ["076", "058", "062", "079"]),
                    ("atmkey%nnn", ["000", "000", "000", "000"]),
                    ("atmkey%name", ["'LIQUID_WATER'", "'SOLID_WATER'", "'SNOW'", "'RAIN'"]),
                    ("OUTGEO%NLEV", ["10"]),
                    ("AHALF", ["0.", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."]),
                    ("BHALF", ["0.", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."]),
                ],
            )
        ],
    ),
    # namelist_56: double-quoted string values.
    Case(
        "namelist_56",
        '&nml str = "a", "b", "cde", j = 5 /\n',
        [("nml", [("str", ['"a"', '"b"', '"cde"']), ("j", ["5"])])],
    ),
    # namelist_58: array assignment through a derived-type component key.
    Case(
        "namelist_58",
        "  &params\n  plot_page%size=5 , 2,\n/\n",
        [("params", [("plot_page%size", ["5", "2"])])],
    ),
    # namelist_59: assignments split by space, with a trailing comment (run 2).
    Case(
        "namelist_59:values",
        "&cmd\ni=10 , j=20 k=30 ! change all three values\n/\n",
        [("cmd", [("i", ["10"]), ("j", ["20"]), ("k", ["30"])])],
    ),
    # namelist_59: comment-only body assigns nothing (run 4).
    Case(
        "namelist_59:comment-only",
        "&cmd\n! change no values\n/\n",
        [("cmd", [])],
    ),
    # namelist_60: array-of-derived-type element assignments.
    Case(
        "namelist_60",
        "&nl_setup\n"
        " field_setup%vel(1)%number=  3,\n"
        " field_setup%vel(2)%number=  9,\n"
        " field_setup%vel(3)%number=  27,\n"
        "/\n",
        [
            (
                "nl_setup",
                [
                    ("field_setup%vel(1)%number", ["3"]),
                    ("field_setup%vel(2)%number", ["9"]),
                    ("field_setup%vel(3)%number", ["27"]),
                ],
            )
        ],
    ),
    # namelist_61: array-section subscripts on the left-hand side.
    Case(
        "namelist_61:read1",
        "&nml a(1,:) = 1 2 3 /\n",
        [("nml", [("a(1,:)", ["1", "2", "3"])])],
    ),
    Case(
        "namelist_61:read3",
        "&nml a(1,:) = 1 2 3 ,     a(2,:) = 4,5,6     a(3,:) = 7 8 9/\n",
        [
            (
                "nml",
                [
                    ("a(1,:)", ["1", "2", "3"]),
                    ("a(2,:)", ["4", "5", "6"]),
                    ("a(3,:)", ["7", "8", "9"]),
                ],
            )
        ],
    ),
    # namelist_64: doubly-qualified nested component key.
    Case(
        "namelist_64",
        " &params\n  curve(1)%symbol%typee = 1234\n /\n",
        [("params", [("curve(1)%symbol%typee", ["1234"])])],
    ),
    # namelist_66: array of derived type (string + logical); second group has an
    # inline comment after the name and strings with significant trailing spaces.
    Case(
        "namelist_66:naml1",
        " &naml1\n"
        "    tracer(1)   = 'aa', .true.\n"
        "    tracer(2)   = 'bb', .true.\n"
        "    tracer(3)   = 'cc', .true.\n"
        " /\n",
        [
            (
                "naml1",
                [
                    ("tracer(1)", ["'aa'", ".true."]),
                    ("tracer(2)", ["'bb'", ".true."]),
                    ("tracer(3)", ["'cc'", ".true."]),
                ],
            )
        ],
    ),
    Case(
        "namelist_66:naml2",
        " &naml2     !   just some stuff\n"
        "    qtracer(1)   = 'dic     ' , 'dissolved inorganic concentration      ',"
        "  'mol-c/l' ,  .true.     ,  .true.,\n"
        "    qtracer(2)   = 'alkalini' , 'total alkalinity concentration         ',"
        "  'eq/l '   ,  .true.     ,  .true.,\n"
        " /\n",
        [
            (
                "naml2",
                [
                    (
                        "qtracer(1)",
                        [
                            "'dic     '",
                            "'dissolved inorganic concentration      '",
                            "'mol-c/l'",
                            ".true.",
                            ".true.",
                        ],
                    ),
                    (
                        "qtracer(2)",
                        [
                            "'alkalini'",
                            "'total alkalinity concentration         '",
                            "'eq/l '",
                            ".true.",
                            ".true.",
                        ],
                    ),
                ],
            )
        ],
    ),
    # namelist_67: well-formed input (the gfortran test checks a read-time truncation
    # warning, which is irrelevant to parsing).
    Case(
        "namelist_67",
        "&NMLIST NML_STRING='123456789' /\n",
        [("nmlist", [("NML_STRING", ["'123456789'"])])],
    ),
    # namelist_71: legacy '$' opener with comment lines before the '/' terminator.
    Case(
        "namelist_71",
        "$indata\nNFP = 5,\n!  \n! \n!  \n/\n",
        [("indata", [("NFP", ["5"])])],
    ),
    # namelist_73: two derived-type array members.
    Case(
        "namelist_73",
        "&nl_setup\n"
        " field_setup%vel(1)%number=  3,\n"
        " field_setup%vel(2)%number=  9,\n"
        " field_setup%vel(3)%number=  27,\n"
        " field_setup%scal(1)%number=  2,\n"
        " field_setup%scal(2)%number=  4,\n"
        " field_setup%scal(3)%number=  8,\n"
        "/\n",
        [
            (
                "nl_setup",
                [
                    ("field_setup%vel(1)%number", ["3"]),
                    ("field_setup%vel(2)%number", ["9"]),
                    ("field_setup%vel(3)%number", ["27"]),
                    ("field_setup%scal(1)%number", ["2"]),
                    ("field_setup%scal(2)%number", ["4"]),
                    ("field_setup%scal(3)%number", ["8"]),
                ],
            )
        ],
    ),
    # namelist_77: derived type with array components.
    Case(
        "namelist_77",
        " &error_params\n"
        "   beam_init%chars(1)='JUNK'\n"
        "   beam_init%grid(1)%n_x=3\n"
        "   beam_init%grid(1)%n_px=2\n"
        " /\n",
        [
            (
                "error_params",
                [
                    ("beam_init%chars(1)", ["'JUNK'"]),
                    ("beam_init%grid(1)%n_x", ["3"]),
                    ("beam_init%grid(1)%n_px", ["2"]),
                ],
            )
        ],
    ),
    # namelist_78: deeply nested derived-type keys.
    Case(
        "namelist_78",
        " &NMLST\n  DER%D(1)%K%J = 1,\n  DER%D(2)%K%J = 2,\n /\n",
        [("nmlst", [("DER%D(1)%K%J", ["1"]), ("DER%D(2)%K%J", ["2"])])],
    ),
    # namelist_79: scalar plus array of derived type (string + logical).
    Case(
        "namelist_79",
        " &namtoptrc\n"
        "    getal = 7\n"
        "    tracer(1) = 'DIC     ', .true.\n"
        "    tracer(2) = 'Alkalini', .true.\n"
        "    tracer(3) = 'O2      ', .true.\n"
        " /\n",
        [
            (
                "namtoptrc",
                [
                    ("getal", ["7"]),
                    ("tracer(1)", ["'DIC     '", ".true."]),
                    ("tracer(2)", ["'Alkalini'", ".true."]),
                    ("tracer(3)", ["'O2      '", ".true."]),
                ],
            )
        ],
    ),
    # namelist_80: legacy '$temp ... $END' delimiters.
    Case(
        "namelist_80",
        " ?\n\n $temp\n  int1=1\n  int2=2\n  int3=3\n $END\n",
        [("temp", [("int1", ["1"]), ("int2", ["2"]), ("int3", ["3"])])],
    ),
    # namelist_81: embedded space inside a subscript qualifier (well-formed stream).
    Case(
        "namelist_81",
        "&nml i(3 ) = 5 /\n",
        [("nml", [("i(3)", ["5"])])],
    ),
    # namelist_82: whole-array section '(:)' subscript.
    Case(
        "namelist_82",
        " &naml1\n    tracer(:)   = 'aa' , .true.\n    tracer(2)   = 'bb' , .true.\n /\n",
        [
            (
                "naml1",
                [
                    ("tracer(:)", ["'aa'", ".true."]),
                    ("tracer(2)", ["'bb'", ".true."]),
                ],
            )
        ],
    ),
    # namelist_85: type-extension components; extra spacing around values.
    Case(
        "namelist_85",
        " &TEST_NML\n TKE%X=  3.14    ,\n TKE%STRING='kf7rcc',\n ANSWER=          42,\n /\n",
        [
            (
                "test_nml",
                [
                    ("TKE%X", ["3.14"]),
                    ("TKE%STRING", ["'kf7rcc'"]),
                    ("ANSWER", ["42"]),
                ],
            )
        ],
    ),
    # namelist_86: value lists continued onto following lines.
    Case(
        "namelist_86",
        " &theList\n"
        "  mode      = 'on'\n"
        "  dogs      = 'Rover',\n"
        "              'Spot'\n"
        "  cats      = 'Fluffy',\n"
        "              'Hairball'\n"
        " /\n",
        [
            (
                "thelist",
                [
                    ("mode", ["'on'"]),
                    ("dogs", ["'Rover'", "'Spot'"]),
                    ("cats", ["'Fluffy'", "'Hairball'"]),
                ],
            )
        ],
    ),
    # namelist_87: '!' comment attached to a value with no separator (vendor extension).
    Case(
        "namelist_87",
        " &nml\n"
        "   i=42!11\n"
        "   r1=43!11\n"
        "   r2=43.!11\n"
        "   r3=inf!11\n"
        "   r4=NaN(0x33)!11\n"
        "   r5=3.e5!11\n"
        "   c=(4,2)!11\n"
        "   ll=.true.!11\n"
        "   c1='a'!11\n"
        "   c2='bc'!11\n"
        "   c3='ax'!11\n"
        " /\n",
        [
            (
                "nml",
                [
                    ("i", ["42"]),
                    ("r1", ["43"]),
                    ("r2", ["43."]),
                    ("r3", ["inf"]),
                    ("r4", ["NaN(0x33)"]),
                    ("r5", ["3.e5"]),
                    ("c", ["(4,2)"]),
                    ("ll", [".true."]),
                    ("c1", ["'a'"]),
                    ("c2", ["'bc'"]),
                    ("c3", ["'ax'"]),
                ],
            )
        ],
    ),
    # namelist_88: array element assignments.
    Case(
        "namelist_88",
        " &tab_nml\n tab(1)='in1',\n tab(2)='in2'\n /\n",
        [("tab_nml", [("tab(1)", ["'in1'"]), ("tab(2)", ["'in2'"])])],
    ),
    # namelist_96: derived-type value sequence; three groups read one at a time.
    Case(
        "namelist_96",
        " &nml chan = 1   '#1 '    10 /\n"
        " &nml chan = 2   '#2 '    42.36/\n"
        " &nml chan = 3   '#3 '    30 /\n",
        [
            ("nml", [("chan", ["1", "'#1 '", "10"])]),
            ("nml", [("chan", ["2", "'#2 '", "42.36"])]),
            ("nml", [("chan", ["3", "'#3 '", "30"])]),
        ],
    ),
    # namelist_99: three independent internal-file reads; the last renames a key.
    Case(
        "namelist_99",
        " &v z=1 tol=1/\n &v z=1 tol=1/\n &v z=1 y=1/\n",
        [
            ("v", [("z", ["1"]), ("tol", ["1"])]),
            ("v", [("z", ["1"]), ("tol", ["1"])]),
            ("v", [("z", ["1"]), ("y", ["1"])]),
        ],
    ),
    # namelist_char_only: single char value; legacy '&END' terminator.
    Case(
        "namelist_char_only",
        " &INX\n   var = 'goodbye'\n &END\n",
        [("inx", [("var", ["'goodbye'"])])],
    ),
    # namelist_empty: an explicitly empty string value.
    Case(
        "namelist_empty",
        " &INPUT\n    var=''\n /\n",
        [("input", [("var", ["''"])])],
    ),
    # namelist_use_only: two groups, distinct keys.
    Case(
        "namelist_use_only",
        " &NML1 aa='lmno' ii=1 rr=2.5 /\n &NML2 aaa='pqrs' iii=2 rrr=3.5 /\n",
        [
            ("nml1", [("aa", ["'lmno'"]), ("ii", ["1"]), ("rr", ["2.5"])]),
            ("nml2", [("aaa", ["'pqrs'"]), ("iii", ["2"]), ("rrr", ["3.5"])]),
        ],
    ),
    # namelist_use: two groups sharing key names.
    Case(
        "namelist_use",
        " &NML1 aa='lmno' ii=1 rr=2.5 /\n &NML2 aa='pqrs' ii=2 rrr=3.5 /\n",
        [
            ("nml1", [("aa", ["'lmno'"]), ("ii", ["1"]), ("rr", ["2.5"])]),
            ("nml2", [("aa", ["'pqrs'"]), ("ii", ["2"]), ("rrr", ["3.5"])]),
        ],
    ),
    # namelist_utf8: a multibyte UTF-8 string value.
    Case(
        "namelist_utf8",
        ' &nml str = "1a你好b" /\n',
        [("nml", [("str", ['"1a你好b"'])])],
    ),
    # namelist_103: derived-type array-section component with a repeat count.
    Case(
        "namelist_103",
        "&n\n ta(1:8)%c = 8*'bogus'\n/\n",
        [("n", [("ta(1:8)%c", ["'bogus'"] * 8)])],
    ),
    # namelist_102: four groups exercising trailing commas, wrapped values, comma-less
    # continuation lines, and inline '!' comments (the integer-valued variant).
    Case(
        "namelist_102",
        "&nml1\n"
        "  array = 1, 2, 3, 4,\n"
        "/\n"
        "\n"
        "&nml2\n"
        "  barray = 5,    ! comment\n"
        "           6,\n"
        "           7     ! another comment\n"
        "           8,\n"
        "/\n"
        "\n"
        "&nml3\n"
        "  carray =  9     ! New comment\n"
        "           10\n"
        "           11     ! another new comment\n"
        "           12\n"
        "/\n"
        "\n"
        "&nml4\n"
        "  darray = 13, 14, 15, 16,\n"
        "/\n",
        [
            ("nml1", [("array", ["1", "2", "3", "4"])]),
            ("nml2", [("barray", ["5", "6", "7", "8"])]),
            ("nml3", [("carray", ["9", "10", "11", "12"])]),
            ("nml4", [("darray", ["13", "14", "15", "16"])]),
        ],
    ),
    # namelist_15: arrays of derived types with nested char-array components,
    # substring qualifiers, a wrapped value list, and a null-value assignment.
    Case(
        "namelist_15",
        "&MYNML\n"
        " x = 3, 4, 'dd', 'ee', 'ff', 'gg',\n"
        "     4, 5, 'hh', 'ii', 'jj', 'kk',\n"
        " x(1)%i = , ,\n"
        " x(2)%i = -3, -4\n"
        " x(2)%m(1)%ch(2)(1:1) ='q',\n"
        " x(2)%m(2)%ch(1)(1:1) ='w',\n"
        " x(1)%m(1)%ch(1:2)(2:2) = 'z','z',\n"
        " x(2)%m(1)%ch(1:2)(2:2) = 'z','z',\n"
        " x(1)%m(2)%ch(1:2)(2:2) = 'z','z',\n"
        " x(2)%m(2)%ch(1:2)(2:2) = 'z','z',\n"
        "/\n",
        [
            (
                "mynml",
                [
                    (
                        "x",
                        [
                            "3",
                            "4",
                            "'dd'",
                            "'ee'",
                            "'ff'",
                            "'gg'",
                            "4",
                            "5",
                            "'hh'",
                            "'ii'",
                            "'jj'",
                            "'kk'",
                        ],
                    ),
                    # "= , ," is two null values: both elements are skipped.
                    ("x(1)%i", ["", ""]),
                    ("x(2)%i", ["-3", "-4"]),
                    ("x(2)%m(1)%ch(2)(1:1)", ["'q'"]),
                    ("x(2)%m(2)%ch(1)(1:1)", ["'w'"]),
                    ("x(1)%m(1)%ch(1:2)(2:2)", ["'z'", "'z'"]),
                    ("x(2)%m(1)%ch(1:2)(2:2)", ["'z'", "'z'"]),
                    ("x(1)%m(2)%ch(1:2)(2:2)", ["'z'", "'z'"]),
                    ("x(2)%m(2)%ch(1:2)(2:2)", ["'z'", "'z'"]),
                ],
            )
        ],
    ),
]


def _params() -> list:
    seen: set[str] = set()
    params = []
    for case in CASES:
        assert case.origin not in seen, f"duplicate case id {case.origin!r}"
        seen.add(case.origin)
        marks = [pytest.mark.xfail(reason=case.xfail, strict=False)] if case.xfail else []
        params.append(pytest.param(case, id=case.origin, marks=marks))
    return params


@pytest.mark.parametrize("case", _params())
def test_gfortran_namelist(case: Case):
    parsed = NamelistFile.parse(case.source).namelists
    actual = [
        (nml.name.lower(), [(a.key, [str(v) for v in a.values]) for a in nml.assignments])
        for nml in parsed
    ]
    expected = [(name.lower(), assignments) for name, assignments in case.groups]
    assert actual == expected
