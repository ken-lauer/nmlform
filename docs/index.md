# nmlform

`nmlform` is a formatter and round-trip parser for Fortran namelists.

Unlike value-oriented readers, it keeps the source lines as the source of truth
and derives a location-tagged tree over them, so comments, spacing, quoting, and
layout survive a round trip. That makes it safe to reformat a namelist, or to
edit individual values, without disturbing anything you did not touch.

## Command-line usage

Installing the package provides an `nmlform` console script that reformats one
or more namelist files, writing the result to standard output. Use `-` to read
from standard input.

```console
$ nmlform example.nml                # reformat to stdout
$ nmlform --in-place *.nml           # rewrite files in place
$ nmlform --check *.nml              # exit non-zero if any file would change
$ nmlform --diff *.nml               # show a unified diff of what would change
$ cat example.nml | nmlform -        # read from stdin
```

Layout is controlled by flags mirroring [`NamelistFormatOptions`][nmlform.NamelistFormatOptions]:
`--indent-size`, `--tabs`, `--field-case`, `--align-equals` /
`--no-align-equals`, `--align-comments` / `--no-align-comments`, and
`--blank-line-after-group` / `--no-blank-line-after-group`. Run `nmlform --help`
for the full list.

## API usage

Parse a file (or a string) into a [`NamelistFile`][nmlform.NamelistFile], then
render it. Rendering without options reproduces the source verbatim; passing
[`NamelistFormatOptions`][nmlform.NamelistFormatOptions] reformats it:

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
nml = NamelistFile.parse("&plot a = 1  bb = 2.0 /\n")

plot = nml.get_namelist("plot")
plot.set("a", "42")                 # update in place
plot.set("cc", "'new'")             # append a new key before the `/`
plot.remove("bb")                   # drop an assignment

print(nml.render())
```

See the [API reference](api.md) for the full set of types and functions.
