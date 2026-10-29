"""SQLAlchemy persistence for hotspot detections and ingestion runs."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import NullPool

from queimalerta.domain.models import HotspotDetection


class Base(DeclarativeBase):
    pass


class HotspotRecord(Base):
    __tablename__ = "hotspot_detection"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="INPE")
    source_record_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    satellite: Mapped[str] = mapped_column(String(80), nullable=False)
    municipality: Mapped[str | None] = mapped_column(String(180))
    state: Mapped[str | None] = mapped_column(String(120))
    state_code: Mapped[str | None] = mapped_column(String(2))
    municipality_id: Mapped[int | None] = mapped_column(Integer)
    state_id: Mapped[int | None] = mapped_column(Integer)
    biome: Mapped[str | None] = mapped_column(String(80))
    days_without_rain: Mapped[float | None] = mapped_column(Float)
    precipitation: Mapped[float | None] = mapped_column(Float)
    fire_risk: Mapped[float | None] = mapped_column(Float)
    frp: Mapped[float | None] = mapped_column(Float)
    raw_object_uri: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_hotspot_observed_at", "observed_at"),
        Index("ix_hotspot_state_observed", "state_code", "observed_at"),
        Index("ix_hotspot_biome_observed", "biome", "observed_at"),
    )


class IngestionRunRecord(Base):
    __tablename__ = "ingestion_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source_observed_max_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    downloaded_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_ingestion_status_started", "status", "started_at"),)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class DatabaseRepository:
    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        engine_options: dict[str, Any] = {
            "pool_pre_ping": True,
            "connect_args": connect_args,
        }
        if os.getenv("VERCEL") and database_url.startswith("postgresql"):
            # A function instance must not retain its own long-lived connection pool.
            # Use the pooled URL supplied by the PostgreSQL provider when available.
            engine_options["poolclass"] = NullPool
        self.engine = create_engine(database_url, **engine_options)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def ping(self) -> bool:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    def start_ingestion(self, source: str = "INPE") -> str:
        run_id = str(uuid.uuid4())
        with Session(self.engine) as session:
            session.add(
                IngestionRunRecord(
                    id=run_id,
                    source=source,
                    started_at=datetime.now(UTC),
                    status="running",
                )
            )
            session.commit()
        return run_id

    def finish_ingestion(
        self,
        run_id: str,
        *,
        downloaded_count: int,
        inserted_count: int,
        updated_count: int,
        rejected_count: int,
        source_observed_max_at: datetime | None,
    ) -> None:
        with Session(self.engine) as session:
            run = session.get(IngestionRunRecord, run_id)
            if run is None:
                raise LookupError(f"Unknown ingestion run: {run_id}")
            run.finished_at = datetime.now(UTC)
            run.status = "success"
            run.downloaded_count = downloaded_count
            run.inserted_count = inserted_count
            run.updated_count = updated_count
            run.rejected_count = rejected_count
            run.source_observed_max_at = source_observed_max_at
            session.commit()

    def fail_ingestion(self, run_id: str, error: Exception) -> None:
        with Session(self.engine) as session:
            run = session.get(IngestionRunRecord, run_id)
            if run is None:
                return
            run.finished_at = datetime.now(UTC)
            run.status = "failed"
            run.error_code = type(error).__name__[:120]
            run.error_message = str(error)[:1000]
            session.commit()

    def upsert_hotspots(self, detections: Iterable[HotspotDetection]) -> tuple[int, int]:
        now = datetime.now(UTC)
        rows = [
            {
                "source": item.source,
                "source_record_id": item.source_record_id,
                "observed_at": item.observed_at,
                "ingested_at": now,
                "latitude": item.latitude,
                "longitude": item.longitude,
                "satellite": item.satellite,
                "municipality": item.municipality,
                "state": item.state,
                "state_code": item.state_code,
                "municipality_id": item.municipality_id,
                "state_id": item.state_id,
                "biome": item.biome,
                "days_without_rain": item.days_without_rain,
                "precipitation": item.precipitation,
                "fire_risk": item.fire_risk,
                "frp": item.frp,
                "raw_object_uri": item.raw_object_uri,
            }
            for item in detections
        ]
        if not rows:
            return 0, 0

        existing: set[str] = set()
        source_ids = [row["source_record_id"] for row in rows]
        with Session(self.engine) as session:
            for start in range(0, len(source_ids), 500):
                chunk = source_ids[start : start + 500]
                existing.update(
                    session.scalars(
                        select(HotspotRecord.source_record_id).where(
                            HotspotRecord.source_record_id.in_(chunk)
                        )
                    )
                )

            dialect = self.engine.dialect.name
            mutable_columns = {
                key: key
                for key in rows[0]
                if key not in {"source_record_id"}
            }
            for start in range(0, len(rows), 500):
                chunk_rows = rows[start : start + 500]
                if dialect == "postgresql":
                    statement = postgresql_insert(HotspotRecord).values(chunk_rows)
                    statement = statement.on_conflict_do_update(
                        index_elements=[HotspotRecord.source_record_id],
                        set_={
                            column: getattr(statement.excluded, source_key)
                            for column, source_key in mutable_columns.items()
                        },
                    )
                elif dialect == "sqlite":
                    statement = sqlite_insert(HotspotRecord).values(chunk_rows)
                    statement = statement.on_conflict_do_update(
                        index_elements=[HotspotRecord.source_record_id],
                        set_={
                            column: getattr(statement.excluded, source_key)
                            for column, source_key in mutable_columns.items()
                        },
                    )
                else:
                    raise RuntimeError(f"Unsupported database dialect: {dialect}")
                session.execute(statement)
            session.commit()

        updated = sum(row["source_record_id"] in existing for row in rows)
        return len(rows) - updated, updated

    @staticmethod
    def _filters(
        since: datetime,
        state_code: str | None,
        biome: str | None,
        satellite: str | None,
    ) -> list[Any]:
        conditions: list[Any] = [HotspotRecord.observed_at >= since]
        if state_code:
            conditions.append(HotspotRecord.state_code == state_code)
        if biome:
            conditions.append(HotspotRecord.biome == biome)
        if satellite:
            conditions.append(HotspotRecord.satellite == satellite)
        return conditions

    def summary(
        self,
        hours: int,
        state_code: str | None = None,
        biome: str | None = None,
        satellite: str | None = None,
    ) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(hours=hours)
        conditions = self._filters(since, state_code, biome, satellite)
        with Session(self.engine) as session:
            total = session.scalar(
                select(func.count(HotspotRecord.id)).where(*conditions)
            ) or 0
            affected_states = session.scalar(
                select(func.count(func.distinct(HotspotRecord.state_code))).where(
                    *conditions, HotspotRecord.state_code.is_not(None)
                )
            ) or 0
            newest = session.scalar(
                select(func.max(HotspotRecord.observed_at)).where(*conditions)
            )
            top_state_row = session.execute(
                select(HotspotRecord.state_code, func.count(HotspotRecord.id).label("count"))
                .where(*conditions, HotspotRecord.state_code.is_not(None))
                .group_by(HotspotRecord.state_code)
                .order_by(func.count(HotspotRecord.id).desc())
                .limit(1)
            ).first()
        return {
            "total": int(total),
            "affected_states": int(affected_states),
            "newest_observed_at": _as_utc(newest),
            "top_state": top_state_row[0] if top_state_row else None,
            "top_state_count": int(top_state_row[1]) if top_state_row else 0,
        }

    def hotspots(
        self,
        hours: int,
        *,
        state_code: str | None = None,
        biome: str | None = None,
        satellite: str | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        since = datetime.now(UTC) - timedelta(hours=hours)
        conditions = self._filters(since, state_code, biome, satellite)
        statement = (
            select(
                HotspotRecord.source_record_id,
                HotspotRecord.latitude,
                HotspotRecord.longitude,
                HotspotRecord.observed_at,
                HotspotRecord.satellite,
                HotspotRecord.municipality,
                HotspotRecord.state,
                HotspotRecord.state_code,
                HotspotRecord.biome,
                HotspotRecord.frp,
                HotspotRecord.fire_risk,
            )
            .where(*conditions)
            .order_by(HotspotRecord.observed_at.desc())
            .limit(limit)
        )
        with Session(self.engine) as session:
            return [dict(row._mapping) for row in session.execute(statement)]

    def filter_options(self) -> dict[str, list[str]]:
        with Session(self.engine) as session:
            states = list(
                session.scalars(
                    select(HotspotRecord.state_code)
                    .where(HotspotRecord.state_code.is_not(None))
                    .distinct()
                    .order_by(HotspotRecord.state_code)
                )
            )
            biomes = list(
                session.scalars(
                    select(HotspotRecord.biome)
                    .where(HotspotRecord.biome.is_not(None))
                    .distinct()
                    .order_by(HotspotRecord.biome)
                )
            )
            satellites = list(
                session.scalars(
                    select(HotspotRecord.satellite)
                    .distinct()
                    .order_by(HotspotRecord.satellite)
                )
            )
        return {"states": states, "biomes": biomes, "satellites": satellites}

    def health(self) -> dict[str, Any]:
        with Session(self.engine) as session:
            latest_run = session.scalars(
                select(IngestionRunRecord).order_by(IngestionRunRecord.started_at.desc()).limit(1)
            ).first()
            latest_success = session.scalars(
                select(IngestionRunRecord)
                .where(IngestionRunRecord.status == "success")
                .order_by(IngestionRunRecord.finished_at.desc())
                .limit(1)
            ).first()
            newest_observed = session.scalar(select(func.max(HotspotRecord.observed_at)))
            total_records = session.scalar(select(func.count(HotspotRecord.id))) or 0

        def run_payload(run: IngestionRunRecord | None) -> dict[str, Any] | None:
            if run is None:
                return None
            return {
                "id": run.id,
                "status": run.status,
                "started_at": _as_utc(run.started_at),
                "finished_at": _as_utc(run.finished_at),
                "downloaded_count": run.downloaded_count,
                "inserted_count": run.inserted_count,
                "updated_count": run.updated_count,
                "rejected_count": run.rejected_count,
                "error_code": run.error_code,
            }

        return {
            "latest_run": run_payload(latest_run),
            "latest_success": run_payload(latest_success),
            "newest_observed_at": _as_utc(newest_observed),
            "total_records": int(total_records),
        }
