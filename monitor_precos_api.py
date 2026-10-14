"""API do Monitor de Preços, isolada das demais ferramentas."""
from __future__ import annotations
import asyncio, hashlib, ipaddress, os, re, secrets, threading, uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from typing import Any
import requests
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/price-monitor", tags=["monitor-precos"])
_refresh_task = None
_refresh_lock = threading.Lock()
REFRESH_HOURS = 24
SCHEDULE_SECONDS = 6 * 60 * 60
SCHEDULE_BATCH = 5

class ProductCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=8, max_length=2048)
    price: float | None = Field(default=None, gt=0, le=100000000)
    target_price: float | None = Field(default=None, gt=0, le=100000000)
    brand: str = Field(default="", max_length=150)
    model: str = Field(default="", max_length=150)
    ean: str = Field(default="", max_length=32)
    image_url: str = Field(default="", max_length=2048)
    source: str = Field(default="Resolvei", max_length=80)

class PriceObservation(BaseModel):
    price: float = Field(gt=0, le=100000000)
    source: str = Field(default="Preço informado pelo usuário", max_length=100)

class TargetPriceUpdate(BaseModel):
    target_price: float | None = Field(default=None, gt=0, le=100000000)

def _now():
    return datetime.now(timezone.utc)

def _iso(value=None):
    return (value or _now()).isoformat()


def _firebase_uid_from_token(token: str) -> str:
    try:
        import firebase_admin
        from firebase_admin import auth
        if not firebase_admin._apps:
            raise HTTPException(503, "Firebase Admin não está configurado no servidor.")
        uid = str(auth.verify_id_token(token).get("uid") or "")
        if not uid:
            raise HTTPException(401, "Sessão Firebase inválida.")
        return uid
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(401, "Sessão inválida ou expirada. Entre novamente no Resolvei.") from exc


def _uid(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Entre na sua conta do Resolvei para usar o Monitor de Preços.")
    token = authorization[7:].strip()
    try:
        return _firebase_uid_from_token(token)
    except HTTPException as exc:
        if exc.status_code == 503:
            raise
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    snapshot = _db().collection("priceMonitorExtensionSessions").document(token_hash).get()
    if not snapshot.exists:
        raise HTTPException(401, "Sessão inválida ou expirada. Entre novamente no Resolvei.")
    session = snapshot.to_dict() or {}
    if not session.get("active", True) or not session.get("uid"):
        raise HTTPException(401, "Esta sessão da extensão foi encerrada. Entre novamente no Resolvei.")
    try:
        expires = datetime.fromisoformat(str(session.get("expiresAt") or "").replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(401, "A sessão da extensão expirou. Entre novamente.")
    if expires <= _now():
        raise HTTPException(401, "A sessão da extensão expirou. Entre novamente.")
    return str(session["uid"])

def _db():
    try:
        import firebase_admin
        from firebase_admin import firestore
        if not firebase_admin._apps:
            raise HTTPException(503, "Firebase Admin não está configurado no servidor.")
        return firestore.client()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Não foi possível acessar o banco do Resolvei.") from exc

def _products(uid):
    return _db().collection("users").document(uid).collection("priceMonitorProducts")

def _ref(uid, product_id):
    return _products(uid).document(product_id)

def _text(value, limit=300):
    return str(value or "").strip()[:limit]

def _validate_url(value):
    parsed = urlparse((value or "").strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(422, "Use uma URL HTTPS válida do produto.")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal", ".localhost")):
        raise HTTPException(422, "Esse endereço não pode ser monitorado.")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise HTTPException(422, "Endereços privados não são aceitos.")
    except ValueError:
        pass
    return value.strip()[:2048]

def _canonical(value):
    parsed = urlparse(value.strip())
    pairs = []
    for key, val in parse_qsl(parsed.query, keep_blank_values=True):
        low = key.lower()
        if low.startswith("utm_") or low in {"gclid", "fbclid", "msclkid", "scid", "trackingid"}:
            continue
        pairs.append((key, val))
    return urlunparse(("https", (parsed.hostname or "").lower(), parsed.path.rstrip("/") or "/", "", urlencode(sorted(pairs)), ""))

def _price(value):
    if isinstance(value, (float, int)):
        n = float(value)
        return round(n, 2) if 0 < n < 100000000 else None
    s = re.sub(r"[^0-9,.\-]", "", str(value or "")).strip()
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]
    try:
        n = float(s)
        return round(n, 2) if 0 < n < 100000000 else None
    except ValueError:
        return None

def _words(value):
    import unicodedata
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()
    stop = {"com", "para", "sem", "por", "the", "and", "novo", "nova", "original", "oficial", "promocao"}
    return {w for w in re.findall(r"[a-z0-9]+", text) if len(w) > 1 and w not in stop}

def _score(query, title):
    a, b = _words(query), _words(title)
    return round(len(a & b) / len(a), 3) if a and b else 0.0


def _flatten_offer_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return " ".join(_flatten_offer_text(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten_offer_text(v) for v in value)
    return ""


def _extract_conditions(text):
    text = _text(text, 1600)
    low = text.lower()
    free_shipping = True if re.search(r"frete\s+(?:gr[aá]tis|gratis|gratuito|gratuita)|envio\s+gr[aá]tis|entrega\s+gr[aá]tis", low) else None
    shipping_match = re.search(r"(?:frete|entrega|envio)[^.;\n]{0,100}", text, re.I)
    shipping_text = _text(shipping_match.group(0), 180) if shipping_match else ""
    installment_count = installment_amount = installment_total = installment_interest = None
    installment_text = ""
    installment_match = re.search(
        r"(\d{1,2})\s*x\s*(?:de\s*)?(?:R\$\s*)?([\d.]+,\d{2}|[\d,]+\.\d{2})?\s*(sem\s+juros|com\s+juros)?",
        text, re.I
    )
    if installment_match:
        count = int(installment_match.group(1))
        amount = _price(installment_match.group(2)) if installment_match.group(2) else None
        interest_text = (installment_match.group(3) or "").lower()
        if 1 <= count <= 48:
            installment_count = count
            installment_amount = amount
            installment_total = round(amount * count, 2) if amount else None
            if "sem juros" in interest_text:
                installment_interest = False
            elif "com juros" in interest_text:
                installment_interest = True
            installment_text = _text(installment_match.group(0), 180)
    coupons = []
    for match in re.finditer(r"(?:cupom|c[oó]digo\s+(?:promocional|de\s+desconto)|use\s+o\s+c[oó]digo)[^\n.;]{0,100}", text, re.I):
        snippet = match.group(0)
        tokens = re.findall(r"\b[A-Z0-9][A-Z0-9_-]{3,19}\b", snippet.upper())
        for token in tokens:
            if token not in {"CUPOM", "DESCONTO", "CODIGO", "PROMOCIONAL", "USE", "OFF"} and not any(c["code"] == token for c in coupons):
                coupons.append({"code": token, "description": _text(snippet, 160)})
        if len(coupons) >= 6:
            break
    return {
        "free_shipping": free_shipping,
        "shipping_text": shipping_text,
        "installment_count": installment_count,
        "installment_amount": installment_amount,
        "installment_total": installment_total,
        "installment_interest": installment_interest,
        "installment_text": installment_text,
        "coupons": coupons[:6],
    }


def _shopping(query):
    key = os.getenv("SERPAPI_KEY", "").strip()
    if not key:
        raise HTTPException(503, "A comparação entre lojas requer SERPAPI_KEY nas variáveis de ambiente do Render. A extensão continuará mostrando a base comunitária.")
    query = _text(query, 180)
    if len(query) < 2:
        raise HTTPException(422, "Informe o nome, marca ou modelo do produto.")
    try:
        response = requests.get("https://serpapi.com/search.json",
            params={"engine":"google_shopping","q":query,"gl":"br","hl":"pt-br","api_key":key},
            timeout=(5, 20), headers={"User-Agent":"ResolveiMonitorPrecos/2.0"})
    except requests.RequestException as exc:
        raise HTTPException(502, "Não foi possível consultar ofertas agora. Tente novamente mais tarde.") from exc
    if response.status_code == 429:
        raise HTTPException(429, "Limite de consultas do provedor de preços atingido. Tente novamente mais tarde.")
    if response.status_code >= 400:
        raise HTTPException(502, "O provedor de preços recusou a consulta. Confira SERPAPI_KEY e a cota disponível.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(502, "A pesquisa retornou uma resposta inválida.") from exc
    if payload.get("error"):
        raise HTTPException(502, "Falha na pesquisa: " + _text(payload["error"], 180))
    results, seen = [], set()
    for row in payload.get("shopping_results", []) or []:
        amount = _price(row.get("extracted_price")) or _price(row.get("price"))
        link = str(row.get("link") or row.get("product_link") or "").strip()
        if not amount or not link.startswith("https://"):
            continue
        canonical = _canonical(link)
        if canonical in seen:
            continue
        seen.add(canonical)
        source = _text(row.get("source"), 100) or (urlparse(link).hostname or "Loja")
        terms = " ".join(filter(None, [
            _text(row.get("title"), 300), _text(row.get("delivery"), 180),
            _flatten_offer_text(row.get("extensions")), _flatten_offer_text(row.get("snippets")),
            _flatten_offer_text(row.get("offers")), _flatten_offer_text(row.get("tags")),
        ]))
        conditions = _extract_conditions(terms)
        delivery = _text(row.get("delivery"), 180)
        if delivery and re.search(r"gr[aá]tis|gratis|gratuit", delivery, re.I):
            conditions["free_shipping"] = True
            conditions["shipping_text"] = delivery
        results.append({
            "title":_text(row.get("title"), 300), "price":amount, "source":source,
            "url":link[:2048], "image_url":_text(row.get("thumbnail"), 2048),
            "delivery":delivery, "rating":row.get("rating"), "reviews":row.get("reviews"),
            **conditions,
        })
    return sorted(results, key=lambda x:x["price"])[:20]

def _history(ref, event):
    ref.collection("history").document().set({**event, "observedAt":_iso()})

def _target_reached(product, target=None):
    target = product.get("targetPrice") if target is None else target
    if target is None:
        return False
    for key in ("price", "bestOfferPrice"):
        try:
            value = float(product.get(key))
            if value > 0 and value <= float(target):
                return True
        except (TypeError, ValueError):
            continue
    return False

def _serialize(snapshot):
    data = snapshot.to_dict() or {}
    data["id"] = snapshot.id
    return data

def _refresh_ref(ref, product):
    match_query = " ".join(x for x in [_text(product.get("title"),160),_text(product.get("brand"),70),
        _text(product.get("model"),70)] if x).strip()
    q = " ".join(x for x in [match_query, _text(product.get("ean"),20)] if x).strip()
    offers = _shopping(q)
    matched = [offer for offer in offers if _score(match_query, offer["title"]) >= 0.35]
    now = _now()
    updates = {"lastCheckedAt":_iso(now),"nextRefreshAt":_iso(now+timedelta(hours=REFRESH_HOURS)),
        "lastRefreshError":"","updatedAt":_iso(now)}
    if not matched:
        updates["lastRefreshError"] = "Não encontrei oferta que corresponda com confiança ao modelo. Revise os dados do produto."
        ref.update(updates)
        return {"ok":True,"matched":False,"message":updates["lastRefreshError"],"offers":[]}
    best = min(matched, key=lambda offer:offer["price"])
    previous = product.get("bestOfferPrice")
    updates.update({"offers":matched[:12],"bestOfferPrice":best["price"],
        "bestOfferSource":best["source"],"bestOfferUrl":best["url"],"bestOfferTitle":best["title"]})
    reached = _target_reached({**product, "bestOfferPrice":best["price"]})
    updates["targetReached"] = reached
    if reached and not product.get("targetReached"):
        updates["targetReachedAt"] = _iso(now)
    elif not reached:
        updates["targetReachedAt"] = ""
    if previous is None or abs(float(previous)-float(best["price"])) >= 0.01:
        _history(ref, {"price":best["price"],"kind":"best-offer","source":best["source"],
            "title":best["title"],"url":best["url"]})
    ref.update(updates)
    return {"ok":True,"matched":True,"bestOffer":best,"offers":matched[:12],"checkedAt":updates["lastCheckedAt"]}


@router.post("/extension/session")
def create_extension_session(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Entre na sua conta do Resolvei.")
    # Apenas um ID token Firebase válido pode criar uma sessão duradoura da extensão.
    uid = _firebase_uid_from_token(authorization[7:].strip())
    access_token = secrets.token_urlsafe(48)
    expires = _now() + timedelta(days=30)
    token_hash = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
    _db().collection("priceMonitorExtensionSessions").document(token_hash).set({
        "uid": uid,
        "active": True,
        "client": "resolvei-browser-extension",
        "createdAt": _iso(),
        "expiresAt": _iso(expires),
    })
    return {"accessToken": access_token, "expiresAt": _iso(expires), "expiresInDays": 30}


@router.post("/extension/session/revoke")
def revoke_extension_session(authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    token = authorization[7:].strip() if authorization else ""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    ref = _db().collection("priceMonitorExtensionSessions").document(token_hash)
    snapshot = ref.get()
    if snapshot.exists and str((snapshot.to_dict() or {}).get("uid") or "") == uid:
        ref.update({"active": False, "revokedAt": _iso()})
    return {"ok": True}


@router.get("/status")
def monitor_status(authorization: str | None = Header(default=None)):
    _uid(authorization)
    enabled = bool(os.getenv("SERPAPI_KEY", "").strip())
    return {"ok":True,"comparisonConfigured":enabled,"automaticRefresh":enabled,"refreshIntervalHours":REFRESH_HOURS,
        "coverageNote":"A cobertura depende das ofertas fornecidas pelo provedor e não inclui necessariamente todas as lojas da internet."}

@router.get("/products")
def list_products(authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    products = [_serialize(doc) for doc in _products(uid).stream()]
    products.sort(key=lambda p:str(p.get("updatedAt") or p.get("createdAt") or ""), reverse=True)
    return {"products":products}

@router.post("/products")
def add_product(req: ProductCreate, authorization: str | None = Header(default=None)):
    uid, url = _uid(authorization), _validate_url(req.url)
    collection, canonical = _products(uid), _canonical(url)
    snapshots = list(collection.limit(101).stream())
    for snapshot in snapshots:
        existing = snapshot.to_dict() or {}
        if _canonical(str(existing.get("url") or "")) != canonical:
            continue
        ref = snapshot.reference
        changes = {"updatedAt":_iso()}
        if req.target_price is not None:
            changes["targetPrice"] = req.target_price
            changes["targetReached"] = _target_reached(existing, req.target_price)
            changes["targetReachedAt"] = _iso() if changes["targetReached"] else ""
        if req.price is not None and (existing.get("price") is None or abs(float(existing["price"])-req.price) >= 0.01):
            changes["price"] = req.price
            _history(ref, {"price":req.price,"kind":"page-observation","source":req.source,"title":req.title,"url":url})
        for key, value in [("title",req.title),("brand",req.brand),("model",req.model),("ean",req.ean),("image_url",req.image_url)]:
            if value:
                changes[key] = _text(value, 2048 if key=="image_url" else 300)
        ref.update(changes)
        return {"product":_serialize(ref.get()),"existing":True}
    if len(snapshots) >= 100:
        raise HTTPException(413, "O limite inicial é de 100 produtos monitorados por conta.")
    now, product_id = _iso(), uuid.uuid4().hex
    data = {"title":_text(req.title),"url":url,"canonicalUrl":canonical,"price":req.price,
        "targetPrice":req.target_price,"targetReached":False,"targetReachedAt":"",
        "brand":_text(req.brand,150),"model":_text(req.model,150),"ean":_text(req.ean,32),
        "image_url":_text(req.image_url,2048),"source":_text(req.source,80) or (urlparse(url).hostname or "Página do produto"),
        "active":True,"offers":[],"bestOfferPrice":None,"bestOfferSource":"","bestOfferUrl":"",
        "createdAt":now,"updatedAt":now,"lastCheckedAt":"",
        "nextRefreshAt":_iso(_now()+timedelta(hours=REFRESH_HOURS)),"lastRefreshError":""}
    ref = collection.document(product_id)
    ref.set(data)
    if req.price is not None:
        _history(ref, {"price":req.price,"kind":"page-observation","source":data["source"],"title":data["title"],"url":url})
    if _target_reached(data):
        ref.update({"targetReached":True,"targetReachedAt":now})
    return {"product":_serialize(ref.get()),"existing":False}

@router.get("/products/{product_id}/history")
def product_history(product_id: str, authorization: str | None = Header(default=None)):
    ref = _ref(_uid(authorization), product_id)
    if not ref.get().exists:
        raise HTTPException(404, "Produto não encontrado.")
    events = []
    for snapshot in ref.collection("history").stream():
        event = snapshot.to_dict() or {}
        event["id"] = snapshot.id
        events.append(event)
    events.sort(key=lambda item:str(item.get("observedAt") or ""))
    return {"history":events}

@router.post("/products/{product_id}/observe")
def observe_price(product_id: str, req: PriceObservation, authorization: str | None = Header(default=None)):
    ref = _ref(_uid(authorization), product_id)
    snapshot = ref.get()
    if not snapshot.exists:
        raise HTTPException(404, "Produto não encontrado.")
    product, now = snapshot.to_dict() or {}, _iso()
    if product.get("price") is None or abs(float(product["price"])-req.price) >= 0.01:
        _history(ref, {"price":req.price,"kind":"page-observation","source":_text(req.source,100),
            "title":product.get("title",""),"url":product.get("url","")})
    reached = _target_reached({**product, "price":req.price})
    ref.update({"price":req.price,"source":_text(req.source,100),"updatedAt":now,"lastObservedAt":now,
        "targetReached":reached,"targetReachedAt":now if reached and not product.get("targetReached") else (product.get("targetReachedAt","") if reached else "")})
    return {"product":_serialize(ref.get())}

@router.post("/products/{product_id}/target")
def set_target_price(product_id: str, req: TargetPriceUpdate, authorization: str | None = Header(default=None)):
    ref = _ref(_uid(authorization), product_id)
    snapshot = ref.get()
    if not snapshot.exists:
        raise HTTPException(404, "Produto não encontrado.")
    product = snapshot.to_dict() or {}
    reached = _target_reached(product, req.target_price) if req.target_price is not None else False
    now = _iso()
    ref.update({"targetPrice":req.target_price,"targetReached":reached,
        "targetReachedAt":now if reached else "","updatedAt":now})
    return {"product":_serialize(ref.get())}

@router.post("/products/{product_id}/refresh")
def refresh_product(product_id: str, authorization: str | None = Header(default=None)):
    ref = _ref(_uid(authorization), product_id)
    snapshot = ref.get()
    if not snapshot.exists:
        raise HTTPException(404, "Produto não encontrado.")
    result = _refresh_ref(ref, snapshot.to_dict() or {})
    result["product"] = _serialize(ref.get())
    return result

@router.get("/search")
def compare_offers(q: str = Query(min_length=2, max_length=180), authorization: str | None = Header(default=None)):
    _uid(authorization)
    offers = _shopping(q)
    return {"query":q,"offers":[{**offer,"matchScore":_score(q,offer["title"])} for offer in offers],
        "coverageNote":"Confirme modelo, capacidade, condição, vendedor, frete, disponibilidade e forma de pagamento antes de comprar."}

@router.delete("/products/{product_id}")
def delete_product(product_id: str, authorization: str | None = Header(default=None)):
    ref = _ref(_uid(authorization), product_id)
    if not ref.get().exists:
        raise HTTPException(404, "Produto não encontrado.")
    for event in ref.collection("history").stream():
        event.reference.delete()
    ref.delete()
    return {"ok":True}


class CommunityObservation(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=8, max_length=2048)
    price: float | None = Field(default=None, gt=0, le=100000000)
    brand: str = Field(default="", max_length=150)
    model: str = Field(default="", max_length=150)
    ean: str = Field(default="", max_length=32)
    image_url: str = Field(default="", max_length=2048)
    free_shipping: bool | None = None
    shipping_text: str = Field(default="", max_length=240)
    installment_count: int | None = Field(default=None, ge=1, le=48)
    installment_amount: float | None = Field(default=None, gt=0, le=100000000)
    installment_total: float | None = Field(default=None, gt=0, le=100000000)
    installment_interest: bool | None = None
    installment_text: str = Field(default="", max_length=240)
    coupons: list[dict[str, str]] = Field(default_factory=list, max_length=10)


def _normalized_product_title(value: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:280]


def _community_key(req: CommunityObservation) -> str:
    ean = re.sub(r"\D", "", req.ean or "")
    if len(ean) in {8, 12, 13, 14}:
        identity = "ean:" + ean
    else:
        title = _normalized_product_title(req.title)
        brand = _normalized_product_title(req.brand)
        model = _normalized_product_title(req.model)
        identity = "product:" + "|".join(part for part in (brand, model, title) if part)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:40]


def _community_offer_id(url: str) -> str:
    parsed = urlparse(url)
    identity = (parsed.hostname or "").lower() + "|" + _canonical(url)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def _clean_coupons(items):
    cleaned, seen = [], set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        code = re.sub(r"[^A-Za-z0-9_-]", "", _text(item.get("code"), 50)).upper()
        description = _text(item.get("description"), 180)
        if not code or code in seen or len(code) < 3:
            continue
        if code in {"CUPOM", "DESCONTO", "CODIGO", "PROMO", "CUPONS", "OFFICIAL"}:
            continue
        seen.add(code)
        cleaned.append({"code": code, "description": description or "Identificado na página; confira validade e regras."})
        if len(cleaned) >= 10:
            break
    return cleaned


def _community_offer_payload(snapshot):
    data = snapshot.to_dict() or {}
    data["id"] = snapshot.id
    return data


def _community_offers(product_ref, limit=20):
    rows = [_community_offer_payload(doc) for doc in product_ref.collection("offers").limit(200).stream()]
    rows.sort(key=lambda item: (
        item.get("price") is None,
        float(item.get("price") or 0),
        str(item.get("updatedAt") or "")
    ))
    return rows[:limit]


def _community_history(product_ref, limit=12):
    events = []
    for offer_doc in product_ref.collection("offers").limit(100).stream():
        for event_doc in offer_doc.reference.collection("history").limit(60).stream():
            event = event_doc.to_dict() or {}
            event["id"] = event_doc.id
            events.append(event)
    events.sort(key=lambda item: str(item.get("observedAt") or ""), reverse=True)
    return events[:limit]


@router.post("/community/observe")
def observe_community_product(req: CommunityObservation, authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    url = _validate_url(req.url)
    now_dt, now = _now(), _iso()
    today = now_dt.date().isoformat()
    product_key = _community_key(req)
    product_ref = _db().collection("communityPriceProducts").document(product_key)
    prior_product = product_ref.get()
    current_product = prior_product.to_dict() or {}
    host = (urlparse(url).hostname or "loja").lower()
    offer_id = _community_offer_id(url)
    offer_ref = product_ref.collection("offers").document(offer_id)
    prior_offer = offer_ref.get()
    old_offer = prior_offer.to_dict() or {}
    price = req.price if req.price is not None else old_offer.get("price")
    coupons = _clean_coupons(req.coupons)
    if not coupons:
        coupons = old_offer.get("coupons", [])
    free_shipping = req.free_shipping if req.free_shipping is not None else old_offer.get("free_shipping")
    shipping_text = _text(req.shipping_text, 240) or _text(old_offer.get("shipping_text"), 240)
    installment_count = req.installment_count if req.installment_count is not None else old_offer.get("installment_count")
    installment_amount = req.installment_amount if req.installment_amount is not None else old_offer.get("installment_amount")
    installment_total = req.installment_total if req.installment_total is not None else old_offer.get("installment_total")
    installment_interest = req.installment_interest if req.installment_interest is not None else old_offer.get("installment_interest")
    installment_text = _text(req.installment_text, 240) or _text(old_offer.get("installment_text"), 240)
    product_data = {
        "title": _text(req.title, 300),
        "brand": _text(req.brand, 150) or current_product.get("brand", ""),
        "model": _text(req.model, 150) or current_product.get("model", ""),
        "ean": re.sub(r"\D", "", _text(req.ean, 32)) or current_product.get("ean", ""),
        "image_url": _text(req.image_url, 2048) or current_product.get("image_url", ""),
        "updatedAt": now,
        "lastObservedAt": now,
    }
    if not prior_product.exists:
        product_data["createdAt"] = now
        product_data["contributorCount"] = 0
        product_data["stores"] = []
    from google.cloud.firestore_v1 import ArrayUnion, Increment
    product_data["stores"] = ArrayUnion([host])
    product_ref.set(product_data, merge=True)
    offer_data = {
        "title": _text(req.title, 300),
        "source": host,
        "url": url,
        "price": price,
        "image_url": _text(req.image_url, 2048) or old_offer.get("image_url", ""),
        "free_shipping": free_shipping,
        "shipping_text": shipping_text,
        "installment_count": installment_count,
        "installment_amount": installment_amount,
        "installment_total": installment_total,
        "installment_interest": installment_interest,
        "installment_text": installment_text,
        "coupons": coupons,
        "updatedAt": now,
        "lastObservedAt": now,
    }
    if req.price is not None:
        offer_data["priceObservedAt"] = now
        price_event_id = hashlib.sha256(f"{today}|{req.price:.2f}".encode("utf-8")).hexdigest()[:28]
        history_ref = offer_ref.collection("history").document(price_event_id)
        if not history_ref.get().exists:
            history_ref.set({
                "price": round(req.price, 2),
                "source": host,
                "url": url,
                "title": _text(req.title, 300),
                "observedAt": now,
                "free_shipping": free_shipping,
                "shipping_text": shipping_text,
                "installment_count": installment_count,
                "installment_amount": installment_amount,
                "installment_total": installment_total,
                "installment_interest": installment_interest,
                "coupons": coupons,
            })
    if not prior_offer.exists:
        offer_data["createdAt"] = now
    offer_ref.set(offer_data, merge=True)
    contribution_id = hashlib.sha256((uid + "|" + product_key + "|" + today).encode("utf-8")).hexdigest()[:32]
    contribution_ref = product_ref.collection("contributions").document(contribution_id)
    if not contribution_ref.get().exists:
        contribution_ref.set({"date": today, "contributorRef": contribution_id, "createdAt": now})
        product_ref.set({"contributorCount": Increment(1)}, merge=True)
    product_snapshot = product_ref.get().to_dict() or {}
    all_offers = _community_offers(product_ref, limit=30)
    priced = [item for item in all_offers if isinstance(item.get("price"), (int, float)) and item["price"] > 0]
    return {
        "ok": True,
        "productKey": product_key,
        "product": {**product_snapshot, "id": product_key},
        "offers": all_offers,
        "bestOffer": priced[0] if priced else None,
        "contributorCount": int(product_snapshot.get("contributorCount") or 0),
        "communityShared": True,
    }


@router.get("/community/search")
def search_community_products(
    q: str = Query(min_length=2, max_length=180),
    authorization: str | None = Header(default=None),
):
    _uid(authorization)
    query_words = _words(q)
    matches = []
    # Firestore não fornece busca textual nativa; limita-se o conjunto lido e ordena-se
    # localmente. Para uma comunidade maior, este endpoint pode migrar para um índice dedicado.
    for snapshot in _db().collection("communityPriceProducts").limit(1500).stream():
        product = snapshot.to_dict() or {}
        searchable = " ".join([
            _text(product.get("title"), 300),
            _text(product.get("brand"), 150),
            _text(product.get("model"), 150),
            _text(product.get("ean"), 32),
        ]).strip()
        score = _score(q, searchable)
        if score < 0.25:
            continue
        offers = _community_offers(snapshot.reference, limit=20)
        priced = [item for item in offers if isinstance(item.get("price"), (int, float)) and item["price"] > 0]
        matches.append({
            "id": snapshot.id,
            "title": _text(product.get("title"), 300),
            "brand": _text(product.get("brand"), 150),
            "model": _text(product.get("model"), 150),
            "ean": _text(product.get("ean"), 32),
            "image_url": _text(product.get("image_url"), 2048),
            "contributorCount": int(product.get("contributorCount") or 0),
            "stores": product.get("stores") or [],
            "matchScore": score,
            "offers": offers,
            "bestOffer": priced[0] if priced else None,
            "history": _community_history(snapshot.reference, limit=10),
            "updatedAt": product.get("updatedAt", ""),
        })
    matches.sort(key=lambda item: (
        item.get("matchScore", 0) < 0.4,
        -float(item.get("matchScore") or 0),
        item.get("bestOffer") is None,
        float((item.get("bestOffer") or {}).get("price") or 0),
    ))
    return {
        "query": q,
        "products": matches[:6],
        "coverageNote": "Base comunitária: preços e condições registrados pelos usuários do Resolvei. Frete, parcelas e cupons podem mudar e precisam ser confirmados na loja.",
    }

async def _scheduler_loop():
    while True:
        try:
            if os.getenv("SERPAPI_KEY", "").strip():
                now, due = _now(), []
                for snapshot in _db().collection_group("priceMonitorProducts").stream():
                    product = snapshot.to_dict() or {}
                    if product.get("active") is False:
                        continue
                    try:
                        target = datetime.fromisoformat(str(product.get("nextRefreshAt") or "").replace("Z","+00:00"))
                    except ValueError:
                        target = now
                    if target.tzinfo is None:
                        target = target.replace(tzinfo=timezone.utc)
                    if target <= now:
                        due.append((str(product.get("nextRefreshAt") or ""),snapshot.reference,product))
                due.sort(key=lambda entry:entry[0])
                for _, ref, product in due[:SCHEDULE_BATCH]:
                    try:
                        await asyncio.to_thread(_refresh_ref,ref,product)
                        await asyncio.sleep(.5)
                    except Exception:
                        continue
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(SCHEDULE_SECONDS)

def start_price_monitor_scheduler():
    global _refresh_task
    with _refresh_lock:
        if _refresh_task is not None and not _refresh_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        _refresh_task = loop.create_task(_scheduler_loop())
