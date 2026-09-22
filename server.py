from __future__ import annotations

import json
import os
import tempfile
import shutil
import zipfile
import subprocess
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import ipaddress
import socket

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna"
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()

app = FastAPI(title="Resolvei API", version="3.0.0")

ALLOWED_HOSTS = {"resolvei.com.br", "www.resolvei.com.br", "localhost", "127.0.0.1"}


class RecipeRequest(BaseModel):
    url: str
    city: str = "Cuiabá"
    state: str = "MT"
    cep: str = ""


class PartyRequest(BaseModel):
    type: str = "outro"
    age: int = 0
    adults: int = Field(default=20, ge=0)
    kids: int = Field(default=10, ge=0)
    hours: float = Field(default=4, ge=0.5)
    drinkers: int = Field(default=8, ge=0)
    alcohol: str = "beer"
    budgetPerPerson: float = Field(default=0, ge=0)


class ShoppingPriceRequest(BaseModel):
    item: str
    city: str = "Cuiabá"
    state: str = "MT"


class SolarResourceRequest(BaseModel):
    cep: str = ""
    street: str = ""
    neighborhood: str = ""
    city: str = "Cuiabá"
    state: str = "MT"
    address: str = ""
    roofAzimuth: float = 0
    roofTilt: float = 15


class SolarImageRequest(BaseModel):
    imageData: str
    terrainWidth: float = 0
    terrainDepth: float = 0
    roofAzimuth: float = 0
    lat: float = 0
    lon: float = 0


def safe_url(raw: str) -> str:
    value = raw.strip()
    if not value.startswith(("https://", "http://")):
        raise HTTPException(status_code=400, detail="Informe uma URL começando com http:// ou https://.")
    parsed = urlparse(value)
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL inválida.")
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local"):
        raise HTTPException(status_code=400, detail="Por segurança, endereços locais não podem ser consultados.")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        for info in infos:
            addr = info[4][0]
            ip = ipaddress.ip_address(addr)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise HTTPException(status_code=400, detail="O endereço informado resolve para uma rede privada e foi bloqueado por segurança.")
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Não foi possível resolver o domínio informado.")
    return value


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ResolveiBot/2.1; +https://resolvei.com.br/)",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Não foi possível ler a página da receita: {exc}") from exc
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        raise HTTPException(status_code=415, detail="A URL não parece apontar para uma página HTML.")
    return response.text[:5_000_000]


def walk_recipe_json(data: Any) -> list[str]:
    found: list[str] = []
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            typ = item.get("@type")
            types = typ if isinstance(typ, list) else [typ]
            if any(isinstance(t, str) and t.lower() == "recipe" for t in types):
                ing = item.get("recipeIngredient")
                if isinstance(ing, list):
                    found.extend(str(x).strip() for x in ing if str(x).strip())
                elif isinstance(ing, str) and ing.strip():
                    found.append(ing.strip())
            for value in item.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(item, list):
            stack.extend(item)
    return found


def extract_raw_ingredients(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []

    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        found.extend(walk_recipe_json(data))

    for el in soup.find_all(attrs={"itemprop": "recipeIngredient"}):
        txt = el.get("content") or el.get_text(" ", strip=True)
        if txt:
            found.append(txt.strip())

    # Fallback: look for lists/headings with ingredient-like class names.
    if len(found) < 2:
        for el in soup.find_all(class_=re.compile(r"ingred|ingredient|ingredients|ingredientes", re.I)):
            txt = el.get_text(" ", strip=True)
            if 3 <= len(txt) <= 240 and txt.lower() not in {x.lower() for x in found}:
                found.append(txt)

    # Clean, deduplicate and avoid obvious headings.
    clean: list[str] = []
    bad = {"ingredientes", "ingredients", "modo de preparo", "modo de preparo:", "ingrediente"}
    for item in found:
        item = re.sub(r"\s+", " ", item).strip(" •-\t\r\n")
        if not item or item.lower() in bad or len(item) > 250:
            continue
        if item.lower() not in {x.lower() for x in clean}:
            clean.append(item)
    return clean[:30]


def heuristic_category(name: str) -> str:
    text = name.lower()
    groups = {
        "laticínios": ["leite", "manteiga", "queijo", "creme de leite", "iogurte", "requeijão"],
        "carnes": ["carne", "picanha", "fraldinha", "frango", "linguiça", "bacon", "presunto", "peixe"],
        "frutas": ["banana", "maçã", "laranja", "limão", "morango", "abacaxi", "mamão", "uva"],
        "hortaliças": ["tomate", "cebola", "alho", "batata", "cenoura", "pimentão", "mandioca", "cheiro-verde"],
        "secos": ["farinha", "arroz", "feijão", "açúcar", "sal", "amido", "fermento", "aveia", "macarrão"],
        "bebidas": ["água", "suco", "refrigerante", "vinho", "cerveja", "café", "leite"],
        "óleos e molhos": ["óleo", "azeite", "vinagre", "molho", "maionese"],
        "temperos": ["páprica", "pimenta", "orégano", "cominho", "canela", "cravo", "ervas"],
    }
    for cat, words in groups.items():
        if any(word in text for word in words):
            return cat
    return "outros"


def heuristic_parse(raw: str) -> dict[str, Any]:
    m = re.match(r"^\s*(\d+(?:[\.,]\d+)?)\s*([A-Za-zÀ-ÿ\.]+)?\s*(.*)$", raw)
    quantity = 1.0
    unit = "un."
    name = raw.strip()
    if m:
        quantity = float(m.group(1).replace(",", "."))
        unit_raw = (m.group(2) or "").lower().rstrip(".")
        aliases = {"g": "g", "kg": "kg", "ml": "ml", "l": "L", "xícara": "xícara", "xícaras": "xícara", "colher": "colher", "colheres": "colher", "unidade": "un.", "unidades": "un.", "dente": "un.", "dentes": "un."}
        unit = aliases.get(unit_raw, unit or "un.")
        name = m.group(3).strip(" -:") or raw.strip()
    return {"name": name, "quantity": quantity, "unit": unit, "category": heuristic_category(name), "raw": raw, "recipe_price": 0}


def openai_json(prompt: str, schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY não configurada")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=prompt,
            text={"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
        )
        text = getattr(response, "output_text", "") or ""
        return json.loads(text)
    except Exception as exc:
        raise RuntimeError(f"Falha ao consultar a IA: {exc}") from exc


def normalize_ingredients(raw_items: list[str], page_title: str = "") -> list[dict[str, Any]]:
    if not raw_items:
        return []
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "ingredients": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "quantity": {"type": "number"},
                        "unit": {"type": "string"},
                        "category": {"type": "string"},
                        "raw": {"type": "string"},
                        "recipe_price": {"type": "number"},
                    },
                    "required": ["name", "quantity", "unit", "category", "raw", "recipe_price"],
                },
            }
        },
        "required": ["ingredients"],
    }
    prompt = f"""Normalize uma lista de ingredientes de uma receita brasileira. Preserve a quantidade original quando possível. Separe quantidade, unidade e nome do ingrediente; classifique em categorias úteis para compras. Nunca invente preços: recipe_price deve ser 0. Página: {page_title}\n\nIngredientes brutos:\n""" + "\n".join(f"- {x}" for x in raw_items)
    try:
        data = openai_json(prompt, "resolvei_recipe", schema)
        return data.get("ingredients", [])[:30]
    except RuntimeError:
        return [heuristic_parse(x) for x in raw_items]


def price_to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    nums = re.findall(r"\d+[\d\.,]*", text)
    if not nums:
        return None
    candidate = nums[-1].replace(".", "").replace(",", ".")
    try:
        return float(candidate)
    except ValueError:
        return None


def search_price(item: str, city: str, state: str) -> list[dict[str, Any]]:
    if not SERPAPI_KEY:
        return []
    params = {
        "engine": "google_shopping",
        "q": item,
        "location": f"{city}, {state}, Brazil",
        "hl": "pt-BR",
        "gl": "br",
        "api_key": SERPAPI_KEY,
        "num": 6,
    }
    try:
        res = requests.get("https://serpapi.com/search.json", params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
    except requests.RequestException:
        return []
    options: list[dict[str, Any]] = []
    for result in data.get("shopping_results", [])[:6]:
        price = price_to_float(result.get("price"))
        if price is None:
            continue
        options.append({
            "title": result.get("title") or item,
            "price": price,
            "source": result.get("source") or "Loja online",
            "link": result.get("link") or result.get("product_link") or "",
        })
    return options



SOLAR_MONTHS = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]

def geocode_solar(req: SolarResourceRequest) -> dict[str, Any]:
    pieces = [x.strip() for x in [req.street, req.neighborhood, req.city, req.state, req.cep, "Brasil"] if x and x.strip()]
    query = ", ".join(pieces)
    if not query:
        raise HTTPException(status_code=400, detail="Informe pelo menos cidade/UF ou CEP para localizar o ponto.")
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", params={"q": query, "format": "json", "limit": 1, "countrycodes": "br", "addressdetails": 1}, headers={"User-Agent":"Resolvei/3.0 (solar-study)"}, timeout=12)
        r.raise_for_status(); data = r.json()
        if not data:
            raise HTTPException(status_code=404, detail="Não encontrei coordenadas para o endereço informado.")
        x=data[0]
        return {"lat":float(x["lat"]),"lon":float(x["lon"]),"displayName":x.get("display_name",query)}
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Falha no serviço de geocodificação: {exc}") from exc


def fallback_solar(lat: float, roof_azimuth: float = 0, roof_tilt: float = 15) -> dict[str, Any]:
    lat_abs = abs(lat)
    psh = min(6.2, max(3.5, 4.7 + max(0.0, 22-lat_abs)*0.025))
    preferred = 0.0 if lat < 0 else 180.0
    tilt = max(10.0, min(35.0, lat_abs))
    diff = abs(((roof_azimuth-preferred+180)%360)-180)
    orient = max(0.78, 1 - (diff/180)*0.24)
    tilt_factor = max(0.90, 1 - abs(roof_tilt-tilt)/90*0.10)
    annual = psh*365*0.80*orient*tilt_factor
    monthly_avg = annual/12
    seasonal = [1.06,1.05,1.00,0.95,0.88,0.82,0.83,0.88,0.96,1.02,1.05,1.08]
    monthly=[{"name":m,"kwh":monthly_avg*f} for m,f in zip(SOLAR_MONTHS,seasonal)]
    return {"source":"fallback","optimalAzimuth":preferred,"optimalTilt":round(tilt,1),"annualKwhPerKwp":round(annual,1),"specificMonthly":round(monthly_avg,1),"monthly":monthly,"psh":round(psh,2)}


def pvgis_fixed(lat: float, lon: float, angle: float, aspect: float) -> dict[str, Any] | None:
    params={"lat":lat,"lon":lon,"peakpower":1,"loss":14,"pvtechchoice":"crystSi","mountingplace":"building","angle":angle,"aspect":aspect,"pvcalculation":1,"outputformat":"json"}
    try:
        r=requests.get("https://re.jrc.ec.europa.eu/api/v5_3/PVcalc",params=params,timeout=20)
        r.raise_for_status(); return r.json()
    except requests.RequestException:
        return None


def pvgis_optimal(lat: float, lon: float) -> dict[str, Any] | None:
    params={"lat":lat,"lon":lon,"peakpower":1,"loss":14,"pvtechchoice":"crystSi","mountingplace":"building","optimalangles":1,"pvcalculation":1,"outputformat":"json"}
    try:
        r=requests.get("https://re.jrc.ec.europa.eu/api/v5_3/PVcalc",params=params,timeout=20)
        r.raise_for_status(); return r.json()
    except requests.RequestException:
        return None


def parse_pvgis(data: dict[str, Any]) -> dict[str, Any]:
    out=data.get("outputs",{}) or {}
    fixed=out.get("fixed",{}) or {}
    totals=out.get("totals",{}) or {}
    monthly=out.get("monthly",[]) or []
    annual = totals.get("fixed",{}).get("E_y") if isinstance(totals.get("fixed"),dict) else None
    if annual is None:
        annual = fixed.get("E_y")
    if annual is None and monthly:
        annual = sum(float(m.get("E_m",0) or 0) for m in monthly)
    rows=[]
    for i,m in enumerate(monthly[:12]):
        rows.append({"name":SOLAR_MONTHS[i] if i<len(SOLAR_MONTHS) else str(i+1),"kwh":float(m.get("E_m",0) or 0)})
    inp=data.get("inputs",{}) or {}
    fixed_in=inp.get("fixed",{}) if isinstance(inp.get("fixed"),dict) else {}
    slope=fixed_in.get("slope", data.get("meta",{}).get("slope",0))
    aspect=fixed_in.get("azimuth", fixed_in.get("aspect",0))
    return {"annualKwhPerKwp":float(annual or 0),"specificMonthly":float((annual or 0)/12),"monthly":rows,"slope":float(slope or 0),"aspect":float(aspect or 0)}


def pvgis_summary(lat: float, lon: float, roof_azimuth: float, roof_tilt: float) -> dict[str, Any]:
    optimal=pvgis_optimal(lat,lon)
    fixed_aspect=((roof_azimuth-180+180)%360)-180
    fixed=pvgis_fixed(lat,lon,roof_tilt,fixed_aspect)
    if optimal:
        opt=parse_pvgis(optimal)
        pv_aspect=opt.get("aspect",0)
        preferred=((pv_aspect+180)%360)
        return {"source":"PVGIS","optimalAzimuth":preferred,"optimalTilt":opt.get("slope",abs(lat)),"annualKwhPerKwp":opt.get("annualKwhPerKwp",0),"specificMonthly":opt.get("specificMonthly",0),"monthly":opt.get("monthly",[]),"roof":parse_pvgis(fixed) if fixed else None}
    return fallback_solar(lat,roof_azimuth,roof_tilt)

def fallback_party(req: PartyRequest) -> dict[str, Any]:
    labels = {
        "aniversario-infantil": "Aniversário infantil", "aniversario-adulto": "Aniversário adulto", "casamento": "Casamento",
        "firma": "Festa da firma / confraternização", "cha-bebe": "Chá de bebê", "cha-revelacao": "Chá revelação",
        "noivado": "Noivado", "formatura": "Formatura", "bodas": "Bodas", "familiar": "Comemoração familiar",
        "junina": "Festa junina", "happy-hour": "Happy hour", "outro": "Outra comemoração",
    }
    g=req.adults+req.kids
    drinkers=min(g,max(0,req.drinkers))
    if req.alcohol == "beer": alcohol = f"≈ {drinkers*(req.hours/4)*1.5:.1f} L de cerveja"
    elif req.alcohol == "wine": alcohol = f"≈ {max(0,round(drinkers*(req.hours/4)*0.25+0.49))} garrafas de vinho de 750 ml"
    elif req.alcohol == "drinks": alcohol = f"≈ {max(0,round(drinkers*(req.hours/4)*4))} doses de drinks"
    elif req.alcohol == "mixed": alcohol = "Mix de cerveja, vinho e/ou drinks a dimensionar pelo perfil"
    else: alcohol = "Sem álcool"
    if req.type == "junina": foods=["milho/pamonha","canjica ou curau","paçoca e pé-de-moleque","cachorro-quente"]
    elif req.type == "happy-hour": foods=["petiscos","tábua de frios","porções quentes","pão de alho/mini-sanduíches"]
    elif req.type == "casamento": foods=["finger foods","canapés","jantar ou prato principal","doces finos","bolo"]
    elif req.type == "firma": foods=["finger foods","mini-sanduíches","doces/bolo","café e bebidas"]
    elif req.type.startswith("aniversario"):
        foods=["salgados","doces","bolo","mini-sanduíches ou lanches"]
    else: foods=["salgados/finger foods","bolo ou sobremesa","prato principal se houver refeição","frutas ou saladas"]
    sections=[
        {"title":"🍽️ Comidas", "items":[{"name":x,"quantity":"adaptar ao formato","reason":"Combina com o perfil do evento."} for x in foods]},
        {"title":"🥤 Bebidas", "items":[{"name":"Água","quantity":f"≈ {g*0.6:.1f} L","reason":"Base para todos os convidados."},{"name":"Refrigerantes/sucos","quantity":f"≈ {g*0.6:.1f} L","reason":"Complemento sem álcool."},{"name":"Bebida alcoólica","quantity":alcohol,"reason":"Somente para adultos e conforme o perfil informado."}]},
        {"title":"🍽️ Utensílios e infraestrutura", "items":[{"name":"Copos","quantity":f"≈ {g*4} un.","reason":"Margem para reposição."},{"name":"Pratos","quantity":f"≈ {g*2} un.","reason":"Aumente conforme o tipo de serviço."},{"name":"Talheres","quantity":f"≈ {max(g,round(g*1.5))} un.","reason":"Reserve extras."},{"name":"Cadeiras","quantity":f"≈ {g} un.","reason":"Ajustar ao formato e tempo em mesa."},{"name":"Guardanapos","quantity":f"≈ {g*2} un.","reason":"Consumo comum de evento."}]},
    ]
    return {"summary":f"Plano-base para {labels.get(req.type, req.type)} com {g} convidados.","sections":sections,"source":"fallback"}



@app.get("/api/address/cep/{cep}")
def address_by_cep(cep: str) -> dict[str, Any]:
    digits=re.sub(r"\D", "", cep)
    if len(digits)!=8:
        raise HTTPException(status_code=400, detail="CEP deve conter 8 dígitos.")
    try:
        r=requests.get(f"https://viacep.com.br/ws/{digits}/json/",timeout=10); r.raise_for_status(); data=r.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar CEP: {exc}") from exc
    if data.get("erro"):
        raise HTTPException(status_code=404, detail="CEP não encontrado.")
    return data


@app.post("/api/solar/resource")
def solar_resource(req: SolarResourceRequest) -> dict[str, Any]:
    loc=geocode_solar(req)
    summary=pvgis_summary(loc["lat"],loc["lon"],float(req.roofAzimuth or 0),float(req.roofTilt or 15))
    return {**loc,**summary,"lat":loc["lat"],"lon":loc["lon"]}


@app.post("/api/solar/image-analyze")
def solar_image_analyze(req: SolarImageRequest) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="Configure OPENAI_API_KEY para habilitar análise visual por IA.")
    if not req.imageData.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="A imagem precisa ser enviada como data URL.")
    schema={"type":"object","additionalProperties":False,"properties":{
        "summary":{"type":"string"},
        "confidence":{"type":"string"},
        "recommendedAzimuth":{"type":"number"},
        "zones":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{"x":{"type":"number"},"y":{"type":"number"},"width":{"type":"number"},"height":{"type":"number"},"reason":{"type":"string"}},"required":["x","y","width","height","reason"]}}
    },"required":["summary","confidence","recommendedAzimuth","zones"]}
    try:
        from openai import OpenAI
        client=OpenAI(api_key=OPENAI_API_KEY)
        prompt=f"""Analise a imagem de um imóvel/telhado para um estudo preliminar de posicionamento de módulos fotovoltaicos. A imagem pode ser um print de mapa/satélite e pode conter norte, ruas e outras áreas. Não assuma medidas exatas nem diga que um ponto é estruturalmente seguro. Identifique visualmente áreas de telhado que parecem utilizáveis, obstáculos visíveis e uma orientação recomendada de módulos. Retorne coordenadas normalizadas 0 a 1 para até 4 zonas retangulares aproximadas (centro x/y, largura/altura). A recomendação de azimute usa convenção 0=N, 90=L, 180=S, 270=O. Considere a localização informada apenas como contexto: lat={req.lat}, lon={req.lon}."""
        response=client.responses.create(model=OPENAI_MODEL,input=[{"role":"user","content":[{"type":"input_text","text":prompt},{"type":"input_image","image_url":req.imageData,"detail":"high"}]}],text={"format":{"type":"json_schema","name":"resolvei_solar_image","strict":True,"schema":schema}})
        return json.loads(response.output_text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha na análise visual por IA: {exc}") from exc


@app.get("/api/solar/prices")
def solar_prices(city: str="Cuiabá",state: str="MT") -> dict[str, Any]:
    if not SERPAPI_KEY:
        return {"configured":False,"items":[]}
    queries={"panel":"painel solar fotovoltaico 550W","inverter":"inversor solar 5kW on grid","mounting":"estrutura solar telhado por módulo","dcProtection":"string box proteção DC fotovoltaica","acProtection":"quadro proteção AC fotovoltaico"}
    items=[]
    for key,q in queries.items():
        opts=search_price(q,city,state.upper())
        if opts:
            items.append({"key":key,"query":q,"best":opts[0],"options":opts})
    return {"configured":True,"city":city,"state":state.upper(),"items":items}


@app.post("/api/files/convert")
async def convert_file(file: UploadFile = File(...), output_format: str = Form(...)):
    allowed = {
        "mp4": {"avi","webm","mov"}, "avi": {"mp4","webm"}, "mov": {"mp4","avi","webm"},
        "mkv": {"mp4","webm"}, "webm": {"mp4","avi"},
        "jpg": {"png","webp","pdf"}, "jpeg": {"png","webp","pdf"},
        "png": {"jpg","webp","pdf"}, "webp": {"jpg","png","pdf"},
        "bmp": {"jpg","png","webp"}, "pdf": {"jpg","png","dxf","dwg"}
    }
    filename = Path(file.filename or "arquivo").name
    src_ext = Path(filename).suffix.lower().lstrip(".")
    out_ext = output_format.lower().lstrip(".")
    if src_ext not in allowed or out_ext not in allowed[src_ext]:
        raise HTTPException(status_code=400, detail="Conversão não suportada.")
    max_bytes = 200 * 1024 * 1024
    with tempfile.TemporaryDirectory(prefix="resolvei-convert-") as td:
        src = Path(td) / filename
        with src.open("wb") as f:
            total = 0
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk: break
                total += len(chunk)
                if total > max_bytes: raise HTTPException(status_code=413, detail="O arquivo excede o limite de 200 MB.")
                f.write(chunk)
        out = Path(td) / f"convertido.{out_ext}"
        try:
            if src_ext in {"jpg","jpeg","png","webp","bmp"}:
                from PIL import Image
                img = Image.open(src)
                if out_ext == "pdf":
                    img.convert("RGB").save(out, "PDF")
                else:
                    if out_ext == "jpg": out = out.with_suffix(".jpg"); img = img.convert("RGB")
                    img.save(out, format=out_ext.upper())
            elif src_ext == "pdf":
                import fitz
                doc = fitz.open(src)
                if len(doc) == 0: raise ValueError("PDF vazio.")
                if out_ext in {"jpg","png"}:
                    if len(doc) == 1:
                        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2,2), alpha=False)
                        pix.save(str(out))
                    else:
                        out = out.with_suffix(".zip")
                        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
                            for i, page in enumerate(doc):
                                pix = page.get_pixmap(matrix=fitz.Matrix(2,2), alpha=False)
                                img = Path(td) / f"pagina-{i+1}.{out_ext}"
                                pix.save(str(img))
                                z.write(img, img.name)
                elif out_ext in {"dxf","dwg"}:
                    import ezdxf
                    cad = ezdxf.new("R2018")
                    msp = cad.modelspace()
                    for page_no, page in enumerate(doc):
                        layer=f"PDF_PAGE_{page_no+1}"
                        for item in page.get_drawings():
                            op=item[0]
                            if op=="l":
                                p1,p2=item[1],item[2]; msp.add_line((p1.x,-p1.y),(p2.x,-p2.y),dxfattribs={"layer":layer})
                            elif op=="re":
                                r=item[1]; pts=[(r.x0,-r.y0),(r.x1,-r.y0),(r.x1,-r.y1),(r.x0,-r.y1)]
                                msp.add_lwpolyline(pts,close=True,dxfattribs={"layer":layer})
                            elif op=="qu":
                                q=item[1]; pts=[(q.ul.x,-q.ul.y),(q.ur.x,-q.ur.y),(q.lr.x,-q.lr.y),(q.ll.x,-q.ll.y)]
                                msp.add_lwpolyline(pts,close=True,dxfattribs={"layer":layer})
                        for block in page.get_text("dict").get("blocks",[]):
                            for line in block.get("lines",[]):
                                for span in line.get("spans",[]):
                                    txt=span.get("text","").strip()
                                    if txt:
                                        x,y=span["origin"]; msp.add_text(txt,dxfattribs={"height":max(float(span.get("size",8)),1),"layer":f"TEXT_PAGE_{page_no+1}"}).set_placement((x,-y))
                    dxf_path=out.with_suffix(".dxf")
                    cad.saveas(dxf_path)
                    if out_ext=="dwg":
                        oda=shutil.which("ODAFileConverter") or shutil.which("odafileconverter")
                        if not oda:
                            raise RuntimeError("DWG exige ODA File Converter no servidor. Use DXF ou instale o conversor ODA.")
                        target=Path(td)/"dwgout"; target.mkdir()
                        p=subprocess.run([oda,str(td),str(target),"ACAD2018","DWG","0","1",str(dxf_path)],capture_output=True,text=True,timeout=300)
                        generated=list(target.rglob("*.dwg"))
                        if p.returncode!=0 or not generated: raise RuntimeError("Falha ao gerar DWG.")
                        shutil.copy2(generated[0],out)
                doc.close()
            else:
                ffmpeg = shutil.which("ffmpeg")
                if not ffmpeg: raise RuntimeError("FFmpeg não está instalado no servidor.")
                cmd = [ffmpeg, "-y", "-i", str(src)]
                if out_ext == "avi": cmd += ["-c:v","mpeg4","-c:a","mp3"]
                elif out_ext == "webm": cmd += ["-c:v","libvpx-vp9","-c:a","libopus"]
                elif out_ext == "mov": cmd += ["-c:v","libx264","-c:a","aac"]
                else: cmd += ["-c:v","libx264","-c:a","aac"]
                cmd += [str(out)]
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                if p.returncode != 0: raise RuntimeError("FFmpeg não conseguiu converter o vídeo.")
            media = {
                "jpg":"image/jpeg","png":"image/png","webp":"image/webp","pdf":"application/pdf","dxf":"application/dxf","dwg":"application/acad",
                "mp4":"video/mp4","avi":"video/x-msvideo","mov":"video/quicktime","webm":"video/webm"
            }.get(out_ext, "application/octet-stream")
            return Response(content=out.read_bytes(), media_type=media,
                            headers={"Content-Disposition": f'attachment; filename="resolvei-convertido.{("zip" if out_ext in {"jpg","png"} and src_ext=="pdf" and out.suffix==".zip" else out_ext)}"'});
        except HTTPException:
            raise
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="A conversão demorou demais e foi interrompida.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e) or "Falha na conversão.")

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "ai_configured": bool(OPENAI_API_KEY), "prices_configured": bool(SERPAPI_KEY), "model": OPENAI_MODEL}


@app.post("/api/recipe/analyze")
def analyze_recipe(req: RecipeRequest) -> dict[str, Any]:
    url = safe_url(req.url)
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "Receita"
    raw = extract_raw_ingredients(html)
    if not raw:
        raise HTTPException(status_code=422, detail="Não encontrei ingredientes estruturados nessa página. Tente outra URL ou insira os ingredientes manualmente.")
    ingredients = normalize_ingredients(raw, title)
    price_items: list[dict[str, Any]] = []
    basket_total = 0.0
    if SERPAPI_KEY:
        for ing in ingredients[:12]:
            options = search_price(ing.get("name", ""), req.city or "Cuiabá", (req.state or "MT").upper())
            best = options[0] if options else None
            price_items.append({"name": ing.get("name", ""), "price": best.get("price") if best else None, "source": best.get("source") if best else "Sem cotação", "title": best.get("title") if best else "", "options": options})
            if best:
                basket_total += float(best["price"])
        price_note = f"Cotação de referência para até {min(12, len(ingredients))} ingredientes, orientada por {req.city}, {req.state}. A soma representa produtos encontrados, não o custo proporcional efetivamente consumido na receita."
    else:
        price_note = "Os ingredientes foram organizados, mas a cotação regional ao vivo está desativada. Configure SERPAPI_KEY no servidor para consultar preços."
    return {
        "title": title,
        "ingredients": ingredients,
        "price_summary": {"total": basket_total, "items": price_items} if SERPAPI_KEY else None,
        "price_note": price_note,
        "city": req.city,
        "state": req.state,
    }


@app.post("/api/party/suggest")
def party_suggest(req: PartyRequest) -> dict[str, Any]:
    req.drinkers = min(req.drinkers, req.adults + req.kids)
    schema = {
        "type":"object","additionalProperties":False,
        "properties":{
            "summary":{"type":"string"},
            "sections":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{
                "title":{"type":"string"},
                "items":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{"name":{"type":"string"},"quantity":{"type":"string"},"reason":{"type":"string"}},"required":["name","quantity","reason"]}}
            },"required":["title","items"]}}
        },"required":["summary","sections"]
    }
    labels={"aniversario-infantil":"aniversário infantil","aniversario-adulto":"aniversário adulto","casamento":"casamento","firma":"festa da firma","cha-bebe":"chá de bebê","cha-revelacao":"chá revelação","noivado":"noivado","formatura":"formatura","bodas":"bodas","familiar":"comemoração familiar","junina":"festa junina","happy-hour":"happy hour","outro":"outra comemoração"}
    prompt=f"""Você é um planejador de festas para o Brasil. Monte um plano prático para: tipo={labels.get(req.type,req.type)}, idade do aniversariante={req.age}, adultos={req.adults}, crianças={req.kids}, duração={req.hours} horas, bebedores de álcool={req.drinkers}, bebida={req.alcohol}, orçamento por pessoa={req.budgetPerPerson}. Sugira comidas, bebidas alcoólicas e não alcoólicas, drinks quando apropriado, gelo, utensílios, copos, pratos, talheres, guardanapos, cadeiras e infraestrutura. Adapte o foco ao tipo e, em aniversário, considere a idade. Não invente preços. Dê quantidades em linguagem prática e explique brevemente o motivo de cada item. Para menores, não sugira consumo de álcool."""
    if OPENAI_API_KEY:
        try:
            data=openai_json(prompt,"resolvei_party",schema)
            data["source"]="openai"
            return data
        except RuntimeError:
            pass
    result=fallback_party(req)
    result["ai_note"]="A IA não está configurada/indisponível; o Resolvei usou o plano-base inteligente." if not OPENAI_API_KEY else "A IA ficou indisponível; o Resolvei usou o plano-base inteligente."
    return result


@app.post("/api/prices/search")
def prices_search(req: ShoppingPriceRequest) -> dict[str, Any]:
    item=req.item.strip()
    if not item:
        raise HTTPException(status_code=400, detail="Informe um item.")
    options=search_price(item,req.city,req.state.upper())
    return {"item":item,"city":req.city,"state":req.state.upper(),"options":options}


@app.get("/{path:path}")
def static_files(path: str = ""):
    # Serve normal files; for browser routes return index.html.
    target=(BASE_DIR/path).resolve()
    try:
        target.relative_to(BASE_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    if path and target.is_file():
        return FileResponse(target)
    index=BASE_DIR/"index.html"
    return FileResponse(index)
