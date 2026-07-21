"""
`nmlform` command-line tool.

Customize this docstring for it to appear in the command-line help information.
"""

import argparse
import logging

DESCRIPTION = __doc__
logger = logging.getLogger(__name__)


def main(**kwargs) -> None:
    print("This is the entrypoint for nmlform.")
    print("These keyword arguments are not yet handled:", kwargs)


def _build_argparser() -> argparse.ArgumentParser:
    """
    This function builds an argument parser for your command-line application.

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
        default="INFO",
        type=str,
        help="Python logging level (e.g. DEBUG, INFO, WARNING)",
    )

    return parser


def cli_main(args: list[str] | None = None) -> None:
    """
    CLI entrypoint main.

    Parameters
    ----------
    args : list of str, optional
        Command-line arguments to parse and pass to :func:`main()`.
    """
    parsed = _build_argparser().parse_args(args=args)
    kwargs = vars(parsed)
    log_level = kwargs.pop("log_level")

    # Adjust the package-level logger level as requested:
    logger = logging.getLogger("nmlform")
    logger.setLevel(log_level)
    logging.basicConfig()
    return main(**kwargs)


if __name__ == "__main__":
    cli_main()
