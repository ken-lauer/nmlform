# nmlform

`nmlform` is a formatter and round-trip parser for Fortran namelists.

[Documentation](https://ken-lauer.github.io/nmlform)

Unlike value-oriented readers, it keeps the source lines as the source of truth
and derives a location-tagged tree over them, so comments, spacing, quoting, and
layout survive a round trip. That makes it safe to reformat a namelist, or to
edit individual values, without disturbing anything you did not touch.

## Installation

`nmlform` has no runtime dependencies, so a plain virtual environment is all you
need:

```bash
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate
```

Then install this package into the environment:

```bash
git clone https://github.com/ken-lauer/nmlform
cd nmlform
python -m pip install .
```

To install optional extras, use one of the following:

```bash
# Optional parsers for YAML/TOML `--values` files (JSON needs nothing extra):
$ python -m pip install .[all]
# The test suite requirements:
$ python -m pip install .[test]
# The documentation requirements:
$ python -m pip install .[doc]
# Everything:
$ python -m pip install .[all,test,doc]
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
nmlform --in-place *.nml         # rewrite files in place
nmlform --check *.nml            # exit non-zero if any file would change
nmlform --diff *.nml             # show a unified diff of what would change
cat example.nml | nmlform -      # read from stdin, write to stdout
```

Layout is controlled by flags that mirror the API's formatting options
(`--indent-size`, `--tabs`, `--field-case`, `--align-equals` /
`--no-align-equals`, `--align-comments` / `--no-align-comments`,
`--blank-line-after-group` / `--no-blank-line-after-group`). See
`nmlform --help` for the full list.

### Setting and removing values

The `nmlform-set` console script edits a single namelist file, setting and/or
removing values and writing the result to standard output (or to a file with
`-o`, or back to the input file with `-i`). Edits are surgical: the source
layout, comments, and untouched values are preserved verbatim.

Given `plot.nml`:

```fortran
&plot
  a = 1  ! a comment
  bb = 2.0
/
```

```console
$ nmlform-set --set plot a 42 --set plot cc "'new'" --remove plot bb plot.nml
&plot
  a = 42  ! a comment
  cc = 'new'
/
```

`--set` and `--remove` are repeatable. Use `NAMELIST#N` (1-based) to target the
N-th of a repeated group. Pass `--reformat` to also apply the formatting flags
above; otherwise only the edited values change. See `nmlform-set --help`.

Values can also come from a file with `--values` (repeatable; `-` reads stdin):

```console
$ nmlform-set --values overrides.json plot.nml
$ nmlform-set --values overrides.yaml --set plot a 99 plot.nml   # --set wins
```

The format is inferred from the extension (override with `--values-format`):

- **JSON** (built in), **YAML**, and **TOML** map groups to `{key: value}`
  tables. A string becomes a quoted Fortran string, numbers and booleans become
  Fortran literals (`.true.`), a list becomes a value list, and `null` removes
  the key. YAML and TOML need the optional parsers: `pip install nmlform[all]`.
- A **namelist file** (`.nml`/`.init`) is applied group by group, field by
  field, copying each raw value verbatim — handy for merging one namelist's
  values into another.

For example, `overrides.json`:

```json
{ "plot": { "a": 42, "title": "hello", "bb": null } }
```

produces the same edit as `--set plot a 42 --set plot title "'hello'" --remove plot bb`.

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
