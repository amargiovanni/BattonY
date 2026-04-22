"""Entry point: `python -m battony` or the `battony` console script."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .app import BattonYApp
from .config import CONFIG_PATH, LOG_DIR, ensure_config, load_config


def _setup_logging(verbose: bool) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logfile = LOG_DIR / "battony.log"
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[logging.FileHandler(logfile, encoding="utf-8")],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="battony",
        description="a modern, glorious, BitchX-inspired IRC client for the terminal",
    )
    parser.add_argument(
        "-c", "--config", type=Path, help=f"path to config file (default: {CONFIG_PATH})"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument("--print-config-path", action="store_true", help="print config path and exit")
    args = parser.parse_args(argv)

    if args.print_config_path:
        print(ensure_config())
        return 0

    _setup_logging(args.verbose)
    config = load_config(args.config)
    app = BattonYApp(config)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
