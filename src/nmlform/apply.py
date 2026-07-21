"""
Value interpolation and templating for namelist files.

These build on the lossless `NamelistFile` tree: values are applied by editing
the source in place (existing keys spliced, missing keys appended before the
terminator), so untouched text is preserved verbatim unless a
`NamelistFormatOptions` is supplied to reformat the output.
"""

from __future__ import annotations

from .namelist import NamelistFile
from .types import NamelistFormatOptions

__all__ = [
    "apply_namelist_values",
    "interpolate_namelist",
    "split_namelist_key",
]


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
