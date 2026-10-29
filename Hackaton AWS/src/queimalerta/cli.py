"""Command-line operations for database setup, ingestion, and status."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from queimalerta.ingestion.service import IngestionService
from queimalerta.observability.logging import configure_logging
from queimalerta.repositories.database import DatabaseRepository
from queimalerta.settings import Settings
from queimalerta.sources.inpe import InpeDailySource


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="queimalerta")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("init-db", help="Create the application database schema")
    ingest = subcommands.add_parser("ingest", help="Ingest recent INPE Brazil daily files")
    ingest.add_argument(
        "--days",
        type=int,
        default=1,
        choices=range(1, 32),
        metavar="1-31",
        help="number of latest daily files to ingest (default: 1)",
    )
    subcommands.add_parser("status", help="Print pipeline and data health as JSON")
    return parser


def main() -> None:
    args = _parser().parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    repository = DatabaseRepository(settings.database_url)

    if args.command == "init-db":
        repository.initialize()
        print("Database schema initialized.")
        return

    if args.command == "ingest":
        service = IngestionService(
            InpeDailySource(settings.inpe_daily_url),
            repository,
            settings.archive_dir,
        )
        result = service.run(days=args.days)
        print(json.dumps(asdict(result), ensure_ascii=False, default=str, indent=2))
        return

    repository.initialize()
    print(json.dumps(repository.health(), ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
