"""
Value interpolation and templating for namelist files.

These build on the lossless `NamelistFile` tree: values are applied by editing
the source in place (existing keys spliced, missing keys appended before the
terminator), so untouched text is preserved verbatim unless a
`NamelistFormatOptions` is supplied to reformat the output.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys

from .namelist import NamelistFile, quote_value
from .types import NamelistFormatOptions

logger = logging.getLogger(__name__)

__all__ = [
    "apply_namelist_values",
    "cli_main_set",
    "interpolate_namelist",
    "load_values_file",
    "split_namelist_key",
]

_VALUES_FORMATS = ("json", "yaml", "toml", "nml")
_VALUES_SUFFIXES = {
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".nml": "nml",
    ".init": "nml",
}


def split_namelist_key(key: str) -> tuple[str, int]:
    """
    Split a ``namelists`` override key into ``(name, index)``.

    A trailing ``#N`` (1-based) targets the N-th group of a repeated name, e.g.
    ``tao_d1_data#2`` -> ``("tao_d1_data", 1)``. A bare name targets the first.
    """
    if "#" in key:
        name, _, suffix = key.rpartition("#")
        return name, int(suffix) - 1
    return key, 0


def apply_namelist_values(nml_file: NamelistFile, values: dict) -> None:
    """
    Apply a values mapping to a parsed namelist file in place.

    Parameters
    ----------
    nml_file : NamelistFile
        A parsed namelist file.
    values : dict
        Keys are namelist group names, optionally with a ``name#N`` suffix (1-based)
        to target the N-th of a repeated group.
        Each value is a ``{key: value}`` mapping of raw assignment values;
        existing keys are updated in place and
        missing keys are appended.
        A value of ``None`` removes that key.
        A group named only for removals that does not exist is left uncreated.
    """
    for name_key, assignments in values.items():
        name, index = split_namelist_key(name_key)
        removals = [key for key, value in assignments.items() if value is None]
        settings = {key: str(value) for key, value in assignments.items() if value is not None}
        if settings:
            target = nml_file.update_namelist(name, settings, index=index)
        else:
            target = nml_file.get_namelist(name, index)
        if target is not None:
            for key in removals:
                target.remove(key)


def interpolate_namelist(
    contents: str,
    *,
    values: dict | None = None,
    filename: str = "tao.init",
    options: NamelistFormatOptions | None = None,
) -> str:
    """
    Interpolate a single namelist (``*.init``/``*.nml``) template file.

    Parameters
    ----------
    contents : str
        The namelist file contents.
    values : dict, optional
        Namelist overrides. See `apply_namelist_values`.
    filename : str, optional
        Virtual filename used for source locations.
    options : NamelistFormatOptions, optional
        When given, re-format the output (field indentation, case, and
        alignment). When ``None`` (default), the source layout is preserved
        verbatim aside from the applied value edits.

    Returns
    -------
    str
        The interpolated namelist file.
    """
    nml_file = NamelistFile.parse(contents, filename)
    if values:
        apply_namelist_values(nml_file, values)
    return nml_file.render(options)


def _to_namelist_value(value: object) -> str:
    """
    Render a structured (JSON/YAML/TOML) scalar as a raw namelist value.

    Strings become quoted Fortran string literals; booleans become ``.true.``/
    ``.false.``; numbers are emitted bare; a list/tuple becomes a
    space-separated value list.
    """
    if isinstance(value, bool):  # bool is an int subclass; check it first
        return ".true." if value else ".false."
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return quote_value(value)
    if isinstance(value, list | tuple):
        return " ".join(_to_namelist_value(item) for item in value)
    raise TypeError(f"Cannot render {type(value).__name__} as a namelist value: {value!r}")


def _normalize_structured(data: object) -> dict[str, dict[str, str | None]]:
    """
    Coerce a parsed JSON/YAML/TOML mapping into an `apply_namelist_values` dict.

    The top level maps namelist group names (optionally ``name#N``) to
    ``{key: value}`` mappings. Each value is converted with `_to_namelist_value`;
    a ``None`` (JSON ``null``) value is kept as a removal marker.
    """
    if not isinstance(data, dict):
        raise ValueError("values file must be a mapping of namelist group -> {key: value}")
    result: dict[str, dict[str, str | None]] = {}
    for group, fields in data.items():
        if not isinstance(fields, dict):
            raise ValueError(f"group {group!r} must map to a mapping of key -> value")
        result[str(group)] = {
            str(key): (None if value is None else _to_namelist_value(value))
            for key, value in fields.items()
        }
    return result


def _values_from_nml(text: str, filename: str) -> dict[str, dict[str, str | None]]:
    """
    Read overrides from a namelist source file, group by group and field by field.

    Each group contributes its assignments as raw value strings (copied
    verbatim). Repeated group names are disambiguated with a ``name#N`` suffix
    (1-based) matching `split_namelist_key`.
    """
    nml_file = NamelistFile.parse(text, filename)
    result: dict[str, dict[str, str | None]] = {}
    counts: dict[str, int] = {}
    for namelist in nml_file.namelists:
        name = namelist.name.lower()
        counts[name] = counts.get(name, 0) + 1
        group_key = name if counts[name] == 1 else f"{name}#{counts[name]}"
        result[group_key] = {
            assignment.key: str(assignment.value) for assignment in namelist.assignments
        }
    return result


def _detect_values_format(source: str) -> str:
    """The values format for ``source``, from its extension (``-`` stdin -> json)."""
    if source == "-":
        return "json"
    suffix = pathlib.Path(source).suffix.lower()
    fmt = _VALUES_SUFFIXES.get(suffix)
    if fmt is None:
        raise ValueError(
            f"Cannot infer values format from {source!r}; pass --values-format "
            f"({', '.join(_VALUES_FORMATS)})."
        )
    return fmt


def load_values_file(source: str, fmt: str | None = None) -> dict[str, dict[str, str | None]]:
    """
    Load a values mapping from ``source`` for `apply_namelist_values`.

    Parameters
    ----------
    source : str
        A path, or ``-`` to read from standard input.
    fmt : {"json", "yaml", "toml", "nml"}, optional
        The file format. When ``None`` (default), it is inferred from the file
        extension (``-`` defaults to JSON). ``yaml`` and ``toml`` need the
        optional parsers (``pip install nmlform[all]``); on Python 3.11+ the
        stdlib ``tomllib`` is used for TOML.

    Returns
    -------
    dict
        A ``{group: {key: value_or_None}}`` mapping of raw namelist values,
        suitable for `apply_namelist_values`.
    """
    fmt = fmt or _detect_values_format(source)
    text = sys.stdin.read() if source == "-" else pathlib.Path(source).read_text(encoding="utf-8")

    if fmt == "json":
        import json

        return _normalize_structured(json.loads(text))
    if fmt == "yaml":
        try:
            import yaml
        except ImportError as ex:  # optional dependency
            raise ImportError(
                "Reading YAML values requires 'pyyaml' (pip install nmlform[all])."
            ) from ex
        return _normalize_structured(yaml.safe_load(text))
    if fmt == "toml":
        try:
            import tomllib
        except ImportError:  # Python 3.10: tomllib was released as tomli
            try:
                import tomli as tomllib
            except ImportError as ex:  # optional dependency
                raise ImportError(
                    "Reading TOML values on Python 3.10 requires 'tomli' "
                    "(pip install nmlform[all])."
                ) from ex
        return _normalize_structured(tomllib.loads(text))
    if fmt == "nml":
        parse_name = "namelist" if source == "-" else source
        return _values_from_nml(text, parse_name)
    raise ValueError(f"Unknown values format: {fmt!r}")


_SET_DESCRIPTION = """
`nmlform-set` command-line tool.

Reads a Fortran-namelist file, sets and/or removes one or more values, and
writes the result to standard output (or to a file with ``--output``, or back to
the input file with ``--in-place``). Use ``-`` as the filename to read from
standard input.

Values may come from repeated ``--set``/``--remove`` options and/or ``--values``
files (JSON, YAML, TOML, or another namelist file). In JSON/YAML/TOML a string
becomes a quoted Fortran string, numbers and booleans become Fortran literals,
a list becomes a value list, and ``null`` removes the key; a namelist values
file copies each field's raw value verbatim. Later sources win, and
``--set``/``--remove`` win over ``--values``.

The source layout is preserved verbatim aside from the edits, unless
``--reformat`` is given, in which case the formatting options are applied.
""".strip()


def _merge_group_values(
    base: dict[str, dict[str, str | None]],
    incoming: dict[str, dict[str, str | None]],
) -> None:
    """Merge ``incoming`` group values into ``base`` in place; ``incoming`` wins."""
    for group, fields in incoming.items():
        base.setdefault(group, {}).update(fields)


def _collect_cli_overrides(
    sets: list[tuple[str, str, str]],
    removes: list[tuple[str, str]],
) -> dict[str, dict[str, str | None]]:
    """
    Fold ``--set``/``--remove`` options into an `apply_namelist_values` mapping.

    Later options win. A key named in both is removed. A group targeted by a
    trailing ``#N`` (1-based) selects the N-th group of a repeated name.
    """
    values: dict[str, dict[str, str | None]] = {}
    for namelist, key, value in sets:
        values.setdefault(namelist, {})[key] = value
    for namelist, key in removes:
        values.setdefault(namelist, {})[key] = None
    return values


def _build_set_argparser() -> argparse.ArgumentParser:
    from . import main
    from ._version import __version__ as package_version

    parser = argparse.ArgumentParser(
        prog="nmlform-set",
        description=_SET_DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter,
    )
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
        "filename",
        metavar="FILE",
        help="Namelist file to modify; use '-' to read from standard input.",
    )
    parser.add_argument(
        "--set",
        nargs=3,
        metavar=("NAMELIST", "KEY", "VALUE"),
        action="append",
        default=[],
        dest="set_",
        help="Set KEY to the raw VALUE in group NAMELIST (use 'NAMELIST#N' for the "
        "N-th of a repeated group); repeatable.",
    )
    parser.add_argument(
        "--remove",
        nargs=2,
        metavar=("NAMELIST", "KEY"),
        action="append",
        default=[],
        dest="remove_",
        help="Remove KEY from group NAMELIST; repeatable.",
    )
    parser.add_argument(
        "--values",
        action="append",
        default=[],
        metavar="FILE",
        dest="values_files",
        help="Read overrides from FILE (JSON/YAML/TOML, or a namelist file); '-' "
        "reads from standard input. Repeatable; later files win.",
    )
    parser.add_argument(
        "--values-format",
        choices=_VALUES_FORMATS,
        default=None,
        help="Force the --values format (default: infer from the file extension; "
        "'-' defaults to json).",
    )
    parser.add_argument(
        "--reformat",
        action="store_true",
        help="Reformat the whole file with the formatting options below "
        "(default: preserve the source layout aside from the edits).",
    )

    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--output",
        "-o",
        help="Write the result to this file (default: standard output).",
    )
    output.add_argument(
        "--in-place",
        "-i",
        action="store_true",
        help="Rewrite the input file in place.",
    )

    main.add_format_arguments(parser)
    return parser


def main_set(argv: list[str] | None = None) -> int:
    """
    Set/remove namelist values from the command line.

    Parameters
    ----------
    argv : list of str, optional
        Command-line arguments to parse; defaults to ``sys.argv``.

    Returns
    -------
    int
        A process exit status: ``0`` on success, ``2`` on a usage error or if
        the file could not be read or parsed.
    """
    from . import main

    parsed = _build_set_argparser().parse_args(args=argv)

    logging.basicConfig()
    logging.getLogger("nmlform").setLevel(parsed.log_level)

    if parsed.in_place and parsed.filename == "-":
        logger.error("Cannot use --in-place with standard input ('-').")
        return 2
    if not parsed.set_ and not parsed.remove_ and not parsed.values_files:
        logger.error("Nothing to do: pass at least one --set, --remove, or --values.")
        return 2
    if parsed.filename == "-" and "-" in parsed.values_files:
        logger.error("Cannot read both the namelist file and --values from standard input.")
        return 2

    try:
        if parsed.filename == "-":
            contents = sys.stdin.read()
        else:
            contents = pathlib.Path(parsed.filename).read_text(encoding="utf-8")
    except OSError as ex:
        logger.error("Could not read %s: %s", parsed.filename, ex)
        return 2

    values: dict[str, dict[str, str | None]] = {}
    try:
        for source in parsed.values_files:
            _merge_group_values(values, load_values_file(source, parsed.values_format))
    except (OSError, ValueError, ImportError) as ex:
        logger.error("Could not load values: %s", ex)
        return 2
    _merge_group_values(values, _collect_cli_overrides(parsed.set_, parsed.remove_))
    options = main.build_format_options(parsed) if parsed.reformat else None
    parse_name = "namelist" if parsed.filename == "-" else parsed.filename

    try:
        result = interpolate_namelist(contents, values=values, filename=parse_name, options=options)
    except Exception:
        logger.exception("Failed to update %s", parsed.filename)
        return 2

    if parsed.in_place:
        pathlib.Path(parsed.filename).write_text(result, encoding="utf-8")
        logger.info("Wrote %s", parsed.filename)
    elif parsed.output:
        pathlib.Path(parsed.output).write_text(result, encoding="utf-8")
        logger.info("Wrote %s", parsed.output)
    else:
        sys.stdout.write(result)
    return 0


def cli_main_set(argv: list[str] | None = None) -> int:
    """CLI entrypoint for ``nmlform-set`` (set/remove values in one file)."""
    return main_set(argv)


if __name__ == "__main__":
    sys.exit(cli_main_set())
