"""Tests for the ``nmlform-set`` command-line entrypoint."""

from __future__ import annotations

import io
import pathlib

import pytest

from ..apply import cli_main_set

SOURCE = "&plot\n  a = 1  ! keep me\n  bb = 2.0\n/\n"


@pytest.fixture
def sample(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "example.nml"
    path.write_text(SOURCE)
    return path


def test_set_preserves_layout(sample: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main_set(["--set", "plot", "a", "42", str(sample)]) == 0
    # Only the value changes; the inline comment and spacing survive.
    assert capsys.readouterr().out == "&plot\n  a = 42  ! keep me\n  bb = 2.0\n/\n"
    assert sample.read_text() == SOURCE  # source untouched without -i/-o


def test_set_appends_missing_key(sample: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main_set(["--set", "plot", "cc", "'new'", str(sample)]) == 0
    assert "cc = 'new'" in capsys.readouterr().out


def test_remove_key(sample: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main_set(["--remove", "plot", "bb", str(sample)]) == 0
    assert "bb" not in capsys.readouterr().out


def test_set_and_remove_together(sample: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main_set(["--set", "plot", "a", "9", "--remove", "plot", "bb", str(sample)]) == 0
    out = capsys.readouterr().out
    assert "a = 9" in out
    assert "bb" not in out


def test_reformat(sample: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    sample.write_text("&plot a=1  bb=2.0 /\n")
    assert cli_main_set(["--set", "plot", "a", "42", "--reformat", str(sample)]) == 0
    assert capsys.readouterr().out == "&plot\n  a  = 42\n  bb = 2.0\n/\n"


def test_reads_stdin(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("&plot a = 1 /\n"))
    assert cli_main_set(["--set", "plot", "a", "42", "-"]) == 0
    assert capsys.readouterr().out == "&plot a = 42 /\n"


def test_in_place(sample: pathlib.Path) -> None:
    assert cli_main_set(["--in-place", "--set", "plot", "a", "7", str(sample)]) == 0
    assert sample.read_text() == "&plot\n  a = 7  ! keep me\n  bb = 2.0\n/\n"


def test_output_file(sample: pathlib.Path, tmp_path: pathlib.Path) -> None:
    out = tmp_path / "out.nml"
    assert cli_main_set(["--set", "plot", "a", "7", "-o", str(out), str(sample)]) == 0
    assert "a = 7" in out.read_text()
    assert sample.read_text() == SOURCE  # input untouched


def test_repeated_group_index(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("&g x=1 /\n&g x=2 /\n"))
    assert cli_main_set(["--set", "g#2", "x", "99", "-"]) == 0
    assert capsys.readouterr().out == "&g x=1 /\n&g x=99 /\n"


def test_nothing_to_do_errors(sample: pathlib.Path) -> None:
    assert cli_main_set([str(sample)]) == 2


def test_in_place_rejects_stdin() -> None:
    assert cli_main_set(["--in-place", "--set", "g", "x", "1", "-"]) == 2


def test_missing_file_errors(tmp_path: pathlib.Path) -> None:
    assert cli_main_set(["--set", "g", "x", "1", str(tmp_path / "nope.nml")]) == 2


def test_values_json(
    sample: pathlib.Path, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    values = tmp_path / "v.json"
    values.write_text(
        '{"plot": {"a": 42, "title": "hi", "flag": true, "arr": [1, 2, 3], "bb": null}}'
    )
    assert cli_main_set(["--values", str(values), str(sample)]) == 0
    out = capsys.readouterr().out
    assert "a = 42" in out  # number -> bare
    assert "title = 'hi'" in out  # string -> quoted
    assert "flag = .true." in out  # bool -> Fortran logical
    assert "arr = 1 2 3" in out  # list -> value list
    assert "bb" not in out  # null -> removed


def test_values_yaml(
    sample: pathlib.Path, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("yaml")
    values = tmp_path / "v.yaml"
    values.write_text("plot:\n  a: 7\n  title: hi there\n  bb: null\n")
    assert cli_main_set(["--values", str(values), str(sample)]) == 0
    out = capsys.readouterr().out
    assert "a = 7" in out
    assert "title = 'hi there'" in out
    assert "bb" not in out


def test_values_toml(
    sample: pathlib.Path, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    values = tmp_path / "v.toml"
    values.write_text('[plot]\na = 9\ntitle = "toml"\n')
    assert cli_main_set(["--values", str(values), str(sample)]) == 0
    out = capsys.readouterr().out
    assert "a = 9" in out
    assert "title = 'toml'" in out


def test_values_nml_copies_raw(
    sample: pathlib.Path, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    values = tmp_path / "v.nml"
    values.write_text("&plot\n  a = 1e-4\n  cc = 3*0.0\n/\n")
    assert cli_main_set(["--values", str(values), str(sample)]) == 0
    out = capsys.readouterr().out
    assert "a = 1e-4" in out  # raw value copied verbatim, not quoted
    assert "cc = 3*0.0" in out


def test_set_wins_over_values(
    sample: pathlib.Path, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    values = tmp_path / "v.json"
    values.write_text('{"plot": {"a": 1}}')
    assert cli_main_set(["--values", str(values), "--set", "plot", "a", "99", str(sample)]) == 0
    assert "a = 99" in capsys.readouterr().out


def test_values_format_override_for_stdin(
    sample: pathlib.Path, monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("&plot a = 5 /\n"))
    assert cli_main_set(["--values", "-", "--values-format", "nml", str(sample)]) == 0
    assert "a = 5" in capsys.readouterr().out


def test_values_unknown_extension_errors(sample: pathlib.Path, tmp_path: pathlib.Path) -> None:
    values = tmp_path / "v.txt"
    values.write_text('{"plot": {"a": 1}}')
    assert cli_main_set(["--values", str(values), str(sample)]) == 2


def test_both_stdin_errors(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert cli_main_set(["--values", "-", "-"]) == 2
