"""
`nmlform` command-line tool.

Reads Fortran-namelist files, reformats each with a shared set of layout
options, and writes the result to standard output (or back to the file with
``--in-place``). Use ``-`` as a filename to read from standard input.
"""

from __future__ import annotations

import argparse
import difflib
import logging
import sys

from .namelist import NamelistFile
from .types import NamelistFormatOptions

DESCRIPTION = __doc__
logger = logging.getLogger(__name__)


def _read_source(filename: str) -> str:
    """Read the text of ``filename``, treating ``-`` as standard input."""
    if filename == "-":
        return sys.stdin.read()
    with open(filename, encoding="utf-8") as fp:
        return fp.read()


def _unified_diff(source: str, formatted: str, filename: str) -> str:
    """A unified diff turning ``source`` into ``formatted`` for ``filename``."""
    name = "<stdin>" if filename == "-" else filename
    diff = difflib.unified_diff(
        source.splitlines(keepends=True),
        formatted.splitlines(keepends=True),
        fromfile=f"{name}\t(original)",
        tofile=f"{name}\t(reformatted)",
    )
    return "".join(diff)


def main(
    filenames: list[str],
    options: NamelistFormatOptions,
    *,
    in_place: bool = False,
    check: bool = False,
    diff: bool = False,
) -> int:
    """
    Reformat each file in ``filenames`` per ``options``.

    Parameters
    ----------
    filenames : list of str
        Namelist files to reformat; ``-`` reads from standard input.
    options : NamelistFormatOptions
        Layout options applied to every file.
    in_place : bool, optional
        Rewrite each file with its reformatted text instead of printing it.
        Not valid for standard input (``-``).
    check : bool, optional
        Do not write anything; exit with a non-zero status if any file would
        be changed by reformatting.
    diff : bool, optional
        Do not write anything; print a unified diff of the changes reformatting
        would make. Like ``check``, exits non-zero if any file would change.

    Returns
    -------
    int
        A process exit status: ``0`` on success, ``1`` if ``check``/``diff``
        found a file that would change, ``2`` if a file could not be read or
        parsed.
    """
    if in_place and "-" in filenames:
        logger.error("Cannot use --in-place with standard input ('-').")
        return 2

    would_change = False
    had_error = False
    for filename in filenames:
        try:
            source = _read_source(filename)
        except OSError as ex:
            logger.error("Could not read %s: %s", filename, ex)
            had_error = True
            continue
        try:
            parse_name = None if filename == "-" else filename
            formatted = NamelistFile.parse(source, filename=parse_name).render(options)
        except Exception:
            logger.exception("Failed to reformat %s", filename)
            had_error = True
            continue

        changed = formatted != source
        would_change = would_change or changed

        if diff:
            if changed:
                sys.stdout.write(_unified_diff(source, formatted, filename))
                logger.info("Would reformat %s", filename)
            continue

        if check:
            if changed:
                logger.info("Would reformat %s", filename)
            continue

        if in_place:
            if changed:
                with open(filename, "w", encoding="utf-8") as fp:
                    fp.write(formatted)
                logger.info("Reformatted %s", filename)
            continue

        sys.stdout.write(formatted)

    if had_error:
        return 2
    if (check or diff) and would_change:
        return 1
    return 0


def _build_argparser() -> argparse.ArgumentParser:
    """
    Build the argument parser for the command-line application.

    For help, see the :mod:`argparse` documentation.
    """
    parser = argparse.ArgumentParser(
        prog="nmlform",
        description=DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter,
    )

    from ._version import __version__ as package_version

    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=package_version,
        help="Show the nmlform version number and exit.",
    )
    parser.add_argument(
        "--log",
        "-l",
        dest="log_level",
        default="WARNING",
        type=str,
        help="Python logging level (e.g. DEBUG, INFO, WARNING).",
    )

    parser.add_argument(
        "filenames",
        metavar="FILE",
        nargs="+",
        help="Namelist file(s) to reformat; use '-' to read from standard input.",
    )

    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--in-place",
        "-i",
        action="store_true",
        help="Rewrite each file in place instead of writing to standard output.",
    )
    output.add_argument(
        "--check",
        action="store_true",
        help="Do not write anything; exit non-zero if any file would be reformatted.",
    )
    output.add_argument(
        "--diff",
        action="store_true",
        help="Do not write anything; print a unified diff of the changes and exit "
        "non-zero if any file would be reformatted.",
    )

    fmt = parser.add_argument_group("formatting options")
    fmt.add_argument(
        "--indent-size",
        type=int,
        default=2,
        help="Number of indent characters per level (default: 2).",
    )
    fmt.add_argument(
        "--tabs",
        action="store_true",
        help="Indent with tabs instead of spaces.",
    )
    fmt.add_argument(
        "--field-case",
        choices=("lower", "upper", "same"),
        default="lower",
        help="Case to apply to field names (default: lower).",
    )
    fmt.add_argument(
        "--align-equals",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Align '=' signs within each run of assignments.",
    )
    fmt.add_argument(
        "--align-comments",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Align trailing '!' comments within each run of assignments.",
    )
    fmt.add_argument(
        "--blank-line-after-group",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Emit a blank line after each namelist group.",
    )

    return parser


def cli_main(args: list[str] | None = None) -> int:
    """
    CLI entrypoint.

    Parameters
    ----------
    args : list of str, optional
        Command-line arguments to parse; defaults to ``sys.argv``.

    Returns
    -------
    int
        The process exit status (see :func:`main`).
    """
    parsed = _build_argparser().parse_args(args=args)

    logging.basicConfig()
    logging.getLogger("nmlform").setLevel(parsed.log_level)

    options = NamelistFormatOptions(
        indent_size=parsed.indent_size,
        indent_char="\t" if parsed.tabs else " ",
        field_case=parsed.field_case,
        align_equals=parsed.align_equals,
        align_comments=parsed.align_comments,
        blank_line_after_group=parsed.blank_line_after_group,
    )
    return main(
        parsed.filenames,
        options,
        in_place=parsed.in_place,
        check=parsed.check,
        diff=parsed.diff,
    )


if __name__ == "__main__":
    sys.exit(cli_main())
