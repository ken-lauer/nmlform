"""Tests for the ``nmlform`` command-line entrypoint."""

from __future__ import annotations

import pathlib

import pytest

from ..main import cli_main

MESSY = "&plot a=1  bb = 2.0 /\n"
FORMATTED = "&plot\n  a  = 1\n  bb = 2.0\n/\n"


@pytest.fixture
def sample(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "example.nml"
    path.write_text(MESSY)
    return path


def test_reformats_to_stdout(sample: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main([str(sample)]) == 0
    assert capsys.readouterr().out == FORMATTED
    assert sample.read_text() == MESSY  # source untouched


def test_reads_stdin(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(MESSY))
    assert cli_main(["-"]) == 0
    assert capsys.readouterr().out == FORMATTED


def test_in_place_rewrites_file(sample: pathlib.Path) -> None:
    assert cli_main(["--in-place", str(sample)]) == 0
    assert sample.read_text() == FORMATTED


def test_check_reports_change(sample: pathlib.Path) -> None:
    assert cli_main(["--check", str(sample)]) == 1
    assert sample.read_text() == MESSY  # unchanged by --check


def test_check_passes_when_formatted(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "clean.nml"
    path.write_text(FORMATTED)
    assert cli_main(["--check", str(path)]) == 0


def test_diff_reports_change(sample: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["--diff", str(sample)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("--- ")
    assert "-&plot a=1  bb = 2.0 /" in out
    assert "+  a  = 1" in out
    assert sample.read_text() == MESSY  # unchanged by --diff


def test_diff_empty_when_formatted(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "clean.nml"
    path.write_text(FORMATTED)
    assert cli_main(["--diff", str(path)]) == 0
    assert capsys.readouterr().out == ""


def test_in_place_rejects_stdin() -> None:
    assert cli_main(["--in-place", "-"]) == 2


def test_missing_file_errors(tmp_path: pathlib.Path) -> None:
    assert cli_main([str(tmp_path / "nope.nml")]) == 2


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (["--indent-size", "4"], "&plot\n    a  = 1\n    bb = 2.0\n/\n"),
        (["--no-align-equals"], "&plot\n  a = 1\n  bb = 2.0\n/\n"),
        (["--field-case", "upper"], "&plot\n  A  = 1\n  BB = 2.0\n/\n"),
    ],
)
def test_formatting_flags(
    sample: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    flags: list[str],
    expected: str,
) -> None:
    assert cli_main([*flags, str(sample)]) == 0
    assert capsys.readouterr().out == expected
