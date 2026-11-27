"""Store-specific product discovery for Radar de Ofertas.

Searches each configured marketplace directly. It deliberately never returns
Google Shopping product pages as purchase destinations.
"""
from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import quote, quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


TIMEOUT = (6, 22)
PAGE_LIMIT = 48

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.7,en;q=0.6",
}


def _plain(value: object, limit: int = 500) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return re.sub(r"\s+", " ", str(value)).strip()[:limit]


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:140]


def _brl(value: object) -> float | None:
    """Parse Brazilian currency/price text without treating thousands as decimals."""
    if isinstance(value, (int, float)):
        number = float(value)
        return round(number, 2) if 0 < number < 100_000_000 else None
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = re.sub(r"(?i)R\s*\$", "", raw)
    raw = re.sub(r"[^0-9,.\-]", "", raw)
    if not raw:
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "." in raw:
        tail = raw.rsplit(".", 1)[-1]
        if len(tail) != 2:
            raw = raw.replace(".", "")
    try:
        number = float(raw)
        return round(number, 2) if 0 < number < 100_000_000 else None
    except (TypeError, ValueError):
        return None


def _amount_node(node) -> float | None:
    if node is None:
        return None
    fraction = node.select_one(".andes-money-amount__fraction")
    if fraction:
        cents = node.select_one(".andes-money-amount__cents")
        raw = fraction.get_text("", strip=True)
        if cents:
            raw += "," + cents.get_text("", strip=True).zfill(2)
        return _brl(raw)
    return _brl(node.get("aria-label") or node.get_text(" ", strip=True))


def _coupon_details(text: str) -> tuple[str, str, float | None]:
    text = _plain(text, 1800)
    if not re.search(r"\bcupom\b|\bcoupon\b", text, re.I):
        return "", "", None

    code = ""
    patterns = (
        r"(?:use|aplique|digite)\s+(?:o\s+)?(?:cupom|c[oó]digo)\s*[:\-]?\s*([A-Z0-9][A-Z0-9_-]{3,24})",
        r"(?:cupom|c[oó]digo)\s*[:\-]\s*([A-Z0-9][A-Z0-9_-]{3,24})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            candidate = match.group(1).upper()
            if candidate not in {"DESCONTO", "PROMOCAO", "PROMOCIONAL", "OFF"}:
                code = candidate
                break

    coupon_price = None
    price_match = re.search(
        r"(R\$\s*[\d.]+(?:,\d{2})?)\s*(?:com|ap[oó]s)\s+(?:o\s+)?cupom",
        text,
        re.I,
    )
    if price_match:
        coupon_price = _brl(price_match.group(1))

    fragments = re.findall(r"[^|•\n]{0,70}\bcupom\b[^|•\n]{0,100}", text, re.I)
    info = _plain(fragments[0], 180) if fragments else "Cupom mencionado na página da loja; confira as condições."
    if code:
        info = "Use o cupom " + code
    return code, info, coupon_price


def _installment_text(text: str) -> str:
    match = re.search(
        r"\b\d{1,2}\s*x\s*(?:de\s*)?(?:R\$\s*)?[\d.]+(?:,\d{2})?(?:\s*sem\s+juros)?",
        _plain(text, 1800),
        re.I,
    )
    return _plain(match.group(0), 100) if match else ""


def _discount_text(text: str) -> float | None:
    match = re.search(r"\b(\d{1,2}(?:[,.]\d{1,2})?)\s*%\s*(?:OFF|de desconto)", text or "", re.I)
    if not match:
        return None
    try:
        return round(float(match.group(1).replace(",", ".")), 2)
    except ValueError:
        return None


def _free_shipping(text: str) -> bool:
    return bool(re.search(r"frete\s+gr[aá]tis|envio\s+gr[aá]tis|entrega\s+gr[aá]tis", text or "", re.I))


def _valid_offer_url(store: str, url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower().removeprefix("www.")
    permitted = {
        "mercado_livre": ("mercadolivre.com.br", "mercadolibre.com"),
        "amazon": ("amazon.com.br",),
        "shopee": ("shopee.com.br",),
        "magalu": ("magazineluiza.com.br",),
    }.get(store, ())
    return any(host == domain or host.endswith("." + domain) for domain in permitted)


def _direct_get(url: str, *, params: dict | None = None, referer: str = "") -> requests.Response:
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    try:
        response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        raise RuntimeError("A loja não respondeu à pesquisa agora. Tente novamente mais tarde.") from exc
    if response.status_code in {403, 429}:
        raise RuntimeError(
            "A própria loja bloqueou temporariamente a consulta automatizada "
            f"(HTTP {response.status_code}). O Radar não substituiu essa busca por resultados do Google."
        )
    if response.status_code >= 400:
        raise RuntimeError(f"A loja retornou HTTP {response.status_code} durante a pesquisa.")
    return response


def _mercado_livre_search(keyword: str) -> list[dict]:
    """Read product cards from Mercado Livre's own search-result pages."""
    slug = _slug(keyword)
    if not slug:
        return []
    results: list[dict] = []
    seen: set[str] = set()

    # A list page contains up to roughly 48 cards. Continue once to improve coverage.
    for offset in (0, 49):
        path = slug if offset == 0 else f"{slug}_Desde_{offset}_NoIndex_True"
        search_url = "https://lista.mercadolivre.com.br/" + path
        response = _direct_get(search_url, referer="https://www.mercadolivre.com.br/")
        soup = BeautifulSoup(response.text, "html.parser")
        links = soup.select("a.poly-component__title")
        if not links and offset == 0:
            # Older/alternate listing markup. Keep the same strict host validation.
            links = soup.select("a.ui-search-link[href], a.ui-search-item__group__element[href]")
        if not links:
            body_text = _plain(soup.get_text(" ", strip=True), 1200).lower()
            if any(term in body_text for term in ("não encontramos", "nao encontramos", "nenhum resultado")):
                break
            if offset == 0:
                raise RuntimeError(
                    "A página do Mercado Livre abriu, mas o Radar não reconheceu os cards de produtos. "
                    "A estrutura da busca pode ter mudado."
                )
            break

        for title_link in links:
            href = urljoin(response.url, str(title_link.get("href") or "").strip())
            if not _valid_offer_url("mercado_livre", href):
                continue
            title = _plain(title_link.get("title") or title_link.get_text(" ", strip=True), 300)
            if len(title) < 3:
                continue

            card = title_link
            for parent in title_link.parents:
                classes = parent.get("class") or []
                if any("poly-card" in str(cls) or "ui-search-result" in str(cls) for cls in classes):
                    card = parent
                    break
            card_text = _plain(card.get_text(" ", strip=True), 1800)
            if re.search(r"\b(usado|usada|seminovo|seminova|recondicionado|recondicionada|refurbished|renewed)\b", title + " " + card_text, re.I):
                continue

            current_node = card.select_one(".poly-price__current .andes-money-amount")
            if not current_node:
                price_nodes = card.select("span.andes-money-amount")
                current_node = next(
                    (node for node in price_nodes if "previous" not in " ".join(node.get("class") or [])),
                    None,
                )
            price = _amount_node(current_node)
            if price is None:
                # Use the product-card price text, never the installment amount.
                price_match = re.search(r"R\$\s*[\d.]+(?:,\d{2})?", card_text)
                price = _brl(price_match.group(0)) if price_match else None
            if price is None:
                continue

            old_node = card.select_one(".poly-price__previous .andes-money-amount, .andes-money-amount--previous")
            original_price = _amount_node(old_node)
            if original_price is None:
                old_match = re.search(r"(?:De|Antes)\s+R\$\s*[\d.]+(?:,\d{2})?", card_text, re.I)
                original_price = _brl(old_match.group(0)) if old_match else None

            coupon_code, coupon_info, coupon_price = _coupon_details(card_text)
            discount = _discount_text(card_text)
            if discount is None and original_price and original_price > price:
                discount = round((original_price - price) / original_price * 100, 2)

            image_node = card.select_one("img.poly-component__picture, img.ui-search-result-image__element, img")
            image = ""
            if image_node:
                image = _plain(
                    image_node.get("src") or image_node.get("data-src") or image_node.get("data-original"),
                    2048,
                )
            seller_node = card.select_one(".poly-component__seller, .ui-search-official-store-label, .poly-component__seller-name")
            seller = _plain(seller_node.get_text(" ", strip=True), 100) if seller_node else ""
            rating_match = re.search(r"\b([0-5][,.]\d)\b", card_text)
            rating = None
            if rating_match:
                try:
                    rating = float(rating_match.group(1).replace(",", "."))
                except ValueError:
                    rating = None

            key = href.split("#", 1)[0].split("?", 1)[0].rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "title": title,
                "price": price,
                "original_price": original_price,
                "coupon_price": coupon_price,
                "coupon_code": coupon_code,
                "coupon_info": coupon_info,
                "discount_percent": discount,
                "source": "Mercado Livre",
                "url": href,
                "image_url": image,
                "delivery": "",
                "free_shipping": _free_shipping(card_text),
                "shipping_text": "Frete grátis" if _free_shipping(card_text) else "",
                "installment_text": _installment_text(card_text),
                "rating": rating,
                "reviews": None,
                "seller": seller,
                "second_hand_condition": "",
                "source_search_url": response.url,
            })
        if offset and len(results) >= PAGE_LIMIT * 2:
            break
    return results


def _amazon_search(keyword: str) -> list[dict]:
    results: list[dict] = []
    url = "https://www.amazon.com.br/s"
    response = _direct_get(url, params={"k": keyword}, referer="https://www.amazon.com.br/")
    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.select('div[data-component-type="s-search-result"][data-asin]')
    for card in cards[:PAGE_LIMIT]:
        asin = _plain(card.get("data-asin"), 32)
        if not asin:
            continue
        title_node = card.select_one("h2 a span")
        title = _plain(title_node.get_text(" ", strip=True) if title_node else "", 300)
        if not title:
            continue
        price_node = card.select_one(".a-price:not(.a-text-price) .a-offscreen")
        price = _brl(price_node.get_text(" ", strip=True) if price_node else "")
        if price is None:
            continue
        old_node = card.select_one(".a-price.a-text-price .a-offscreen")
        original = _brl(old_node.get_text(" ", strip=True) if old_node else "")
        text = _plain(card.get_text(" ", strip=True), 1800)
        coupon_code, coupon_info, coupon_price = _coupon_details(text)
        discount = _discount_text(text)
        if discount is None and original and original > price:
            discount = round((original - price) / original * 100, 2)
        image_node = card.select_one("img.s-image")
        image = _plain(image_node.get("src") if image_node else "", 2048)
        seller_node = card.select_one(".a-row .a-size-base.a-color-secondary")
        results.append({
            "title": title,
            "price": price,
            "original_price": original,
            "coupon_price": coupon_price,
            "coupon_code": coupon_code,
            "coupon_info": coupon_info,
            "discount_percent": discount,
            "source": "Amazon",
            "url": f"https://www.amazon.com.br/dp/{asin}",
            "image_url": image,
            "delivery": "",
            "free_shipping": _free_shipping(text),
            "shipping_text": "Frete grátis" if _free_shipping(text) else "",
            "installment_text": _installment_text(text),
            "rating": None,
            "reviews": None,
            "seller": _plain(seller_node.get_text(" ", strip=True) if seller_node else "", 100),
            "second_hand_condition": "",
            "source_search_url": response.url,
        })
    if not cards and not any(x in response.text.lower() for x in ("s-result-item", "não encontramos", "no results")):
        raise RuntimeError("A busca da Amazon carregou, mas os cards de produtos não foram reconhecidos.")
    return results


def _shopee_search(keyword: str) -> list[dict]:
    search_url = "https://shopee.com.br/search?keyword=" + quote_plus(keyword)
    endpoint = "https://shopee.com.br/api/v4/search/search_items"
    response = _direct_get(
        endpoint,
        params={
            "by": "relevancy",
            "keyword": keyword,
            "limit": PAGE_LIMIT,
            "newest": 0,
            "order": "desc",
            "page_type": "search",
            "scenario": "PAGE_GLOBAL_SEARCH",
            "version": 2,
        },
        referer=search_url,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("A busca direta da Shopee retornou uma resposta inválida.") from exc
    rows = payload.get("items") or (payload.get("data") or {}).get("items") or []
    results = []
    for row in rows:
        item = row.get("item_basic") or row
        item_id = item.get("itemid")
        shop_id = item.get("shopid")
        title = _plain(item.get("name"), 300)
        try:
            price = _brl(float(item.get("price_min") or item.get("price") or 0) / 100000)
            original = _brl(float(item.get("price_before_discount") or 0) / 100000)
        except (TypeError, ValueError):
            price, original = None, None
        if not item_id or not shop_id or not title or price is None:
            continue
        coupon_code, coupon_info, coupon_price = _coupon_details(_plain(item, 1800))
        discount = _discount_text(str(item.get("discount") or ""))
        if discount is None:
            try:
                discount = float(str(item.get("discount") or "").replace("%", "").replace(",", "."))
            except (TypeError, ValueError):
                discount = None
        if discount is None and original and original > price:
            discount = round((original - price) / original * 100, 2)
        image_key = _plain(item.get("image"), 200)
        image = "https://down-br.img.susercontent.com/file/" + image_key if image_key else ""
        name_slug = _slug(title)[:90]
        product_url = f"https://shopee.com.br/{name_slug}-i.{shop_id}.{item_id}"
        item_rating = item.get("item_rating") or {}
        rating = item_rating.get("rating_star")
        rating_count = item_rating.get("rating_count") or []
        results.append({
            "title": title,
            "price": price,
            "original_price": original,
            "coupon_price": coupon_price,
            "coupon_code": coupon_code,
            "coupon_info": coupon_info,
            "discount_percent": discount,
            "source": "Shopee",
            "url": product_url,
            "image_url": image,
            "delivery": "",
            "free_shipping": bool(item.get("show_free_shipping")),
            "shipping_text": "Frete grátis" if item.get("show_free_shipping") else "",
            "installment_text": "",
            "rating": rating,
            "reviews": rating_count[0] if isinstance(rating_count, list) and rating_count else None,
            "seller": _plain(item.get("shop_name"), 100),
            "second_hand_condition": "",
            "source_search_url": search_url,
        })
    if not rows and payload.get("error"):
        raise RuntimeError("A Shopee recusou a pesquisa direta: " + _plain(payload.get("error"), 160))
    return results


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _magalu_search(keyword: str) -> list[dict]:
    slug = _slug(keyword)
    url = "https://www.magazineluiza.com.br/busca/" + slug + "/"
    response = _direct_get(url, referer="https://www.magazineluiza.com.br/")
    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict] = []
    seen: set[str] = set()

    # Prefer structured product records when Magalu includes them in its SSR HTML.
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for node in _walk_json(payload):
            kind = node.get("@type", "")
            kinds = [str(x).lower() for x in kind] if isinstance(kind, list) else [str(kind).lower()]
            if not any(x == "product" for x in kinds):
                continue
            name = _plain(node.get("name"), 300)
            offers = node.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = _brl(offers.get("price") or offers.get("lowPrice"))
            product_url = urljoin(response.url, _plain(node.get("url"), 2048))
            if not name or price is None or not _valid_offer_url("magalu", product_url):
                continue
            image = node.get("image")
            if isinstance(image, list):
                image = image[0] if image else ""
            original = _brl(offers.get("highPrice") or offers.get("listPrice"))
            results.append({
                "title": name, "price": price, "original_price": original,
                "coupon_price": None, "coupon_code": "", "coupon_info": "",
                "discount_percent": round((original - price) / original * 100, 2) if original and original > price else None,
                "source": "Magazine Luiza", "url": product_url,
                "image_url": _plain(image, 2048), "delivery": "",
                "free_shipping": None, "shipping_text": "",
                "installment_text": "", "rating": None, "reviews": None,
                "seller": "", "second_hand_condition": "", "source_search_url": response.url,
            })

    # Search cards are used when the result page does not expose Product JSON-LD.
    if not results:
        links = soup.select('a[href*="/p/"]')
        for link in links:
            product_url = urljoin(response.url, _plain(link.get("href"), 2048))
            if not _valid_offer_url("magalu", product_url):
                continue
            card = link
            for parent in link.parents:
                text = _plain(parent.get_text(" ", strip=True), 1500)
                if len(text) > 30 and re.search(r"R\$\s*[\d.]+(?:,\d{2})?", text):
                    card = parent
                    break
            card_text = _plain(card.get_text(" ", strip=True), 1800)
            title_node = card.select_one("h2, h3, [data-testid*='title']")
            title = _plain(title_node.get_text(" ", strip=True) if title_node else link.get("title") or link.get_text(" ", strip=True), 300)
            price_match = re.search(r"R\$\s*[\d.]+(?:,\d{2})?", card_text)
            price = _brl(price_match.group(0)) if price_match else None
            if not title or price is None:
                continue
            coupon_code, coupon_info, coupon_price = _coupon_details(card_text)
            original_match = re.search(r"(?:de|por)\s+R\$\s*[\d.]+(?:,\d{2})?", card_text, re.I)
            original = _brl(original_match.group(0)) if original_match else None
            image_node = card.select_one("img")
            image = _plain((image_node.get("src") or image_node.get("data-src")) if image_node else "", 2048)
            key = product_url.split("?", 1)[0]
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "title": title, "price": price, "original_price": original,
                "coupon_price": coupon_price, "coupon_code": coupon_code, "coupon_info": coupon_info,
                "discount_percent": _discount_text(card_text),
                "source": "Magazine Luiza", "url": product_url,
                "image_url": image, "delivery": "",
                "free_shipping": _free_shipping(card_text),
                "shipping_text": "Frete grátis" if _free_shipping(card_text) else "",
                "installment_text": _installment_text(card_text),
                "rating": None, "reviews": None, "seller": "", "second_hand_condition": "",
                "source_search_url": response.url,
            })

    if not results and not any(x in response.text.lower() for x in ("nenhum produto", "não encontramos", "nao encontramos")):
        raise RuntimeError("A busca da Magazine Luiza carregou, mas os cards de produtos não foram reconhecidos.")
    return results[:PAGE_LIMIT]


def search_store_offers(store: str, keyword: str) -> list[dict]:
    """Search only the marketplace selected by the user's monitor."""
    key = str(store or "").strip().lower()
    query = _plain(keyword, 160)
    if len(query) < 2:
        return []
    adapters = {
        "mercado_livre": _mercado_livre_search,
        "amazon": _amazon_search,
        "shopee": _shopee_search,
        "magalu": _magalu_search,
    }
    adapter = adapters.get(key)
    if not adapter:
        raise RuntimeError("Não existe um conector de busca direta para esta loja.")
    offers = adapter(query)
    accepted = []
    seen = set()
    for offer in offers:
        url = str(offer.get("url") or "").strip()
        if not _valid_offer_url(key, url):
            continue
        canonical = url.split("#", 1)[0].split("?", 1)[0].rstrip("/")
        if canonical in seen:
            continue
        seen.add(canonical)
        offer["url"] = url
        accepted.append(offer)
    return accepted
