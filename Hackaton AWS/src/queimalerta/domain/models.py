"""Validated domain values passed from source adapters to persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class HotspotDetection:
    source_record_id: str
    latitude: float
    longitude: float
    observed_at: datetime
    satellite: str
    municipality: str | None = None
    state: str | None = None
    state_code: str | None = None
    municipality_id: int | None = None
    state_id: int | None = None
    biome: str | None = None
    days_without_rain: float | None = None
    precipitation: float | None = None
    fire_risk: float | None = None
    frp: float | None = None
    source: str = "INPE"
    raw_object_uri: str | None = None
