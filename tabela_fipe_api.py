from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any, Callable
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/fipe", tags=["Tabela FIPE"])
BRASIL_API_BASE = "https://brasilapi.com.br/api"
_ALLOWED_TYPES = {"carros", "motos", "caminhoes"}
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = Lock()


def _cached(key: str, ttl_seconds: int, loader: Callable[[], Any]) -> Any:
    now = time.monotonic()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item and item[0] > now:
            return item[1]
        if item:
            _CACHE.pop(key, None)
    value = loader()
    with _CACHE_LOCK:
        if len(_CACHE) > 2500:
            expired = [k for k, v in _CACHE.items() if v[0] <= time.monotonic()]
            for old_key in expired[:1000]:
                _CACHE.pop(old_key, None)
        _CACHE[key] = (time.monotonic() + ttl_seconds, value)
    return value


def _download_json(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{BRASIL_API_BASE}{path}"
    try:
        response = requests.get(
            url,
            params=params or {},
            headers={
                "Accept": "application/json",
                "User-Agent": "Resolvei-TabelaFIPE/1.0",
            },
            timeout=(4, 15),
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail="A BrasilAPI não respondeu. Tente novamente em instantes.",
        ) from exc

    if response.status_code in (400, 404):
        raise HTTPException(
            status_code=404,
            detail="Não foram encontrados dados FIPE para esta seleção ou referência.",
        )
    if response.status_code == 429:
        raise HTTPException(
            status_code=503,
            detail="A BrasilAPI limitou temporariamente as consultas. Tente novamente em instantes.",
        )
    if response.status_code >= 500:
        raise HTTPException(
            status_code=502,
            detail="O serviço da BrasilAPI está temporariamente indisponível.",
        )
    try:
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="A BrasilAPI retornou uma resposta inválida.",
        ) from exc


def _get_json(path: str, params: dict[str, Any] | None = None, ttl_seconds: int = 21600) -> Any:
    query = urlencode(sorted((params or {}).items()))
    key = f"{path}?{query}"
    return _cached(key, ttl_seconds, lambda: _download_json(path, params))


def _vehicle_type(value: str) -> str:
    if value not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de veículo inválido.")
    return value


def _numeric_id(value: str, label: str) -> str:
    if not re.fullmatch(r"\d{1,8}", str(value)):
        raise HTTPException(status_code=400, detail=f"Código de {label} inválido.")
    return str(value)


def _parse_brl(value: Any) -> float | None:
    if value is None:
        return None
    raw = str(value).strip().replace("R$", "").replace("\u00a0", "").replace(" ", "")
    if not raw:
        return None
    # The BrasilAPI returns Brazilian currency strings such as "R$ 123.456,78".
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


@router.get("/brands/{vehicle_type}")
def brands(vehicle_type: str):
    vehicle_type = _vehicle_type(vehicle_type)
    data = _get_json(f"/fipe/marcas/v1/{vehicle_type}", ttl_seconds=86400)
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="Formato inesperado na lista de marcas.")
    return data


@router.get("/models/{vehicle_type}/{brand_id}")
def models(vehicle_type: str, brand_id: str):
    vehicle_type = _vehicle_type(vehicle_type)
    brand_id = _numeric_id(brand_id, "marca")
    data = _get_json(f"/fipe/veiculos/v1/{vehicle_type}/{brand_id}", ttl_seconds=86400)
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="Formato inesperado na lista de modelos.")
    return data


@router.get("/years/{vehicle_type}/{brand_id}/{model_id}")
def years(vehicle_type: str, brand_id: str, model_id: str):
    vehicle_type = _vehicle_type(vehicle_type)
    brand_id = _numeric_id(brand_id, "marca")
    model_id = _numeric_id(model_id, "modelo")
    data = _get_json(
        f"/fipe/anos/v1/{vehicle_type}/{brand_id}/{model_id}",
        ttl_seconds=86400,
    )
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="Formato inesperado na lista de anos.")
    return data


@router.get("/details/{vehicle_type}/{brand_id}/{model_id}/{year_code:path}")
def details(vehicle_type: str, brand_id: str, model_id: str, year_code: str):
    vehicle_type = _vehicle_type(vehicle_type)
    brand_id = _numeric_id(brand_id, "marca")
    model_id = _numeric_id(model_id, "modelo")
    # FIPE year codes generally look like "2022-1"; only allow this safe form.
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", year_code):
        raise HTTPException(status_code=400, detail="Código de ano-modelo inválido.")
    data = _get_json(
        f"/fipe/detalhes/v1/{vehicle_type}/{brand_id}/{model_id}/{year_code}",
        ttl_seconds=21600,
    )
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Formato inesperado nos dados do veículo.")
    return data


def _table_references() -> list[dict[str, Any]]:
    raw = _get_json("/fipe/tabelas/v1", ttl_seconds=3600)
    if not isinstance(raw, list):
        raise HTTPException(status_code=502, detail="Formato inesperado na lista de referências FIPE.")
    refs: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = item.get("codigo", item.get("code"))
        month = item.get("mes", item.get("month", ""))
        try:
            code_int = int(code)
        except (TypeError, ValueError):
            continue
        refs.append({"codigo": code_int, "mes": str(month).strip()})
    refs.sort(key=lambda item: item["codigo"])
    return refs


def _history_point(fipe_code: str, year_model: int, reference: dict[str, Any]) -> dict[str, Any] | None:
    code = reference["codigo"]
    try:
        raw = _get_json(
            f"/fipe/preco/v1/{fipe_code}",
            params={"tabela_referencia": code},
            ttl_seconds=86400,
        )
    except HTTPException:
        # A model/version may not exist in every older reference; keep gaps rather than
        # fabricating values or failing the entire chart.
        return None

    candidates = raw if isinstance(raw, list) else [raw]
    for item in candidates:
        if not isinstance(item, dict):
            continue
        try:
            item_year = int(item.get("anoModelo", item.get("modelYear")))
        except (TypeError, ValueError):
            continue
        if item_year != year_model:
            continue
        raw_price = item.get("valor", item.get("price"))
        price = _parse_brl(raw_price)
        if price is None or price <= 0:
            continue
        month = str(item.get("mesReferencia") or reference["mes"]).strip()
        return {
            "referencia": code,
            "mes": month,
            "valor": round(price, 2),
            "valorFormatado": str(raw_price).strip(),
        }
    return None


@router.get("/history/{fipe_code}")
def history(
    fipe_code: str,
    year_model: int = Query(..., ge=0, le=9999),
    months: int = Query(12, ge=3, le=24),
):
    if not re.fullmatch(r"\d{6}-\d", fipe_code):
        raise HTTPException(status_code=400, detail="Código FIPE inválido.")

    def load_history():
        refs = _table_references()
        if not refs:
            return {
                "codigoFipe": fipe_code,
                "anoModelo": year_model,
                "mesesSolicitados": months,
                "historico": [],
            }
        selected = refs[-(months + 1):]
        points: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(_history_point, fipe_code, year_model, ref): ref
                for ref in selected
            }
            for future in as_completed(futures):
                try:
                    point = future.result()
                except Exception:
                    point = None
                if point:
                    points.append(point)
        points.sort(key=lambda point: point["referencia"])
        return {
            "codigoFipe": fipe_code,
            "anoModelo": year_model,
            "mesesSolicitados": months,
            "historico": points,
            "fonte": "BrasilAPI — Tabela FIPE",
        }

    return _cached(
        f"history:{fipe_code}:{year_model}:{months}",
        21600,
        load_history,
    )
