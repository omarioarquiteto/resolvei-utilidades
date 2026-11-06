from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from opcoes_digitais_auth import _get_session
from opcoes_digitais_engine import MIN_CANDLES, STRATEGIES, analyze_trend_strength
from opcoes_digitais_analista_bin import ANALISTA_BIN_STRATEGIES, analyze_opcoes_signal

router = APIRouter(prefix="/api/opcoes-digitais", tags=["OPÇÕES DIGITAIS"])

INTERVALS = {"1m": 60, "5m": 300}
CANDLE_COUNT = 320
CANDLE_REQUEST_TIMEOUT = 12
ASSET_CACHE_TTL = 60
HISTORY_COLLECTION = "opcoesDigitaisSignals"
_HISTORY_MEMORY: dict[str, list[dict[str, Any]]] = {}


class Req(BaseModel):
    symbol: str
    timeframe: str = "1m"
    strategy: str = "auto"


def _account_key(item: dict) -> str:
    email = str(item.get("email") or "").strip().lower()
    if not email:
        return hashlib.sha256(b"opcoes-digitais-anonimo").hexdigest()
    return hashlib.sha256(email.encode("utf-8")).hexdigest()


def _firestore_collection():
    try:
        import firebase_admin
        from firebase_admin import firestore

        if not firebase_admin._apps:
            return None
        return firestore.client().collection(HISTORY_COLLECTION)
    except Exception:
        return None


def _asset_cache(item: dict) -> dict:
    return item.setdefault("asset_cache", {"at": 0.0, "data": None})


async def _ensure_connection(item: dict) -> None:
    client = item["client"]
    ws = getattr(client, "_ws", None)
    if ws is None:
        await client.connect()
        return
    if bool(getattr(ws, "_closed", False)):
        try:
            await client.close()
        except Exception:
            pass
        await client.connect()


async def _load_assets(item: dict) -> dict:
    cache = _asset_cache(item)
    now = time.time()
    if cache["data"] is not None and now - cache["at"] < ASSET_CACHE_TTL:
        return cache["data"]

    try:
        asset_client = item.get("asset_client")
        if asset_client is None:
            from iqoptionapi.stable_api import IQ_Option

            ws = getattr(item["client"], "_ws", None)
            ssid = getattr(ws, "_ssid", None)
            if not ssid:
                raise RuntimeError("SSID da sessão IQ Option não está disponível.")

            asset_client = IQ_Option(
                getattr(item["client"], "_email", ""),
                getattr(item["client"], "_password", ""),
                set_ssid=ssid,
                auto_logout=False,
            )
            ok = await asyncio.wait_for(asyncio.to_thread(asset_client.connect), 12)
            if ok is not None and isinstance(ok, tuple) and ok and ok[0] is False:
                reason = ok[1] if len(ok) > 1 else "conexão recusada"
                raise RuntimeError(str(reason))
            item["asset_client"] = asset_client

        opcode = await asyncio.wait_for(
            asyncio.to_thread(asset_client.get_all_ACTIVES_OPCODE),
            5,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="A IQ Option demorou para disponibilizar o catálogo de ativos.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao consultar o catálogo da IQ Option: {type(exc).__name__}: {str(exc)[:180]}",
        ) from exc

    if not isinstance(opcode, dict) or not opcode:
        raise HTTPException(status_code=502, detail="A IQ Option não retornou ativos para esta sessão.")

    assets = []
    for symbol, active_id in opcode.items():
        normalized = str(symbol).strip()
        if normalized:
            assets.append({"symbol": normalized, "open": True, "activeId": active_id})

    assets.sort(key=lambda asset: asset["symbol"])
    data = {"groups": {"all": assets}, "updatedAt": int(now), "total": len(assets)}
    cache["at"] = now
    cache["data"] = data
    return data


def _history_records(account_key: str) -> tuple[list[dict[str, Any]], str]:
    collection = _firestore_collection()
    if collection is not None:
        try:
            documents = collection.where("accountKey", "==", account_key).stream()
            records = [doc.to_dict() or {} for doc in documents]
            records.sort(key=lambda record: float(record.get("createdAt") or 0), reverse=True)
            return records[:100], "firestore"
        except Exception:
            pass
    records = list(_HISTORY_MEMORY.get(account_key, []))
    records.sort(key=lambda record: float(record.get("createdAt") or 0), reverse=True)
    return records[:100], "memoria"


def _resolve_pending(
    account_key: str,
    symbol: str,
    timeframe: str,
    candles: list[dict[str, Any]],
) -> None:
    interval = INTERVALS[timeframe]
    by_time = {int(round(float(candle["time"]))): candle for candle in candles}
    collection = _firestore_collection()
    documents = []
    if collection is not None:
        try:
            documents = list(
                collection.where("accountKey", "==", account_key).stream()
            )
        except Exception:
            documents = []

    memory_records = _HISTORY_MEMORY.setdefault(account_key, [])
    cloud_ids = set()
    for document in documents:
        record = document.to_dict() or {}
        cloud_ids.add(document.id)
        if (
            record.get("status") != "PENDENTE"
            or record.get("symbol") != symbol
            or record.get("timeframe") != timeframe
        ):
            continue
        entry_time = int(round(float(record.get("entryCandleTime") or 0)))
        candle = by_time.get(entry_time)
        if candle is None:
            continue
        _settle_record(record, candle, document.reference)

    for record in memory_records:
        if (
            record.get("status") != "PENDENTE"
            or record.get("symbol") != symbol
            or record.get("timeframe") != timeframe
            or record.get("id") in cloud_ids
        ):
            continue
        entry_time = int(round(float(record.get("entryCandleTime") or 0)))
        candle = by_time.get(entry_time)
        if candle is not None:
            _settle_record(record, candle, None)


def _settle_record(
    record: dict[str, Any],
    candle: dict[str, Any],
    reference: Any,
) -> None:
    entry_price = float(candle["open"])
    close_price = float(candle["close"])
    direction = record.get("direction")
    if abs(close_price - entry_price) <= max(abs(entry_price) * 1e-10, 1e-12):
        outcome = "DRAW"
    elif (direction == "CALL" and close_price > entry_price) or (
        direction == "PUT" and close_price < entry_price
    ):
        outcome = "WIN"
    else:
        outcome = "LOSS"

    update = {
        "status": "RESOLVIDO",
        "outcome": outcome,
        "entryPrice": entry_price,
        "closePrice": close_price,
        "settledAt": time.time(),
        "resultSource": "CANDLE_SIMULADO",
        "simulated": True,
    }
    record.update(update)
    if reference is not None:
        try:
            reference.update(update)
        except Exception:
            pass


def _record_signal(
    account_key: str,
    symbol: str,
    timeframe: str,
    result: dict[str, Any],
    candle_time: float,
) -> None:
    if result.get("direction") not in ("CALL", "PUT"):
        return
    interval = INTERVALS[timeframe]
    record = {
        "id": uuid.uuid4().hex,
        "accountKey": account_key,
        "createdAt": time.time(),
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": result.get("strategy"),
        "strategyLabel": result.get("strategyLabel"),
        "direction": result.get("direction"),
        "score": float(result.get("score") or 0),
        "callScore": float(result.get("callScore") or 0),
        "putScore": float(result.get("putScore") or 0),
        "referencePrice": float(result.get("referencePrice") or 0),
        "candleTime": float(candle_time),
        "entryCandleTime": float(candle_time + interval),
        "expiryAt": float(candle_time + (2 * interval)),
        "expiryMinutes": int(interval / 60),
        "status": "PENDENTE",
        "outcome": None,
        "simulated": True,
        "analysisVersion": result.get("analysisVersion", "2.0"),
    }
    memory_records = _HISTORY_MEMORY.setdefault(account_key, [])
    memory_records.append(record)
    if len(memory_records) > 300:
        del memory_records[:-300]

    collection = _firestore_collection()
    if collection is not None:
        try:
            collection.document(record["id"]).set(record)
        except Exception:
            # A cópia em memória mantém o recurso disponível caso o Firestore oscile.
            pass


def _update_history_after_analysis(
    account_key: str,
    symbol: str,
    timeframe: str,
    candles: list[dict[str, Any]],
    result: dict[str, Any],
    candle_time: float,
) -> None:
    _resolve_pending(account_key, symbol, timeframe, candles)
    _record_signal(account_key, symbol, timeframe, result, candle_time)


@router.get("/assets")
async def assets(x_iq_session: str | None = Header(default=None)):
    return await _load_assets(_get_session(x_iq_session))


@router.get("/config")
async def config(x_iq_session: str | None = Header(default=None)):
    _get_session(x_iq_session)
    return {
        "strategies": {key: value["name"] for key, value in STRATEGIES.items()},
        "strategyWeights": {
            key: value["weights"] for key, value in ANALISTA_BIN_STRATEGIES.items()
        },
        "supportedTimeframes": list(INTERVALS),
        "analysisEngine": "Analista Bin",
        "analysisVersion": "analista-bin-shared-v1",
    }


@router.get("/history")
async def history(x_iq_session: str | None = Header(default=None)):
    item = _get_session(x_iq_session)
    account_key = _account_key(item)
    records, storage = await asyncio.to_thread(_history_records, account_key)
    wins = sum(1 for record in records if record.get("outcome") == "WIN")
    losses = sum(1 for record in records if record.get("outcome") == "LOSS")
    draws = sum(1 for record in records if record.get("outcome") == "DRAW")
    pending = sum(1 for record in records if record.get("status") == "PENDENTE")
    settled = wins + losses
    rate = round(100 * wins / settled, 1) if settled else None
    visible = [
        {
            "id": record.get("id"),
            "symbol": record.get("symbol"),
            "timeframe": record.get("timeframe"),
            "strategyLabel": record.get("strategyLabel"),
            "direction": record.get("direction"),
            "score": record.get("score"),
            "createdAt": record.get("createdAt"),
            "status": record.get("status"),
            "outcome": record.get("outcome"),
            "simulated": bool(record.get("simulated", True)),
        }
        for record in records
    ]
    return {
        "ok": True,
        "storage": storage,
        "sampleSize": settled,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "pending": pending,
        "winRate": rate,
        "records": visible,
        "note": "Resultados simulados pela variação entre abertura e fechamento da próxima vela. Não são resultados de ordens executadas na corretora.",
    }


@router.post("/analyze")
async def run(req: Req, x_iq_session: str | None = Header(default=None)):
    item = _get_session(x_iq_session)

    if req.timeframe not in INTERVALS:
        raise HTTPException(status_code=400, detail="Timeframe deve ser 1m ou 5m.")
    if req.strategy not in STRATEGIES:
        raise HTTPException(status_code=400, detail="Estratégia inválida.")

    symbol = req.symbol.upper().strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="Informe o par para análise.")

    interval = INTERVALS[req.timeframe]
    catalog = await _load_assets(item)
    known = {
        asset["symbol"]
        for group in catalog["groups"].values()
        for asset in group
    }
    if symbol not in known:
        raise HTTPException(
            status_code=400,
            detail=f"O ativo {symbol} não está presente no catálogo atual da IQ Option.",
        )

    try:
        await _ensure_connection(item)
        raw = await asyncio.wait_for(
            item["client"].get_candles(symbol, interval, CANDLE_COUNT, int(time.time())),
            CANDLE_REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"A IQ Option não respondeu aos candles de {symbol} dentro de {CANDLE_REQUEST_TIMEOUT}s.",
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"O par {symbol} não está disponível na tabela de ativos da IQ Option.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao obter candles da IQ Option: {str(exc)[:180]}",
        ) from exc

    rows = []
    for candle in raw or []:
        try:
            volume_value = candle.get("volume")
            rows.append(
                {
                    "time": float(candle.get("from", candle.get("to", 0))),
                    "open": float(candle["open"]),
                    "high": float(candle.get("max", candle.get("high"))),
                    "low": float(candle.get("min", candle.get("low"))),
                    "close": float(candle["close"]),
                    "volume": (
                        float(volume_value)
                        if volume_value is not None
                        else None
                    ),
                }
            )
        except (TypeError, ValueError, KeyError):
            continue

    rows.sort(key=lambda row: row["time"])
    now = time.time()
    closed = [
        row for row in rows
        if row["time"] + interval <= now + 0.2
    ]
    if len(closed) < MIN_CANDLES:
        raise HTTPException(
            status_code=502,
            detail=(
                f"A IQ Option retornou {len(closed)} candles fechados para {symbol}; "
                f"são necessários pelo menos {MIN_CANDLES}. A vela em formação não será usada."
            ),
        )

    candle_time = float(closed[-1]["time"])
    try:
        result = await asyncio.to_thread(
            analyze_opcoes_signal,
            closed[-CANDLE_COUNT:],
            req.strategy,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha no motor de análise: {type(exc).__name__}: {str(exc)[:220]}",
        ) from exc

    result.update(
        {
            "ok": True,
            "symbol": symbol,
            "timeframe": req.timeframe,
            "candleTime": candle_time,
            "nextCandleAt": ((int(now) // interval) + 1) * interval,
            "referencePrice": float(closed[-1]["close"]),
        }
    )

    account_key = _account_key(item)
    asyncio.create_task(
        asyncio.to_thread(
            _update_history_after_analysis,
            account_key,
            symbol,
            req.timeframe,
            closed[-CANDLE_COUNT:],
            result,
            candle_time,
        )
    )
    return result


TREND_THRESHOLD = 85.0
TREND_CANDLE_COUNT = 150
TREND_SCAN_CONCURRENCY = 5
TREND_CANDLE_TIMEOUT = 9.0


def _trend_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    task = state.get("task")
    results = sorted(
        list((state.get("results") or {}).values()),
        key=lambda result: float(result.get("strength") or 0),
        reverse=True,
    )
    return {
        "ok": True,
        "timeframe": state.get("timeframe", "1m"),
        "threshold": TREND_THRESHOLD,
        "isRunning": bool(task is not None and not task.done()),
        "scanInProgress": bool(state.get("scanInProgress")),
        "scannedAssets": int(state.get("scannedAssets") or 0),
        "totalAssets": int(state.get("totalAssets") or 0),
        "scanErrors": int(state.get("scanErrors") or 0),
        "scanStartedAt": state.get("scanStartedAt"),
        "scanCompletedAt": state.get("scanCompletedAt"),
        "results": results,
    }


def _normalize_trend_candle(
    candle: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    try:
        candle_time = float(candle.get("from", candle.get("time", candle.get("to", 0))))
        close_price = float(candle["close"])
        open_price = float(candle.get("open", previous["open"] if previous else close_price))
        high_value = float(candle.get("max", candle.get("high", previous["high"] if previous else max(open_price, close_price))))
        low_value = float(candle.get("min", candle.get("low", previous["low"] if previous else min(open_price, close_price))))
        volume_value = candle.get("volume", previous.get("volume") if previous else None)
        if candle_time <= 0:
            return None
        return {
            "time": candle_time,
            "open": open_price,
            "high": max(high_value, open_price, close_price),
            "low": min(low_value, open_price, close_price),
            "close": close_price,
            "volume": float(volume_value) if volume_value is not None else None,
        }
    except (TypeError, ValueError, KeyError):
        return None


async def _publish_trend_score(
    state: dict[str, Any],
    symbol: str,
    rows: list[dict[str, Any]],
) -> None:
    if len(rows) < 110:
        state["results"].pop(symbol, None)
        return
    trend = await asyncio.to_thread(
        analyze_trend_strength, rows[-TREND_CANDLE_COUNT:]
    )
    if (
        float(trend.get("strength") or 0) > TREND_THRESHOLD
        and trend.get("direction") in ("CALL", "PUT")
    ):
        state["results"][symbol] = {
            "symbol": symbol,
            "strength": float(trend["strength"]),
            "direction": trend["direction"],
            "trendLabel": trend["trendLabel"],
            "adx": float(trend.get("adx") or 0),
            "updatedAt": time.time(),
        }
    else:
        # Remove assim que a força cair abaixo do limite configurado.
        state["results"].pop(symbol, None)


async def _trend_scan_loop(item: dict[str, Any], state: dict[str, Any]) -> None:
    interval = INTERVALS[state["timeframe"]]
    history_semaphore = asyncio.Semaphore(TREND_SCAN_CONCURRENCY)
    state["scanInProgress"] = True
    state["scanStartedAt"] = time.time()

    catalog = await _load_assets(item)
    assets_by_symbol = {}
    for group in (catalog.get("groups") or {}).values():
        for asset in group or []:
            symbol = str(asset.get("symbol") or "").strip()
            if symbol:
                assets_by_symbol[symbol] = asset
    assets = list(assets_by_symbol.values())
    state["totalAssets"] = len(assets)

    async def monitor_asset(asset: dict[str, Any]) -> None:
        symbol = str(asset.get("symbol") or "").strip()
        active_id = asset.get("activeId")
        if not symbol or active_id is None:
            state["scannedAssets"] += 1
            return

        counted = False
        while True:
            iterator = None
            try:
                async with history_semaphore:
                    now = time.time()
                    raw = await asyncio.wait_for(
                        item["client"].get_candles(
                            int(active_id), interval, TREND_CANDLE_COUNT, int(now)
                        ),
                        timeout=TREND_CANDLE_TIMEOUT,
                    )

                rows = []
                for candle in raw or []:
                    row = _normalize_trend_candle(candle)
                    if row is not None:
                        rows.append(row)
                rows.sort(key=lambda row: row["time"])
                if len(rows) < 110 or not rows or time.time() - rows[-1]["time"] > max(interval * 3, 180):
                    state["results"].pop(symbol, None)
                    if not counted:
                        counted = True
                        state["scannedAssets"] += 1
                    return

                rows = rows[-TREND_CANDLE_COUNT:]
                await _publish_trend_score(state, symbol, rows)

                if not counted:
                    counted = True
                    state["scannedAssets"] += 1
                    if state["scannedAssets"] >= state["totalAssets"]:
                        state["scanInProgress"] = False
                        state["scanCompletedAt"] = time.time()

                # O feed candle-generated entrega alterações do candle em formação.
                # Assim a pontuação muda junto com as atualizações enviadas pela corretora.
                await asyncio.sleep(0.04)
                stream = item["client"].stream_candles(int(active_id), interval)
                iterator = stream.__aiter__()
                last_evaluation = 0.0

                while True:
                    update = await asyncio.wait_for(
                        iterator.__anext__(),
                        timeout=max(interval * 3, 180),
                    )
                    latest_time = float(update.get("from", update.get("time", 0)) or 0)
                    previous = next(
                        (row for row in reversed(rows) if row["time"] == latest_time),
                        None,
                    )
                    row = _normalize_trend_candle(update, previous)
                    if row is None:
                        continue

                    existing_index = next(
                        (index for index in range(len(rows) - 1, -1, -1) if rows[index]["time"] == row["time"]),
                        None,
                    )
                    if existing_index is not None:
                        rows[existing_index] = row
                    elif not rows or row["time"] > rows[-1]["time"]:
                        rows.append(row)
                        if len(rows) > TREND_CANDLE_COUNT:
                            rows = rows[-TREND_CANDLE_COUNT:]
                    else:
                        continue

                    monotonic_now = asyncio.get_running_loop().time()
                    if monotonic_now - last_evaluation >= 3.0:
                        await _publish_trend_score(state, symbol, rows)
                        last_evaluation = monotonic_now

            except StopAsyncIteration:
                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                raise
            except Exception:
                state["scanErrors"] = int(state.get("scanErrors") or 0) + 1
                previous = state["results"].get(symbol)
                if previous and time.time() - float(previous.get("updatedAt") or 0) > max(interval * 3, 180):
                    state["results"].pop(symbol, None)
                if not counted:
                    counted = True
                    state["scannedAssets"] += 1
                    if state["scannedAssets"] >= state["totalAssets"]:
                        state["scanInProgress"] = False
                        state["scanCompletedAt"] = time.time()
                await asyncio.sleep(8.0)
            finally:
                if iterator is not None:
                    try:
                        await iterator.aclose()
                    except Exception:
                        pass

    try:
        await _ensure_connection(item)
        tasks = [asyncio.create_task(monitor_asset(asset)) for asset in assets]
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        state["scanInProgress"] = False
        raise
    except Exception as exc:
        state["scanInProgress"] = False
        state["lastError"] = type(exc).__name__
        raise


@router.get("/trends")
async def trends(
    timeframe: str = "1m",
    x_iq_session: str | None = Header(default=None),
):
    item = _get_session(x_iq_session)
    if timeframe not in INTERVALS:
        raise HTTPException(status_code=400, detail="Timeframe deve ser 1m ou 5m.")

    catalog = await _load_assets(item)
    state = item.get("trend_scanner")
    task = state.get("task") if isinstance(state, dict) else None

    if (
        not isinstance(state, dict)
        or state.get("timeframe") != timeframe
        or task is None
        or task.done()
    ):
        if task is not None and not task.done():
            task.cancel()

        state = {
            "timeframe": timeframe,
            "results": {},
            "totalAssets": int(catalog.get("total") or 0),
            "scannedAssets": 0,
            "scanErrors": 0,
            "scanInProgress": False,
            "scanStartedAt": None,
            "scanCompletedAt": None,
            "task": None,
        }
        item["trend_scanner"] = state
        state["task"] = asyncio.create_task(_trend_scan_loop(item, state))

    return _trend_snapshot(state)


@router.post("/trends/stop")
async def stop_trends(x_iq_session: str | None = Header(default=None)):
    item = _get_session(x_iq_session)
    state = item.get("trend_scanner") or {}
    task = state.get("task")
    if task is not None and not task.done():
        task.cancel()
    return {"ok": True}
