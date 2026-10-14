"""API do Monitor de Preços, isolada das demais ferramentas."""
from __future__ import annotations
import asyncio, ipaddress, os, re, threading, uuid
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

def _uid(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Entre na sua conta do Resolvei para usar o Monitor de Preços.")
    try:
        import firebase_admin
        from firebase_admin import auth
        if not firebase_admin._apps:
            raise HTTPException(503, "Firebase Admin não está configurado no servidor.")
        uid = str(auth.verify_id_token(authorization[7:].strip()).get("uid") or "")
        if not uid:
            raise HTTPException(401, "Sessão Firebase inválida.")
        return uid
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(401, "Sessão inválida ou expirada. Entre novamente no Resolvei.") from exc

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

def _shopping(query):
    key = os.getenv("SERPAPI_KEY", "").strip()
    if not key:
        raise HTTPException(503, "A comparação entre lojas requer SERPAPI_KEY nas variáveis de ambiente do Render. O histórico e os preços registrados manualmente continuam disponíveis.")
    query = _text(query, 180)
    if len(query) < 2:
        raise HTTPException(422, "Informe o nome, marca ou modelo do produto.")
    try:
        response = requests.get("https://serpapi.com/search.json",
            params={"engine":"google_shopping","q":query,"gl":"br","hl":"pt-br","api_key":key},
            timeout=(5, 20), headers={"User-Agent":"ResolveiMonitorPrecos/1.0"})
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
        results.append({
            "title":_text(row.get("title"), 300), "price":amount,
            "source":_text(row.get("source"), 100) or (urlparse(link).hostname or "Loja"),
            "url":link[:2048], "image_url":_text(row.get("thumbnail"), 2048),
            "delivery":_text(row.get("delivery"), 180), "rating":row.get("rating"), "reviews":row.get("reviews")
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
