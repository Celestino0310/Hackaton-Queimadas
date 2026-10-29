"""
QueimAlerta - Monitoramento de Queimadas no Brasil
===================================================

Backend Flask que:
  * Consome a API pública de Localidades do IBGE (regioes / estados / municipios)
  * Agrega estatisticas de focos de queimadas por regiao / estado / municipio
  * Permite registrar (reportar) uma queimada ocorrendo agora
  * Combina relatos dos usuarios com uma base historica de focos

Fontes de dados publicas:
  * IBGE - API de Localidades:
      https://servicodados.ibge.gov.br/api/docs/localidades
  * INPE - Programa Queimadas (focos de calor):
      https://terrabrasilis.dpi.inpe.br/queimadas/portal/dados-abertos/
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request, send_from_directory

# --------------------------------------------------------------------------- #
# Configuracao
# --------------------------------------------------------------------------- #

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
REPORTS_FILE = os.path.join(DATA_DIR, "reports.json")
OCCURRENCES_FILE = os.path.join(DATA_DIR, "occurrences.json")

IBGE_BASE = "https://servicodados.ibge.gov.br/api/v1/localidades"
HTTP_TIMEOUT = 15

os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")


# --------------------------------------------------------------------------- #
# CORS — permite que o app nativo (Capacitor) ou uma PWA em outro host
# consumam a API. Como a API e publica/somente leitura + relatos simples,
# liberamos todas as origens.
# --------------------------------------------------------------------------- #

@app.after_request
def _add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    # o service worker precisa de escopo raiz
    if request.path.endswith("sw.js"):
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/api/<path:_any>", methods=["OPTIONS"])
@app.route("/<path:_any>", methods=["OPTIONS"])
def _cors_preflight(_any):
    return ("", 204)


# --------------------------------------------------------------------------- #
# Cache simples em memoria para respostas do IBGE
# --------------------------------------------------------------------------- #

_cache = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 60 * 60 * 24  # 24h


def _cache_get(key):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry["ts"] < _CACHE_TTL):
            return entry["value"]
    return None


def _cache_set(key, value):
    with _cache_lock:
        _cache[key] = {"value": value, "ts": time.time()}


def _ibge_get(path):
    """GET em uma rota da API do IBGE com cache."""
    key = f"ibge:{path}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    url = f"{IBGE_BASE}{path}"
    resp = requests.get(url, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    _cache_set(key, data)
    return data


# --------------------------------------------------------------------------- #
# Persistencia de relatos (reports) dos usuarios
# --------------------------------------------------------------------------- #

_reports_lock = threading.Lock()


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_reports():
    return _load_json(REPORTS_FILE, [])


def save_reports(reports):
    _save_json(REPORTS_FILE, reports)


# --------------------------------------------------------------------------- #
# Base de ocorrencias (focos historicos)
# --------------------------------------------------------------------------- #

def load_occurrences():
    """
    Carrega a base de ocorrencias historicas de focos de calor.
    Estrutura: lista de { "uf": "SP", "municipio": "...", "focos": 123 }
    Se o arquivo nao existir, gera uma base derivada de valores reais
    agregados do INPE (ano de referencia) para permitir o funcionamento
    offline da demonstracao.
    """
    data = _load_json(OCCURRENCES_FILE, None)
    if data is None:
        data = _default_occurrences()
        _save_json(OCCURRENCES_FILE, data)
    return data


def _default_occurrences():
    """
    Totais anuais aproximados de focos de calor por UF (satelite de
    referencia, ordem de grandeza baseada em divulgacoes do INPE/Programa
    Queimadas). Servem como base de demonstracao agregada por estado.
    Os relatos em tempo real enviados pelos usuarios somam-se a estes numeros.
    """
    por_uf = {
        "AC": 8500, "AL": 1200, "AP": 2600, "AM": 38000, "BA": 18000,
        "CE": 4200, "DF": 900, "ES": 1100, "GO": 15000, "MA": 29000,
        "MT": 72000, "MS": 23000, "MG": 19000, "PA": 68000, "PB": 2300,
        "PR": 5600, "PE": 3800, "PI": 14000, "RJ": 1500, "RN": 1800,
        "RS": 4800, "RO": 21000, "RR": 7400, "SC": 2100, "SP": 11000,
        "SE": 700, "TO": 26000,
    }
    return [{"uf": uf, "municipio": None, "focos": focos}
            for uf, focos in por_uf.items()]


# --------------------------------------------------------------------------- #
# Rotas de dados geograficos (IBGE)
# --------------------------------------------------------------------------- #

@app.route("/api/regioes")
def api_regioes():
    try:
        return jsonify(_ibge_get("/regioes"))
    except requests.RequestException as exc:
        return jsonify({"error": "Falha ao consultar IBGE", "detail": str(exc)}), 502


@app.route("/api/estados")
def api_estados():
    """Lista estados, opcionalmente filtrando por regiao (?regiao=ID)."""
    regiao = request.args.get("regiao")
    try:
        if regiao:
            estados = _ibge_get(f"/regioes/{regiao}/estados?orderBy=nome")
        else:
            estados = _ibge_get("/estados?orderBy=nome")
        return jsonify(estados)
    except requests.RequestException as exc:
        return jsonify({"error": "Falha ao consultar IBGE", "detail": str(exc)}), 502


@app.route("/api/municipios")
def api_municipios():
    """Lista municipios de um estado (?uf=SP ou ?uf=35)."""
    uf = request.args.get("uf")
    if not uf:
        return jsonify({"error": "Parametro 'uf' obrigatorio"}), 400
    try:
        municipios = _ibge_get(f"/estados/{uf}/municipios?orderBy=nome")
        return jsonify(municipios)
    except requests.RequestException as exc:
        return jsonify({"error": "Falha ao consultar IBGE", "detail": str(exc)}), 502


# --------------------------------------------------------------------------- #
# Rotas de estatisticas de ocorrencias
# --------------------------------------------------------------------------- #

def _uf_sigla_para_regiao():
    """Mapa UF -> {regiao_nome, uf_nome} usando o IBGE (com cache)."""
    try:
        estados = _ibge_get("/estados?orderBy=nome")
    except requests.RequestException:
        return {}
    mapa = {}
    for e in estados:
        mapa[e["sigla"]] = {
            "uf_nome": e["nome"],
            "regiao_id": e["regiao"]["id"],
            "regiao_nome": e["regiao"]["nome"],
        }
    return mapa


@app.route("/api/ocorrencias")
def api_ocorrencias():
    """
    Ranking de ocorrencias (focos historicos + relatos de usuarios).

    Parametros opcionais:
      ?nivel=uf|regiao     -> agrupamento (default: uf)
      ?regiao=<nome|id>    -> filtra por regiao
      ?uf=<sigla>          -> filtra por estado
      ?limit=<n>           -> limita o numero de linhas
    """
    nivel = request.args.get("nivel", "uf")
    filtro_regiao = request.args.get("regiao")
    filtro_uf = request.args.get("uf")
    limit = request.args.get("limit", type=int)

    base = load_occurrences()
    reports = load_reports()
    info = _uf_sigla_para_regiao()

    # Agrega focos historicos por UF
    por_uf = {}
    for row in base:
        uf = row["uf"]
        por_uf.setdefault(uf, 0)
        por_uf[uf] += row.get("focos", 0)

    # Soma relatos de usuarios (cada relato conta como 1 ocorrencia ativa)
    relatos_por_uf = {}
    for r in reports:
        uf = (r.get("uf") or "").upper()
        if uf:
            relatos_por_uf[uf] = relatos_por_uf.get(uf, 0) + 1
            por_uf[uf] = por_uf.get(uf, 0) + 1

    # Monta linhas enriquecidas
    linhas = []
    for uf, focos in por_uf.items():
        meta = info.get(uf, {})
        linhas.append({
            "uf": uf,
            "uf_nome": meta.get("uf_nome", uf),
            "regiao_nome": meta.get("regiao_nome", "Desconhecida"),
            "regiao_id": meta.get("regiao_id"),
            "focos": focos,
            "relatos_ativos": relatos_por_uf.get(uf, 0),
        })

    # Filtros
    if filtro_uf:
        fu = filtro_uf.upper()
        linhas = [l for l in linhas if l["uf"] == fu]
    if filtro_regiao:
        fr = str(filtro_regiao).lower()
        linhas = [l for l in linhas
                  if fr in str(l["regiao_nome"]).lower()
                  or fr == str(l["regiao_id"])]

    # Agrupamento por regiao
    if nivel == "regiao":
        agg = {}
        for l in linhas:
            key = l["regiao_nome"]
            agg.setdefault(key, {
                "regiao_nome": key,
                "regiao_id": l["regiao_id"],
                "focos": 0,
                "relatos_ativos": 0,
            })
            agg[key]["focos"] += l["focos"]
            agg[key]["relatos_ativos"] += l["relatos_ativos"]
        linhas = list(agg.values())

    linhas.sort(key=lambda x: x["focos"], reverse=True)
    if limit:
        linhas = linhas[:limit]

    total = sum(l["focos"] for l in linhas)
    return jsonify({
        "nivel": nivel,
        "total_focos": total,
        "total_relatos_ativos": len(reports),
        "itens": linhas,
    })


# --------------------------------------------------------------------------- #
# Rotas de relatos (reportar queimada agora)
# --------------------------------------------------------------------------- #

@app.route("/api/reports", methods=["GET"])
def api_list_reports():
    reports = load_reports()
    reports.sort(key=lambda r: r.get("criado_em", ""), reverse=True)
    return jsonify(reports)


@app.route("/api/reports", methods=["POST"])
def api_create_report():
    payload = request.get_json(silent=True) or {}

    uf = (payload.get("uf") or "").strip().upper()
    municipio = (payload.get("municipio") or "").strip()
    descricao = (payload.get("descricao") or "").strip()
    intensidade = (payload.get("intensidade") or "media").strip().lower()
    lat = payload.get("lat")
    lon = payload.get("lon")

    if not uf or len(uf) != 2:
        return jsonify({"error": "Campo 'uf' (sigla com 2 letras) e obrigatorio"}), 400
    if not municipio:
        return jsonify({"error": "Campo 'municipio' e obrigatorio"}), 400
    if intensidade not in ("baixa", "media", "alta"):
        intensidade = "media"

    report = {
        "id": str(uuid.uuid4()),
        "uf": uf,
        "municipio": municipio,
        "descricao": descricao,
        "intensidade": intensidade,
        "lat": lat,
        "lon": lon,
        "criado_em": datetime.now(timezone.utc).isoformat(),
        "status": "ativo",
    }

    with _reports_lock:
        reports = load_reports()
        reports.append(report)
        save_reports(reports)

    return jsonify(report), 201


@app.route("/api/reports/<report_id>", methods=["DELETE"])
def api_delete_report(report_id):
    with _reports_lock:
        reports = load_reports()
        novos = [r for r in reports if r.get("id") != report_id]
        if len(novos) == len(reports):
            return jsonify({"error": "Relato nao encontrado"}), 404
        save_reports(novos)
    return jsonify({"ok": True})


# --------------------------------------------------------------------------- #
# Frontend
# --------------------------------------------------------------------------- #

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # host 0.0.0.0 -> acessivel por celulares na mesma rede Wi-Fi
    # (use o IP da maquina no app: Configuracoes > Endereco do servidor)
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(host=host, port=port, debug=True)
