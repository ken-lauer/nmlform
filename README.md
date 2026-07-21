# nmlform

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
$ export NMLTREE=$PWD
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
