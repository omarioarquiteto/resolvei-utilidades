"""Radar de Ofertas: descoberta por loja, aprovação/publicação no Telegram."""
from __future__ import annotations

import base64
import hashlib
import html
import os
import re
from datetime import timedelta
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from monitor_precos_api import _db, _iso, _now, _price, _score, _shopping, _text, _uid

router = APIRouter(prefix="/api/deal-radar", tags=["radar-ofertas"])

STORES = {
    "mercado_livre": "Mercado Livre",
    "amazon": "Amazon",
    "shopee": "Shopee",
    "magalu": "Magazine Luiza",
}
INTERVALS = (15, 30, 60, 180, 360)


class MonitorInput(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    store: str = Field(default="mercado_livre", max_length=30)
    keywords: list[str] = Field(default_factory=list)
    min_discount_percent: float = Field(default=10, ge=0, le=90)
    max_price: float | None = Field(default=None, gt=0, le=100000000)
    interval_minutes: int = Field(default=30, ge=15, le=360)
    publish_mode: str = Field(default="approval", max_length=20)
    active: bool = True


class AffiliateLinkInput(BaseModel):
    affiliate_url: str = Field(min_length=8, max_length=2048)


class TelegramConnectInput(BaseModel):
    bot_token: str = Field(min_length=20, max_length=300)
    channel_username: str = Field(min_length=2, max_length=80)


def _monitors(uid: str):
    return _db().collection("users").document(uid).collection("dealRadarMonitors")


def _telegram_ref(uid: str):
    return _db().collection("users").document(uid).collection("dealRadarSettings").document("telegram")


def _normal(value: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()


def _clean_monitor(req: MonitorInput) -> dict:
    store = str(req.store or "").strip().lower()
    if store not in STORES:
        raise HTTPException(422, "Escolha uma loja disponível.")
    if req.publish_mode not in {"approval", "automatic"}:
        raise HTTPException(422, "Escolha publicação automática ou com aprovação.")
    if req.interval_minutes not in INTERVALS:
        raise HTTPException(422, "Os intervalos permitidos são 15, 30, 60, 180 ou 360 minutos.")
    keywords = []
    for raw in req.keywords[:5]:
        word = _text(raw, 100)
        if len(word) >= 2 and word.casefold() not in {x.casefold() for x in keywords}:
            keywords.append(word)
    if not keywords:
        raise HTTPException(422, "Informe pelo menos uma palavra-chave.")
    if req.max_price is not None and req.max_price <= 0:
        raise HTTPException(422, "O preço máximo precisa ser maior que zero.")
    return {
        "title": _text(req.title, 100),
        "store": store,
        "storeLabel": STORES[store],
        "keywords": keywords,
        "minDiscountPercent": round(float(req.min_discount_percent), 2),
        "maxPrice": round(float(req.max_price), 2) if req.max_price is not None else None,
        "intervalMinutes": int(req.interval_minutes),
        "publishMode": req.publish_mode,
        "active": bool(req.active),
    }


def _credential_key() -> bytes:
    value = os.getenv("RESOLVEI_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    if not value:
        raise HTTPException(503, "A criptografia de credenciais do Resolvei não está configurada no Render.")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))
        if len(raw) != 32:
            raise ValueError
        return raw
    except Exception as exc:
        raise HTTPException(503, "A chave de criptografia do Resolvei está inválida.") from exc


def _encrypt_secret(secret: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    encrypted = AESGCM(_credential_key()).encrypt(nonce, secret.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def _decrypt_secret(value: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    return AESGCM(_credential_key()).decrypt(raw[:12], raw[12:], None).decode("utf-8")


def _telegram_call(token: str, method: str, payload: dict | None = None) -> dict:
    try:
        response = requests.post(
            "https://api.telegram.org/bot" + token + "/" + method,
            json=payload or {},
            timeout=(5, 20),
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(502, "Não foi possível se comunicar com o Telegram agora.") from exc
    if response.status_code >= 400 or not data.get("ok"):
        description = _text(data.get("description") if isinstance(data, dict) else "", 220)
        raise HTTPException(502, "O Telegram recusou a operação: " + (description or "erro não especificado"))
    return data.get("result") or {}


def _telegram_settings(uid: str) -> dict:
    snapshot = _telegram_ref(uid).get()
    return snapshot.to_dict() or {} if snapshot.exists else {}


def _public_telegram_settings(uid: str) -> dict:
    data = _telegram_settings(uid)
    return {
        "connected": bool(data.get("connected")),
        "channelUsername": _text(data.get("channelUsername"), 80),
        "botUsername": _text(data.get("botUsername"), 80),
        "connectedAt": _text(data.get("connectedAt"), 80),
    }


def _affiliate_url(value: str, store: str) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower().rstrip(".")
    permitted_hosts = {
        "mercado_livre": {"meli.la", "mercadolivre.com.br", "mercadolivre.com", "mercadolibre.com", "meli.com"},
        "amazon": {"amzn.to", "amazon.com.br", "amazon.com"},
        "shopee": {"shopee.com.br", "shope.ee"},
        "magalu": {"magazineluiza.com.br", "magazinevoce.com.br"},
    }
    allowed = permitted_hosts.get(store, set())
    permitted = host in allowed or any(host.endswith("." + domain) for domain in allowed if domain not in {"meli.la", "amzn.to", "shope.ee"})
    if parsed.scheme != "https" or not host or not permitted or parsed.username or parsed.password:
        raise HTTPException(422, "Cole um link de afiliado HTTPS válido para a loja deste monitoramento.")
    return raw[:2048]


def _store_match(store: str, offer: dict) -> bool:
    expected = _normal(STORES[store]).replace(" ", "")
    source = _normal(offer.get("source", "")).replace(" ", "")
    host = (urlparse(str(offer.get("url") or "")).hostname or "").lower()
    if expected in source or expected in host.replace(".", ""):
        return True
    if store == "mercado_livre":
        return "mercadolivre" in source or "mercadolivre.com.br" in host or "meli.la" in host
    if store == "magalu":
        return "magazineluiza" in source or "magalu" in source or "magazineluiza.com.br" in host
    return False


def _qualifies(offer: dict, monitor: dict, previous: dict | None = None) -> tuple[float | None, bool]:
    price = _price(offer.get("price"))
    original = _price(offer.get("original_price"))
    prior = _price((previous or {}).get("currentPrice"))
    discount = None
    if original is not None and price is not None and original > price:
        discount = round((original - price) / original * 100, 2)
    elif prior is not None and price is not None and prior > price:
        discount = round((prior - price) / prior * 100, 2)
    max_price = _price(monitor.get("maxPrice"))
    if price is None or (max_price is not None and price > max_price):
        return discount, False
    min_discount = float(monitor.get("minDiscountPercent") or 0)
    eligible = discount is not None and discount >= min_discount
    if discount is None and min_discount == 0 and max_price is not None:
        eligible = True
    return discount, eligible


def _telegram_post(uid: str, offer: dict, monitor: dict) -> dict:
    settings = _telegram_settings(uid)
    if not settings.get("connected") or not settings.get("tokenEncrypted") or not settings.get("channelUsername"):
        raise HTTPException(409, "Conecte o bot do Telegram e informe um canal público antes de publicar.")
    affiliate = _affiliate_url(str(offer.get("affiliateUrl") or ""))
    token = _decrypt_secret(settings["tokenEncrypted"])
    title = html.escape(_text(offer.get("title"), 220) or "Oferta encontrada")
    source = html.escape(_text(offer.get("source"), 80) or monitor.get("storeLabel") or "Loja")
    price = _price(offer.get("currentPrice"))
    old_price = _price(offer.get("originalPrice"))
    discount = offer.get("discountPercent")
    lines = ["<b>" + title + "</b>"]
    if old_price is not None and price is not None and old_price > price:
        lines.append("<s>De " + ("R$ {:,.2f}".format(old_price).replace(",", "X").replace(".", ",").replace("X", ".")) + "</s>")
    if price is not None:
        lines.append("<b>Por " + ("R$ {:,.2f}".format(price).replace(",", "X").replace(".", ",").replace("X", ".")) + "</b>")
    if discount is not None:
        lines.append("🔥 <b>{:.1f}% de desconto</b>".format(float(discount)).replace(".", ","))
    lines.append("🏬 " + source)
    lines.append("")
    lines.append("⚠️ Confira preço, frete e disponibilidade na loja.")
    caption = "\n".join(lines)
    payload = {
        "chat_id": settings["channelUsername"],
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [[{"text": "🛒 VER OFERTA", "url": affiliate}]]
        },
    }
    image_url = str(offer.get("image_url") or "").strip()
    if image_url.startswith("https://"):
        payload.update({"photo": image_url, "caption": caption[:1024]})
        return _telegram_call(token, "sendPhoto", payload)
    payload.update({"text": caption + "\n<a href=\"" + html.escape(affiliate, quote=True) + "\">🛒 VER OFERTA</a>"})
    return _telegram_call(token, "sendMessage", payload)


def _publish_opportunity(uid: str, monitor_ref, opportunity_ref, monitor: dict, opportunity: dict) -> dict:
    result = _telegram_post(uid, opportunity, monitor)
    sent_at = _iso()
    opportunity_ref.set({
        "status": "published",
        "lastSentAt": sent_at,
        "lastSentPrice": _price(opportunity.get("currentPrice")),
        "telegramMessageId": str((result.get("message_id") or "")),
        "lastPublishError": "",
    }, merge=True)
    return {"published": True, "messageId": result.get("message_id")}


def _scan_monitor(uid: str, monitor_ref, monitor: dict) -> dict:
    store = str(monitor.get("store") or "mercado_livre")
    if store not in STORES:
        raise HTTPException(422, "A loja deste monitor não é suportada.")
    keywords = [str(x) for x in (monitor.get("keywords") or [])[:5] if _text(x, 100)]
    if not keywords:
        raise HTTPException(422, "Este monitor não tem palavras-chave cadastradas.")
    opportunities_ref = monitor_ref.collection("opportunities")
    candidates: dict[str, dict] = {}
    for keyword in keywords:
        query = _text(keyword + " " + STORES[store], 180)
        for offer in _shopping(query):
            if not _store_match(store, offer):
                continue
            title = _text(offer.get("title"), 300)
            if not title or _score(keyword, title) < 0.30:
                continue
            # Exclui anúncios usados/recondicionados do Radar inicial.
            if re.search(r"\b(usado|usada|seminovo|seminova|recondicionado|recondicionada|open box)\b", _normal(title)):
                continue
            url = str(offer.get("url") or "").strip()
            if not url.startswith("https://"):
                continue
            key = hashlib.sha256((store + "|" + url.split("?")[0].rstrip("/")).encode("utf-8")).hexdigest()[:40]
            candidates[key] = {"offer": offer, "keyword": keyword}
    now = _now()
    scanned = 0
    eligible_count = 0
    published_count = 0
    pending_count = 0
    for key, candidate in list(candidates.items())[:max(1, min(int(monitor.get("maxResults") or 12), 20))]:
        offer = candidate["offer"]
        keyword = candidate["keyword"]
        url = str(offer.get("url") or "").strip()
        opportunity_ref = opportunities_ref.document(key)
        old_snapshot = opportunity_ref.get()
        previous = old_snapshot.to_dict() or {}
        price = _price(offer.get("price"))
        if price is None:
            continue
        discount, eligible = _qualifies(offer, monitor, previous)
        old_current = _price(previous.get("currentPrice"))
        original = _price(offer.get("original_price"))
        if original is None and old_current is not None and old_current > price:
            original = old_current
        status = str(previous.get("status") or "watching")
        if status == "ignored":
            continue
        affiliate = _text(previous.get("affiliateUrl"), 2048)
        last_sent = _price(previous.get("lastSentPrice"))
        lower_than_sent = last_sent is None or price < last_sent - 0.01
        data = {
            "title": _text(offer.get("title"), 300),
            "store": store,
            "source": _text(offer.get("source"), 100) or STORES[store],
            "url": url,
            "image_url": _text(offer.get("image_url"), 2048),
            "currentPrice": price,
            "originalPrice": original,
            "discountPercent": discount,
            "previousPrice": old_current,
            "affiliateUrl": affiliate,
            "lastSeenAt": _iso(now),
            "updatedAt": _iso(now),
            "eligible": eligible,
            "lastScanKeyword": keyword,
        }
        if not old_snapshot.exists:
            data["createdAt"] = _iso(now)
            data["firstSeenPrice"] = price
            data["status"] = "watching"
        if eligible:
            eligible_count += 1
            if monitor.get("publishMode") == "automatic":
                if affiliate and lower_than_sent:
                    status = "ready_to_publish"
                elif not affiliate:
                    status = "awaiting_affiliate_link"
            elif status != "published" or lower_than_sent:
                status = "pending_approval"
                pending_count += 1
        elif status not in {"published"}:
            status = "watching"
        data["status"] = status
        opportunity_ref.set(data, merge=True)
        scanned += 1
        if eligible and monitor.get("publishMode") == "automatic" and affiliate and lower_than_sent:
            try:
                _publish_opportunity(uid, monitor_ref, opportunity_ref, monitor, {**previous, **data})
                published_count += 1
            except HTTPException as exc:
                opportunity_ref.set({"status": "publish_error", "lastPublishError": _text(exc.detail, 240)}, merge=True)
    result = {
        "ok": True,
        "monitorId": monitor_ref.id,
        "store": STORES[store],
        "keywords": keywords,
        "resultsFound": len(candidates),
        "offersSaved": scanned,
        "eligibleOffers": eligible_count,
        "pendingApproval": pending_count,
        "published": published_count,
        "checkedAt": _iso(now),
    }
    next_scan = _iso(now + timedelta(minutes=int(monitor.get("intervalMinutes") or 30)))
    monitor_ref.set({
        "lastScanAt": _iso(now),
        "nextScanAt": next_scan,
        "lastScanError": "",
        "lastScanSummary": result,
        "updatedAt": _iso(now),
    }, merge=True)
    return result


@router.get("/monitors")
def list_monitors(authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    rows = []
    for snapshot in _monitors(uid).stream():
        row = snapshot.to_dict() or {}
        row["id"] = snapshot.id
        rows.append(row)
    rows.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    return {"monitors": rows}


@router.post("/monitors")
def create_monitor(req: MonitorInput, authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    data = _clean_monitor(req)
    now = _now()
    data.update({
        "createdAt": _iso(now),
        "updatedAt": _iso(now),
        "lastScanAt": "",
        "nextScanAt": _iso(now),
        "lastScanError": "",
        "lastScanSummary": {},
        "maxResults": 12,
    })
    ref = _monitors(uid).document()
    ref.set(data)
    return {"monitor": {"id": ref.id, **data}}


@router.put("/monitors/{monitor_id}")
def update_monitor(monitor_id: str, req: MonitorInput, authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    ref = _monitors(uid).document(monitor_id)
    if not ref.get().exists:
        raise HTTPException(404, "Monitor não encontrado.")
    data = _clean_monitor(req)
    data.update({
        "updatedAt": _iso(),
        "nextScanAt": _iso(),
    })
    ref.set(data, merge=True)
    return {"monitor": {"id": ref.id, **(ref.get().to_dict() or {})}}


@router.delete("/monitors/{monitor_id}")
def delete_monitor(monitor_id: str, authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    ref = _monitors(uid).document(monitor_id)
    if not ref.get().exists:
        raise HTTPException(404, "Monitor não encontrado.")
    ref.delete()
    return {"ok": True}


@router.post("/monitors/{monitor_id}/scan")
def scan_monitor(monitor_id: str, authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    ref = _monitors(uid).document(monitor_id)
    snapshot = ref.get()
    if not snapshot.exists:
        raise HTTPException(404, "Monitor não encontrado.")
    monitor = snapshot.to_dict() or {}
    if not monitor.get("active", True):
        raise HTTPException(409, "Este monitor está pausado.")
    try:
        result = _scan_monitor(uid, ref, monitor)
    except HTTPException as exc:
        ref.set({"lastScanAt": _iso(), "nextScanAt": _iso(_now() + timedelta(minutes=30)),
                 "lastScanError": _text(exc.detail, 240)}, merge=True)
        raise
    return result


@router.get("/monitors/{monitor_id}/opportunities")
def list_opportunities(monitor_id: str, authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    monitor_ref = _monitors(uid).document(monitor_id)
    if not monitor_ref.get().exists:
        raise HTTPException(404, "Monitor não encontrado.")
    rows = []
    for snapshot in monitor_ref.collection("opportunities").stream():
        row = snapshot.to_dict() or {}
        row["id"] = snapshot.id
        rows.append(row)
    rows.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    return {"opportunities": rows[:100]}


@router.post("/monitors/{monitor_id}/opportunities/{opportunity_id}/affiliate")
def save_affiliate_link(monitor_id: str, opportunity_id: str, req: AffiliateLinkInput,
                        authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    monitor_ref = _monitors(uid).document(monitor_id)
    monitor_snapshot = monitor_ref.get()
    if not monitor_snapshot.exists:
        raise HTTPException(404, "Monitor não encontrado.")
    monitor = monitor_snapshot.to_dict() or {}
    opportunity_ref = monitor_ref.collection("opportunities").document(opportunity_id)
    snapshot = opportunity_ref.get()
    if not snapshot.exists:
        raise HTTPException(404, "Oportunidade não encontrada.")
    opportunity = snapshot.to_dict() or {}
    affiliate = _affiliate_url(req.affiliate_url, str(monitor.get("store") or "mercado_livre"))
    opportunity_ref.set({"affiliateUrl": affiliate, "updatedAt": _iso()}, merge=True)
    opportunity["affiliateUrl"] = affiliate
    if monitor.get("publishMode") == "automatic" and opportunity.get("eligible"):
        last_sent = _price(opportunity.get("lastSentPrice"))
        current = _price(opportunity.get("currentPrice"))
        if last_sent is None or (current is not None and current < last_sent - 0.01):
            try:
                _publish_opportunity(uid, monitor_ref, opportunity_ref, monitor, opportunity)
                return {"ok": True, "published": True}
            except HTTPException as exc:
                opportunity_ref.set({"status": "publish_error", "lastPublishError": _text(exc.detail, 240)}, merge=True)
                raise
    return {"ok": True, "published": False}


@router.post("/monitors/{monitor_id}/opportunities/{opportunity_id}/approve")
def approve_opportunity(monitor_id: str, opportunity_id: str,
                        authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    monitor_ref = _monitors(uid).document(monitor_id)
    monitor_snapshot = monitor_ref.get()
    if not monitor_snapshot.exists:
        raise HTTPException(404, "Monitor não encontrado.")
    monitor = monitor_snapshot.to_dict() or {}
    opportunity_ref = monitor_ref.collection("opportunities").document(opportunity_id)
    snapshot = opportunity_ref.get()
    if not snapshot.exists:
        raise HTTPException(404, "Oportunidade não encontrada.")
    opportunity = snapshot.to_dict() or {}
    if not opportunity.get("eligible"):
        raise HTTPException(409, "Esta oportunidade não atende mais aos critérios do monitor.")
    if not opportunity.get("affiliateUrl"):
        raise HTTPException(409, "Cadastre o link de afiliado deste produto antes de aprovar.")
    last_sent = _price(opportunity.get("lastSentPrice"))
    current = _price(opportunity.get("currentPrice"))
    if last_sent is not None and current is not None and current >= last_sent - 0.01:
        raise HTTPException(409, "Esta oportunidade já foi publicada por este preço.")
    result = _publish_opportunity(uid, monitor_ref, opportunity_ref, monitor, opportunity)
    return {"ok": True, **result}


@router.post("/monitors/{monitor_id}/opportunities/{opportunity_id}/ignore")
def ignore_opportunity(monitor_id: str, opportunity_id: str,
                       authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    ref = _monitors(uid).document(monitor_id).collection("opportunities").document(opportunity_id)
    if not ref.get().exists:
        raise HTTPException(404, "Oportunidade não encontrada.")
    ref.set({"status": "ignored", "eligible": False, "updatedAt": _iso()}, merge=True)
    return {"ok": True}


@router.get("/telegram")
def telegram_status(authorization: str | None = Header(default=None)):
    return _public_telegram_settings(_uid(authorization))


@router.post("/telegram/connect")
def connect_telegram(req: TelegramConnectInput, authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    token = req.bot_token.strip()
    channel = req.channel_username.strip()
    if not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", channel):
        raise HTTPException(422, "Informe o @username de um canal público do Telegram.")
    me = _telegram_call(token, "getMe")
    chat = _telegram_call(token, "getChat", {"chat_id": channel})
    if chat.get("type") != "channel":
        raise HTTPException(422, "O endereço informado não corresponde a um canal público do Telegram.")
    member = _telegram_call(token, "getChatMember", {"chat_id": channel, "user_id": me.get("id")})
    if member.get("status") not in {"administrator", "creator"} or member.get("can_post_messages") is False:
        raise HTTPException(422, "Adicione o bot ao canal como administrador e permita publicar mensagens.")
    _telegram_ref(uid).set({
        "connected": True,
        "tokenEncrypted": _encrypt_secret(token),
        "channelUsername": channel,
        "botUsername": _text(me.get("username"), 80),
        "connectedAt": _iso(),
        "updatedAt": _iso(),
    }, merge=True)
    return _public_telegram_settings(uid)


@router.post("/telegram/test")
def test_telegram(authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    settings = _telegram_settings(uid)
    if not settings.get("tokenEncrypted") or not settings.get("channelUsername"):
        raise HTTPException(409, "Conecte primeiro seu bot e canal.")
    token = _decrypt_secret(settings["tokenEncrypted"])
    result = _telegram_call(token, "sendMessage", {
        "chat_id": settings["channelUsername"],
        "text": "✅ Conexão do Radar de Ofertas Resolvei confirmada. As publicações de teste estão funcionando.",
    })
    return {"ok": True, "messageId": result.get("message_id")}


@router.delete("/telegram")
def disconnect_telegram(authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    _telegram_ref(uid).delete()
    return {"ok": True}


@router.post("/admin/scan-due")
def scan_due_monitors(
    batch_size: int = Query(default=5, ge=1, le=20),
    x_price_monitor_cron_key: str | None = Header(default=None, alias="X-Price-Monitor-Cron-Key"),
):
    expected = os.getenv("PRICE_MONITOR_CRON_KEY", "").strip()
    if not expected or not x_price_monitor_cron_key or not __import__("secrets").compare_digest(expected, x_price_monitor_cron_key):
        raise HTTPException(403, "Chave de execução automática ausente ou inválida.")
    now_text = _iso(_now())
    collection = _db().collection_group("dealRadarMonitors")
    due = list(collection.where("nextScanAt", "<=", now_text).order_by("nextScanAt").limit(batch_size).stream())
    processed = errors = published = eligible = 0
    results = []
    for snapshot in due:
        monitor = snapshot.to_dict() or {}
        if monitor.get("active") is False:
            continue
        uid = snapshot.reference.parent.parent.id
        try:
            result = _scan_monitor(uid, snapshot.reference, monitor)
            processed += 1
            published += int(result.get("published") or 0)
            eligible += int(result.get("eligibleOffers") or 0)
            results.append(result)
        except Exception as exc:
            errors += 1
            message = _text(getattr(exc, "detail", "") or type(exc).__name__, 220)
            snapshot.reference.set({
                "lastScanAt": _iso(),
                "nextScanAt": _iso(_now() + timedelta(minutes=30)),
                "lastScanError": message,
            }, merge=True)
            results.append({"monitorId": snapshot.id, "ok": False, "error": message})
    return {
        "ok": errors == 0,
        "scannedDueCandidates": len(due),
        "processed": processed,
        "eligibleOffers": eligible,
        "published": published,
        "errors": errors,
        "checkedAt": _iso(),
        "results": results,
    }


# Agendamento independente: cada monitor dispara conforme sua própria frequência.
import asyncio
import threading

_radar_task = None
_radar_lock = threading.Lock()


async def _radar_scheduler_loop():
    while True:
        try:
            now_text = _iso(_now())
            query = (
                _db().collection_group("dealRadarMonitors")
                .where("nextScanAt", "<=", now_text)
                .order_by("nextScanAt")
                .limit(max(1, min(int(os.getenv("DEAL_RADAR_SCAN_BATCH", "5")), 20)))
            )
            due = list(query.stream())
            for snapshot in due:
                monitor = snapshot.to_dict() or {}
                if monitor.get("active") is False:
                    continue
                uid = snapshot.reference.parent.parent.id
                try:
                    await asyncio.to_thread(_scan_monitor, uid, snapshot.reference, monitor)
                except Exception as exc:
                    message = _text(getattr(exc, "detail", "") or type(exc).__name__, 220)
                    snapshot.reference.set({
                        "lastScanAt": _iso(),
                        "nextScanAt": _iso(_now() + timedelta(minutes=30)),
                        "lastScanError": message,
                        "updatedAt": _iso(),
                    }, merge=True)
                await asyncio.sleep(0.15)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Falhas temporárias do Firestore ou de índices não interrompem o serviço.
            pass
        await asyncio.sleep(max(15, int(os.getenv("DEAL_RADAR_SCHEDULER_SECONDS", "60"))))


def start_deal_radar_scheduler():
    global _radar_task
    with _radar_lock:
        if _radar_task is not None and not _radar_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        _radar_task = loop.create_task(_radar_scheduler_loop())
