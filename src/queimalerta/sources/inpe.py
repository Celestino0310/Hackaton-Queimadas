"""Adapter for the official INPE daily Brazil active-fire CSV directory."""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from queimalerta.domain.models import HotspotDetection

_FILE_PATTERN = re.compile(r"^focos_diario_br_(\d{8})\.csv$")
_STATE_ID_TO_UF = {
    11: "RO",
    12: "AC",
    13: "AM",
    14: "RR",
    15: "PA",
    16: "AP",
    17: "TO",
    21: "MA",
    22: "PI",
    23: "CE",
    24: "RN",
    25: "PB",
    26: "PE",
    27: "AL",
    28: "SE",
    29: "BA",
    31: "MG",
    32: "ES",
    33: "RJ",
    35: "SP",
    41: "PR",
    42: "SC",
    43: "RS",
    50: "MS",
    51: "MT",
    52: "GO",
    53: "DF",
}


@dataclass(frozen=True, slots=True)
class InpeFile:
    filename: str
    url: str
    day: date


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _optional_float(value: str | None) -> float | None:
    cleaned = _optional_text(value)
    if cleaned is None:
        return None
    number = float(cleaned)
    return number if math.isfinite(number) else None


def _optional_int(value: str | None) -> int | None:
    number = _optional_float(value)
    return int(number) if number is not None else None


class InpeDailySource:
    def __init__(self, base_url: str, timeout_seconds: int = 45) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = (5, timeout_seconds)
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "QueimAlerta/0.1 (+active-fire monitoring; educational project)"}
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def discover(self, days: int = 1) -> list[InpeFile]:
        response = self.session.get(self.base_url, timeout=self.timeout)
        response.raise_for_status()
        parser = _LinkParser()
        parser.feed(response.text)
        files: list[InpeFile] = []
        for href in parser.hrefs:
            filename = href.rstrip("/").rsplit("/", 1)[-1]
            match = _FILE_PATTERN.match(filename)
            if not match:
                continue
            files.append(
                InpeFile(
                    filename=filename,
                    url=urljoin(self.base_url, href),
                    day=datetime.strptime(match.group(1), "%Y%m%d").date(),
                )
            )
        files.sort(key=lambda item: (item.day, item.filename))
        if not files:
            raise RuntimeError("INPE directory did not contain recognizable Brazil daily CSV files")
        return files[-max(1, days) :]

    def download(self, source_file: InpeFile) -> bytes:
        response = self.session.get(source_file.url, timeout=self.timeout)
        response.raise_for_status()
        if not response.content:
            raise RuntimeError(f"INPE returned an empty file: {source_file.filename}")
        return response.content

    @staticmethod
    def checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def parse(
        content: bytes, *, raw_object_uri: str | None = None
    ) -> tuple[list[HotspotDetection], int]:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text), skipinitialspace=True)
        required = {"id", "lat", "lon", "data_hora_gmt", "satelite"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            missing = sorted(required.difference(reader.fieldnames or []))
            raise ValueError(f"INPE CSV is missing required columns: {', '.join(missing)}")

        detections: list[HotspotDetection] = []
        rejected = 0
        for row in reader:
            try:
                source_id = (_optional_text(row.get("id")) or "").lower()
                latitude = float(row["lat"].strip())
                longitude = float(row["lon"].strip())
                satellite = _optional_text(row.get("satelite")) or "Desconhecido"
                observed_at = datetime.strptime(
                    row["data_hora_gmt"].strip(), "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=UTC)
                country = (_optional_text(row.get("pais")) or "Brasil").casefold()
                if (
                    not source_id
                    or not math.isfinite(latitude)
                    or not math.isfinite(longitude)
                    or not (-34.0 <= latitude <= 6.0)
                    or not (-74.0 <= longitude <= -32.0)
                    or country != "brasil"
                ):
                    raise ValueError("record is outside the validated Brazil feed contract")
                state_id = _optional_int(row.get("estado_id"))
                detections.append(
                    HotspotDetection(
                        source_record_id=source_id,
                        latitude=latitude,
                        longitude=longitude,
                        observed_at=observed_at,
                        satellite=satellite,
                        municipality=_optional_text(row.get("municipio")),
                        state=_optional_text(row.get("estado")),
                        state_code=_STATE_ID_TO_UF.get(state_id),
                        municipality_id=_optional_int(row.get("municipio_id")),
                        state_id=state_id,
                        biome=_optional_text(row.get("bioma")),
                        days_without_rain=_optional_float(
                            row.get("numero_dias_sem_chuva")
                        ),
                        precipitation=_optional_float(row.get("precipitacao")),
                        fire_risk=_optional_float(row.get("risco_fogo")),
                        frp=_optional_float(row.get("frp")),
                        raw_object_uri=raw_object_uri,
                    )
                )
            except (KeyError, TypeError, ValueError):
                rejected += 1
        return detections, rejected

    @staticmethod
    def with_archive_uri(
        detections: list[HotspotDetection], archive_uri: str
    ) -> list[HotspotDetection]:
        return [replace(item, raw_object_uri=archive_uri) for item in detections]
