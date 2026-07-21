# nmlform

`nmlform` is a formatter and round-trip parser for Fortran namelists.

Unlike value-oriented readers, it keeps the source lines as the source of truth
and derives a location-tagged tree over them, so comments, spacing, quoting, and
layout survive a round trip. That makes it safe to reformat a namelist, or to
edit individual values, without disturbing anything you did not touch.

## Installation

Create a conda environment for the package:

```bash
$ mamba env create -n nmlform python=3.12 pip
$ conda activate nmlform
```

And then install this package into the environment:

```bash
$ git clone https://github.com/ken-lauer/nmlform
$ cd nmlform
$ export NMLFORM=$PWD
$ python -m pip install .
```

To install extras for running the package tests or documentation, use one the
following:

```bash
# Install the base requirements and test suite requirements:
$ python -m pip install .[test]
# Install the base requirements and the documentation requirements:
$ python -m pip install .[doc]
# Install all of the requirements:
$ python -m pip install .[test,doc]
```

## Command-line usage

Installing the package provides an `nmlform` console script that reformats one
or more namelist files, writing the result to standard output. Use `-` to read
from standard input.

Given a messy `example.nml`:

```fortran
&plot a=1  bb = 2.0
    long_name= 'value'   ! a comment
/
```

Running `nmlform` reformats it:

```console
$ nmlform example.nml
&plot
  a         = 1
  bb        = 2.0
  long_name = 'value'  ! a comment
/
```

Common options:

```console
$ nmlform --in-place *.nml         # rewrite files in place
$ nmlform --check *.nml            # exit non-zero if any file would change
$ nmlform --diff *.nml             # show a unified diff of what would change
$ cat example.nml | nmlform -      # read from stdin, write to stdout
```

Layout is controlled by flags that mirror the API's formatting options
(`--indent-size`, `--tabs`, `--field-case`, `--align-equals` /
`--no-align-equals`, `--align-comments` / `--no-align-comments`,
`--blank-line-after-group` / `--no-blank-line-after-group`). See
`nmlform --help` for the full list.

## API usage

Parse a file (or a string) into a `NamelistFile`, then render it. Rendering
without options reproduces the source verbatim; passing
`NamelistFormatOptions` reformats it:

```python
from nmlform import NamelistFile, NamelistFormatOptions

nml = NamelistFile.from_file("example.nml")

# Round-trip: byte-for-byte identical to the source.
assert nml.render() == open("example.nml").read()

# Reformat with explicit options.
print(nml.render(NamelistFormatOptions(indent_size=4, field_case="upper")))
```

Access and edit groups and their assignments. Edits are surgical — only the
touched value is spliced, so surrounding comments and layout are preserved:

```python
from nmlform import NamelistFile

nml = NamelistFile.parse("&plot a = 1  bb = 2.0 /\n")

plot = nml.get_namelist("plot")
print(plot.get("a").value)          # -> the value Token for `a`

plot.set("a", "42")                 # update in place
plot.set("cc", "'new'")             # append a new key before the `/`
plot.remove("bb")                   # drop an assignment

print(nml.render())
```

You can also update or create groups in bulk:

```python
nml.update_namelist("plot", {"a": "1", "title": "'demo'"})
```

Values are kept as raw source tokens. Use `unquote_value` / `quote_value` to
convert between a Fortran string literal and its content:

```python
from nmlform import quote_value, unquote_value

quote_value("it's")                 # -> "'it''s'"
```

See the [documentation](https://ken-lauer.github.io/nmlform) for the full API
reference.
