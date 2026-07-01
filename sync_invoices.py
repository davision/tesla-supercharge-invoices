#!/usr/bin/env python3
"""Poll Tesla Fleet API for new charging invoices and save them locally."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from tesla_invoicer.config import load_config
from tesla_invoicer.state import clear_processed_invoices
from tesla_invoicer.sync import run_sync


def configure_logging(log_file: Path | None, verbose: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Tesla charging invoices")
    parser.add_argument("--env-file", default=".env", help="Path to .env file")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear processed-invoice history and re-download all invoices",
    )
    args = parser.parse_args()

    config = load_config(args.env_file)
    configure_logging(config.log_file, args.verbose)

    if args.reset:
        cleared = clear_processed_invoices(config.state_file)
        logging.info("Reset: cleared %s processed invoice(s) from state.", cleared)

    downloaded = run_sync(config)
    logging.info("Finished. Downloaded %s invoice(s) to %s.", downloaded, config.invoices_dir)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception("%s", exc)
        raise SystemExit(1) from exc
