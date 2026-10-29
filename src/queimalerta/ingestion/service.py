"""Orchestration for reproducible, idempotent INPE ingestion."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from queimalerta.repositories.database import DatabaseRepository
from queimalerta.sources.inpe import InpeDailySource

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    run_id: str
    files: int
    downloaded: int
    inserted: int
    updated: int
    rejected: int
    newest_observation: datetime | None


class IngestionService:
    def __init__(
        self,
        source: InpeDailySource,
        repository: DatabaseRepository,
        archive_dir: Path | None,
    ) -> None:
        self.source = source
        self.repository = repository
        self.archive_dir = archive_dir

    def _archive(self, filename: str, content: bytes, checksum: str) -> Path | None:
        if self.archive_dir is None:
            return None
        now = datetime.now(UTC)
        day_dir = self.archive_dir / now.strftime("%Y/%m/%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(filename).stem
        target = day_dir / f"{stem}_{now:%Y%m%dT%H%M%SZ}_{checksum[:10]}.csv"
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
        return target

    def run(self, days: int = 1) -> IngestionResult:
        self.repository.initialize()
        run_id = self.repository.start_ingestion()
        downloaded = inserted = updated = rejected = 0
        newest: datetime | None = None
        try:
            source_files = self.source.discover(days=days)
            for source_file in source_files:
                content = self.source.download(source_file)
                checksum = self.source.checksum(content)
                archive_path = self._archive(source_file.filename, content, checksum)
                raw_object_uri = archive_path.as_uri() if archive_path else source_file.url
                detections, file_rejected = self.source.parse(
                    content, raw_object_uri=raw_object_uri
                )
                file_inserted, file_updated = self.repository.upsert_hotspots(detections)
                downloaded += len(detections) + file_rejected
                inserted += file_inserted
                updated += file_updated
                rejected += file_rejected
                if detections:
                    file_newest = max(item.observed_at for item in detections)
                    newest = max(newest, file_newest) if newest else file_newest
                logger.info(
                    "INPE file ingested",
                    extra={
                        "event": "ingestion_file_success",
                        "run_id": run_id,
                        "source_file": source_file.filename,
                        "inserted_count": file_inserted,
                        "updated_count": file_updated,
                        "rejected_count": file_rejected,
                    },
                )

            self.repository.finish_ingestion(
                run_id,
                downloaded_count=downloaded,
                inserted_count=inserted,
                updated_count=updated,
                rejected_count=rejected,
                source_observed_max_at=newest,
            )
            result = IngestionResult(
                run_id=run_id,
                files=len(source_files),
                downloaded=downloaded,
                inserted=inserted,
                updated=updated,
                rejected=rejected,
                newest_observation=newest,
            )
            logger.info(
                "INPE ingestion completed",
                extra={
                    "event": "ingestion_success",
                    "run_id": run_id,
                    "file_count": result.files,
                    "downloaded_count": downloaded,
                    "inserted_count": inserted,
                    "updated_count": updated,
                    "rejected_count": rejected,
                    "newest_observation": newest,
                },
            )
            return result
        except Exception as error:
            self.repository.fail_ingestion(run_id, error)
            logger.exception(
                "INPE ingestion failed",
                extra={
                    "event": "ingestion_failure",
                    "run_id": run_id,
                    "error_code": type(error).__name__,
                },
            )
            raise
