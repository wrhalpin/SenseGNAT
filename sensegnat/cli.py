from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from pathlib import Path

from sensegnat import __version__
from sensegnat.api.service import SenseGNATService
from sensegnat.config.settings import load_settings
from sensegnat.ingestion.factory import build_adapter

logger = logging.getLogger(__name__)

_LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sensegnat",
        description="SenseGNAT — behavior analytics companion to GNAT.",
    )
    parser.add_argument(
        "--version", action="version", version=f"sensegnat {__version__}"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="-v for INFO, -vv for DEBUG (default: WARNING)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run the detection pipeline")
    run.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the SenseGNAT YAML config file",
    )
    run.add_argument(
        "--interval",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Re-run every N seconds until interrupted (default: run once)",
    )
    return parser


def _summarize(published: list[dict]) -> str:
    counts = Counter(obj.get("type", "unknown") for obj in published)
    indicators = counts.get("indicator", 0)
    notes = counts.get("note", 0)
    groupings = counts.get("grouping", 0)
    return (
        f"published {len(published)} STIX objects "
        f"({indicators} indicators, {notes} notes, {groupings} groupings)"
    )


def _run(config_path: Path, interval: int | None) -> int:
    settings = load_settings(config_path)
    if settings.adapter is None:
        print(
            "error: config has no 'adapter:' section — add one, e.g.\n"
            "  adapter:\n    type: csv\n    path: ./events.csv",
            file=sys.stderr,
        )
        return 2

    adapter = build_adapter(settings.adapter)
    service = SenseGNATService(adapter=adapter, settings=settings)

    while True:
        published = service.run_once()
        print(_summarize(published))
        if interval is None:
            return 0
        logger.info("sleeping %ds until next run", interval)
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=_LOG_LEVELS.get(min(args.verbose, 2), logging.DEBUG),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "run":
        try:
            return _run(args.config, args.interval)
        except KeyboardInterrupt:
            print("interrupted", file=sys.stderr)
            return 130
        except (FileNotFoundError, ValueError, ImportError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    return 2  # unreachable — subparsers are required


if __name__ == "__main__":
    sys.exit(main())
