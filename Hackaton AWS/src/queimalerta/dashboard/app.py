"""Plotly Dash application for Brazil active-fire monitoring."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dash_table, dcc, html
from flask import jsonify

from queimalerta.observability.logging import configure_logging
from queimalerta.repositories.database import DatabaseRepository
from queimalerta.settings import Settings

BRASILIA = ZoneInfo("America/Sao_Paulo")


def _empty_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 16, "color": "#697386"},
    )
    figure.update_layout(
        template="plotly_white",
        xaxis={"visible": False},
        yaxis={"visible": False},
        margin={"l": 20, "r": 20, "t": 45, "b": 20},
    )
    return figure


def _local_time(value: datetime | None) -> str:
    if value is None:
        return "Sem dados"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(BRASILIA).strftime("%d/%m/%Y %H:%M BRT")


def _iso_health(payload: dict) -> dict:
    return {
        key: (
            _iso_health(value)
            if isinstance(value, dict)
            else value.isoformat()
            if isinstance(value, datetime)
            else value
        )
        for key, value in payload.items()
    }


def _layout(refresh_seconds: int) -> html.Div:
    return html.Div(
        className="app-shell",
        children=[
            dcc.Interval(
                id="refresh-timer",
                interval=refresh_seconds * 1000,
                n_intervals=0,
            ),
            html.Header(
                className="hero",
                children=[
                    html.Div(
                        [
                            html.P("MONITORAMENTO AMBIENTAL", className="eyebrow"),
                            html.H1("QueimAlerta Brasil"),
                            html.P(
                                "Detecções de fogo ativo por satélite, atualizadas durante o dia.",
                                className="subtitle",
                            ),
                        ]
                    ),
                    html.Div(id="last-updated", className="last-updated"),
                ],
            ),
            html.Div(id="freshness-banner", className="status-banner"),
            html.Section(
                className="filters panel",
                children=[
                    html.Div(
                        [
                            html.Label("Período", htmlFor="period-filter"),
                            dcc.Dropdown(
                                id="period-filter",
                                options=[
                                    {"label": "Última hora", "value": 1},
                                    {"label": "Últimas 6 horas", "value": 6},
                                    {"label": "Últimas 24 horas", "value": 24},
                                    {"label": "Últimos 3 dias", "value": 72},
                                    {"label": "Últimos 7 dias", "value": 168},
                                ],
                                value=24,
                                clearable=False,
                            ),
                        ],
                        className="filter-item",
                    ),
                    html.Div(
                        [
                            html.Label("Estado", htmlFor="state-filter"),
                            dcc.Dropdown(
                                id="state-filter",
                                options=[],
                                placeholder="Todos os estados",
                                clearable=True,
                            ),
                        ],
                        className="filter-item",
                    ),
                    html.Div(
                        [
                            html.Label("Bioma", htmlFor="biome-filter"),
                            dcc.Dropdown(
                                id="biome-filter",
                                options=[],
                                placeholder="Todos os biomas",
                                clearable=True,
                            ),
                        ],
                        className="filter-item",
                    ),
                    html.Div(
                        [
                            html.Label("Satélite", htmlFor="satellite-filter"),
                            dcc.Dropdown(
                                id="satellite-filter",
                                options=[],
                                placeholder="Todos os satélites",
                                clearable=True,
                            ),
                        ],
                        className="filter-item",
                    ),
                ],
            ),
            html.Section(
                className="kpi-grid",
                children=[
                    html.Article(
                        [html.P("Detecções no período"), html.H2(id="kpi-total")],
                        className="kpi-card",
                    ),
                    html.Article(
                        [html.P("Estados afetados"), html.H2(id="kpi-states")],
                        className="kpi-card",
                    ),
                    html.Article(
                        [html.P("Estado com mais focos"), html.H2(id="kpi-top-state")],
                        className="kpi-card",
                    ),
                    html.Article(
                        [html.P("Observação mais recente"), html.H2(id="kpi-newest")],
                        className="kpi-card",
                    ),
                ],
            ),
            html.Section(
                className="panel map-panel",
                children=[
                    html.Div(
                        [
                            html.H2("Mapa de detecções"),
                            html.P(
                                "Pontos são detecções térmicas e não confirmações de incêndio.",
                                className="section-note",
                            ),
                        ],
                        className="section-heading",
                    ),
                    dcc.Loading(dcc.Graph(id="hotspot-map", config={"displaylogo": False})),
                ],
            ),
            html.Section(
                className="chart-grid",
                children=[
                    html.Article(
                        className="panel",
                        children=[
                            html.H2("Evolução por hora"),
                            dcc.Graph(id="timeline-chart", config={"displaylogo": False}),
                        ],
                    ),
                    html.Article(
                        className="panel",
                        children=[
                            html.H2("Estados com mais detecções"),
                            dcc.Graph(id="ranking-chart", config={"displaylogo": False}),
                        ],
                    ),
                ],
            ),
            html.Section(
                className="panel",
                children=[
                    html.Div(
                        [
                            html.H2("Detecções recentes"),
                            html.P(
                                "A tabela mostra até 250 registros do filtro atual.",
                                className="section-note",
                            ),
                        ],
                        className="section-heading",
                    ),
                    dash_table.DataTable(
                        id="hotspot-table",
                        columns=[
                            {"name": "Horário (BRT)", "id": "observed_local"},
                            {"name": "UF", "id": "state_code"},
                            {"name": "Município", "id": "municipality"},
                            {"name": "Bioma", "id": "biome"},
                            {"name": "Satélite", "id": "satellite"},
                            {"name": "FRP", "id": "frp"},
                        ],
                        page_size=15,
                        sort_action="native",
                        filter_action="native",
                        style_table={"overflowX": "auto"},
                        style_cell={
                            "fontFamily": "Inter, Segoe UI, sans-serif",
                            "fontSize": 13,
                            "padding": "11px",
                            "textAlign": "left",
                        },
                        style_header={
                            "backgroundColor": "#f3f6f4",
                            "fontWeight": 700,
                            "border": "none",
                        },
                    ),
                ],
            ),
            html.Section(
                className="panel monitoring-panel",
                children=[
                    html.Div(
                        [
                            html.P("OPERAÇÃO", className="eyebrow dark"),
                            html.H2("Saúde do sistema"),
                        ]
                    ),
                    html.Div(id="monitoring-details", className="monitoring-grid"),
                ],
            ),
            html.Footer(
                [
                    html.P(
                        [
                            "Fonte: ",
                            html.A(
                                "Programa Queimadas — INPE",
                                href="https://terrabrasilis.dpi.inpe.br/queimadas/portal/dados-abertos/",
                                target="_blank",
                            ),
                            ". Horários armazenados em UTC e exibidos em BRT.",
                        ]
                    ),
                    html.P(
                        "Detecções por satélite podem incluir queimadas controladas "
                        "e falsos positivos."
                    ),
                ]
            ),
        ],
    )


def create_app(settings: Settings | None = None) -> Dash:
    settings = settings or Settings.from_env()
    repository = DatabaseRepository(settings.database_url)
    repository.initialize()
    assets_folder = Path(__file__).with_name("assets")
    app = Dash(
        __name__,
        title="QueimAlerta Brasil",
        update_title="Atualizando…",
        assets_folder=str(assets_folder),
    )
    app.layout = _layout(settings.refresh_seconds)

    @app.server.get("/health/live")
    def health_live():
        return jsonify({"status": "ok", "time": datetime.now(UTC).isoformat()})

    @app.server.get("/health/ready")
    def health_ready():
        try:
            repository.ping()
            return jsonify({"status": "ready"})
        except Exception as error:
            return jsonify({"status": "not_ready", "error": type(error).__name__}), 503

    @app.server.get("/health/data")
    def health_data():
        payload = repository.health()
        latest_success = payload.get("latest_success")
        finished_at = latest_success.get("finished_at") if latest_success else None
        stale = (
            finished_at is None
            or (datetime.now(UTC) - finished_at).total_seconds()
            > settings.stale_after_minutes * 60
        )
        return jsonify({"status": "stale" if stale else "fresh", **_iso_health(payload)}), (
            503 if stale else 200
        )

    @app.callback(
        Output("freshness-banner", "children"),
        Output("freshness-banner", "className"),
        Output("last-updated", "children"),
        Output("kpi-total", "children"),
        Output("kpi-states", "children"),
        Output("kpi-top-state", "children"),
        Output("kpi-newest", "children"),
        Output("hotspot-map", "figure"),
        Output("timeline-chart", "figure"),
        Output("ranking-chart", "figure"),
        Output("hotspot-table", "data"),
        Output("monitoring-details", "children"),
        Output("state-filter", "options"),
        Output("biome-filter", "options"),
        Output("satellite-filter", "options"),
        Input("refresh-timer", "n_intervals"),
        Input("period-filter", "value"),
        Input("state-filter", "value"),
        Input("biome-filter", "value"),
        Input("satellite-filter", "value"),
    )
    def refresh_dashboard(
        _interval: int,
        hours: int,
        state_code: str | None,
        biome: str | None,
        satellite: str | None,
    ):
        hours = int(hours or 24)
        summary = repository.summary(hours, state_code, biome, satellite)
        rows = repository.hotspots(
            hours,
            state_code=state_code,
            biome=biome,
            satellite=satellite,
            limit=max(settings.max_map_points, 50_000),
        )
        health = repository.health()
        options = repository.filter_options()
        latest_success = health.get("latest_success")
        finished_at = latest_success.get("finished_at") if latest_success else None
        stale = (
            finished_at is None
            or (datetime.now(UTC) - finished_at).total_seconds()
            > settings.stale_after_minutes * 60
        )
        if finished_at is None:
            banner = (
                "Sem ingestão concluída. Execute o comando de ingestão "
                "para carregar dados do INPE."
            )
            banner_class = "status-banner critical"
        elif stale:
            banner = (
                f"Dados possivelmente desatualizados: última ingestão concluída em "
                f"{_local_time(finished_at)}."
            )
            banner_class = "status-banner warning"
        else:
            banner = f"Dados operacionais. Última ingestão concluída em {_local_time(finished_at)}."
            banner_class = "status-banner healthy"

        if rows:
            frame = pd.DataFrame(rows)
            frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True)
            frame["state_display"] = frame["state_code"].fillna("N/D")
            map_frame = frame.head(settings.max_map_points).copy()
            map_figure = go.Figure()
            for satellite_name, satellite_frame in map_frame.groupby("satellite"):
                custom_data = list(
                    zip(
                        satellite_frame["state_code"].fillna("N/D"),
                        satellite_frame["biome"].fillna("N/D"),
                        satellite_frame["observed_at"].map(
                            lambda value: value.strftime("%d/%m/%Y %H:%M UTC")
                        ),
                        satellite_frame["frp"].map(
                            lambda value: "N/D" if pd.isna(value) else f"{value:.1f}"
                        ),
                        strict=True,
                    )
                )
                map_figure.add_trace(
                    go.Scattermap(
                        lat=satellite_frame["latitude"].tolist(),
                        lon=satellite_frame["longitude"].tolist(),
                        mode="markers",
                        name=str(satellite_name),
                        text=satellite_frame["municipality"].fillna("Local não identificado"),
                        customdata=custom_data,
                        marker={"size": 9, "opacity": 0.72},
                        hovertemplate=(
                            "<b>%{text}</b><br>"
                            "UF: %{customdata[0]}<br>"
                            "Bioma: %{customdata[1]}<br>"
                            "Observado: %{customdata[2]}<br>"
                            "FRP: %{customdata[3]}<br>"
                            "Lat/Lon: %{lat:.4f}, %{lon:.4f}"
                            "<extra>%{fullData.name}</extra>"
                        ),
                    )
                )
            map_figure.update_layout(
                map={
                    "style": "carto-positron",
                    "center": {"lat": -14.2, "lon": -51.9},
                    "zoom": 3,
                },
                title=f"{len(map_frame):,} pontos exibidos".replace(",", "."),
                margin={"l": 0, "r": 0, "t": 42, "b": 0},
                legend_title_text="Satélite",
                height=590,
            )

            frame["hour"] = frame["observed_at"].dt.floor("h")
            timeline = frame.groupby("hour", as_index=False).size()
            timeline_figure = go.Figure(
                go.Scatter(
                    x=timeline["hour"].tolist(),
                    y=timeline["size"].tolist(),
                    mode="lines",
                    fill="tozeroy",
                    line={"color": "#e2542f", "width": 2},
                    fillcolor="rgba(226,84,47,.18)",
                    hovertemplate="%{x}<br>%{y} detecções<extra></extra>",
                )
            )
            timeline_figure.update_layout(
                template="plotly_white",
                xaxis_title="Hora (UTC)",
                yaxis_title="Detecções",
                margin={"l": 45, "r": 20, "t": 20, "b": 45},
                showlegend=False,
            )

            ranking = (
                frame.groupby("state_display", as_index=False)
                .size()
                .sort_values("size", ascending=True)
                .tail(10)
            )
            ranking_figure = go.Figure(
                go.Bar(
                    x=ranking["size"].tolist(),
                    y=ranking["state_display"].tolist(),
                    orientation="h",
                    marker={"color": "#286b57"},
                    hovertemplate="%{y}: %{x} detecções<extra></extra>",
                )
            )
            ranking_figure.update_layout(
                template="plotly_white",
                xaxis_title="Detecções",
                yaxis_title="UF",
                margin={"l": 45, "r": 20, "t": 20, "b": 45},
                showlegend=False,
            )

            table_frame = frame.head(250).copy()
            table_frame["observed_local"] = table_frame["observed_at"].map(
                lambda value: value.tz_convert(BRASILIA).strftime("%d/%m/%Y %H:%M")
            )
            table_frame["frp"] = table_frame["frp"].map(
                lambda value: "—" if pd.isna(value) else f"{value:.1f}"
            )
            table_data = table_frame[
                ["observed_local", "state_code", "municipality", "biome", "satellite", "frp"]
            ].fillna("—").to_dict("records")
        else:
            no_data = "Nenhuma detecção encontrada para os filtros selecionados."
            map_figure = _empty_figure(no_data)
            timeline_figure = _empty_figure(no_data)
            ranking_figure = _empty_figure(no_data)
            table_data = []

        latest_run = health.get("latest_run") or {}
        monitoring = [
            html.Div(
                [
                    html.Span("Estado da ingestão"),
                    html.Strong(latest_run.get("status", "sem execução")),
                ],
                className="monitor-item",
            ),
            html.Div(
                [
                    html.Span("Registros armazenados"),
                    html.Strong(f"{health['total_records']:,}".replace(",", ".")),
                ],
                className="monitor-item",
            ),
            html.Div(
                [
                    html.Span("Baixados na última execução"),
                    html.Strong(
                        f"{latest_run.get('downloaded_count', 0):,}".replace(",", ".")
                    ),
                ],
                className="monitor-item",
            ),
            html.Div(
                [
                    html.Span("Inseridos / atualizados"),
                    html.Strong(
                        f"{latest_run.get('inserted_count', 0)} / "
                        f"{latest_run.get('updated_count', 0)}"
                    ),
                ],
                className="monitor-item",
            ),
            html.Div(
                [
                    html.Span("Rejeitados"),
                    html.Strong(str(latest_run.get("rejected_count", 0))),
                ],
                className="monitor-item",
            ),
            html.Div(
                [
                    html.Span("Observação mais recente"),
                    html.Strong(_local_time(health.get("newest_observed_at"))),
                ],
                className="monitor-item",
            ),
        ]

        top_state = (
            f"{summary['top_state']} ({summary['top_state_count']:,})".replace(",", ".")
            if summary["top_state"]
            else "Sem dados"
        )
        state_options = [{"label": value, "value": value} for value in options["states"]]
        biome_options = [{"label": value, "value": value} for value in options["biomes"]]
        satellite_options = [
            {"label": value, "value": value} for value in options["satellites"]
        ]
        return (
            banner,
            banner_class,
            f"Painel atualizado: {_local_time(datetime.now(UTC))}",
            f"{summary['total']:,}".replace(",", "."),
            str(summary["affected_states"]),
            top_state,
            _local_time(summary["newest_observed_at"]),
            map_figure,
            timeline_figure,
            ranking_figure,
            table_data,
            monitoring,
            state_options,
            biome_options,
            satellite_options,
        )

    return app


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    app = create_app(settings)
    app.run(host=settings.host, port=settings.port, debug=settings.debug)


if __name__ == "__main__":
    main()
