"use strict";

const API_BASE = "https://resolvei-utilidades.onrender.com/api/price-monitor";
const FIREBASE_API_KEY = "AIzaSyBox8tior0HX5T6ox2ZNNo9fbzUkHxw8go";
const SESSION_KEY = "resolveiPriceMonitorSession";
const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

let currentProduct = null;
let activeUser = null;
let combinedOffers = [];
let comparisonBusy = false;
let communityData = null;

function parsePrice(value) {
  if (typeof value === "number") return value > 0 ? Math.round(value * 100) / 100 : null;
  let text = String(value == null ? "" : value).replace(/[^\d,.\-]/g, "").trim();
  if (!text) return null;
  if (text.indexOf(",") >= 0 && text.indexOf(".") >= 0) {
    text = text.lastIndexOf(",") > text.lastIndexOf(".")
      ? text.replace(/\./g, "").replace(",", ".")
      : text.replace(/,/g, "");
  } else if (text.indexOf(",") >= 0) {
    text = text.replace(/\./g, "").replace(",", ".");
  } else if ((text.match(/\./g) || []).length > 1) {
    const parts = text.split(".");
    text = parts.slice(0, -1).join("") + "." + parts[parts.length - 1];
  }
  const result = Number(text);
  return Number.isFinite(result) && result > 0 ? Math.round(result * 100) / 100 : null;
}

function money(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? brl.format(number) : "Preço não informado";
}

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
    return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch];
  });
}

function setState(message, type) {
  const box = document.getElementById("state");
  if (!box) return;
  box.textContent = message;
  box.className = "state" + (type ? " " + type : "");
}

function showLogin(message, isError) {
  document.getElementById("login-panel").classList.remove("hidden");
  document.getElementById("app-panel").classList.add("hidden");
  document.getElementById("logout").classList.add("hidden");
  if (message) setState(message, isError ? "error" : "");
}

function showApp() {
  document.getElementById("login-panel").classList.add("hidden");
  document.getElementById("app-panel").classList.remove("hidden");
  document.getElementById("logout").classList.remove("hidden");
  document.getElementById("account-line").textContent = activeUser ? "Conectado como " + activeUser : "Sessão do Resolvei conectada";
}

function storageGet(key) {
  return new Promise(function (resolve) {
    chrome.storage.local.get([key], function (data) {
      resolve(data && data[key] ? data[key] : null);
    });
  });
}

function storageSet(value) {
  return new Promise(function (resolve, reject) {
    chrome.storage.local.set({ [SESSION_KEY]: value }, function () {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve();
    });
  });
}

function storageClear() {
  return new Promise(function (resolve) {
    chrome.storage.local.remove([SESSION_KEY], resolve);
  });
}

async function ensureSession() {
  const session = await storageGet(SESSION_KEY);
  if (!session || !session.apiToken || !Number.isFinite(Number(session.expiresAt)) || Number(session.expiresAt) <= Date.now()) {
    await storageClear();
    activeUser = null;
    throw new Error("Sua sessão do Resolvei expirou. Entre novamente para continuar.");
  }
  activeUser = session.email || "";
  return session;
}

async function api(path, options) {
  const session = await ensureSession();
  const opts = options || {};
  const headers = Object.assign({}, opts.headers || {}, {
    "Authorization": "Bearer " + session.apiToken
  });
  if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(API_BASE + path, Object.assign({}, opts, { headers }));
  } catch (_) {
    throw new Error("Não foi possível conectar ao Resolvei. Verifique sua conexão e tente novamente.");
  }
  const payload = await response.json().catch(function () { return {}; });
  if (!response.ok) {
    const detail = payload.detail || payload.message || "Falha ao consultar a base de preços.";
    if (response.status === 401) {
      await storageClear();
      activeUser = null;
      throw new Error("Sua sessão expirou. Entre novamente no Resolvei.");
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

async function createApiSession(firebaseIdToken, email) {
  const response = await fetch(API_BASE + "/extension/session", {
    method: "POST",
    headers: {
      "Authorization": "Bearer " + firebaseIdToken
    }
  });
  const data = await response.json().catch(function () { return {}; });
  if (!response.ok || !data.accessToken) {
    throw new Error(data.detail || "O login foi validado, mas não foi possível iniciar a sessão da extensão.");
  }
  const session = {
    apiToken: data.accessToken,
    email: String(email || ""),
    expiresAt: Date.parse(data.expiresAt || "") || (Date.now() + 30 * 24 * 60 * 60 * 1000)
  };
  await storageSet(session);
  activeUser = session.email;
  return session;
}

function loginWithEmail(email, password) {
  return fetch("https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=" + encodeURIComponent(FIREBASE_API_KEY), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email, password: password, returnSecureToken: true })
  }).then(async function (response) {
    const data = await response.json().catch(function () { return {}; });
    if (!response.ok || !data.idToken) {
      const code = data && data.error && data.error.message || "";
      const messages = {
        "EMAIL_NOT_FOUND": "Não encontrei uma conta com esse e-mail.",
        "INVALID_PASSWORD": "E-mail ou senha incorretos.",
        "INVALID_LOGIN_CREDENTIALS": "E-mail ou senha incorretos.",
        "USER_DISABLED": "Esta conta está desativada.",
        "TOO_MANY_ATTEMPTS_TRY_LATER": "Muitas tentativas. Aguarde e tente novamente.",
        "OPERATION_NOT_ALLOWED": "Login por e-mail ainda não está habilitado no Firebase."
      };
      throw new Error(messages[code] || "Não foi possível entrar. Confira suas credenciais e tente novamente.");
    }
    // Troca o ID token curto do Firebase por uma sessão opaca revogável da extensão.
    return createApiSession(data.idToken, data.email || email);
  });
}

/* Esta função é serializada pelo navegador e executada na aba ativa da loja. */
function extractProductFromPage() {
  function readPrice(value) {
    if (typeof value === "number") return value > 0 ? Math.round(value * 100) / 100 : null;
    let text = String(value == null ? "" : value).replace(/[^\d,.\-]/g, "").trim();
    if (!text) return null;
    if (text.indexOf(",") >= 0 && text.indexOf(".") >= 0) {
      text = text.lastIndexOf(",") > text.lastIndexOf(".")
        ? text.replace(/\./g, "").replace(",", ".")
        : text.replace(/,/g, "");
    } else if (text.indexOf(",") >= 0) {
      text = text.replace(/\./g, "").replace(",", ".");
    } else if ((text.match(/\./g) || []).length > 1) {
      const parts = text.split(".");
      text = parts.slice(0, -1).join("") + "." + parts[parts.length - 1];
    }
    const number = Number(text);
    return Number.isFinite(number) && number > 0 ? Math.round(number * 100) / 100 : null;
  }

  function firstText(selectors) {
    for (let i = 0; i < selectors.length; i += 1) {
      const el = document.querySelector(selectors[i]);
      if (!el) continue;
      let value = el.getAttribute("content") || el.getAttribute("data-price") ||
        el.getAttribute("value") || el.textContent || "";
      value = String(value).trim();
      if (value) return value;
    }
    return "";
  }

  function asString(value) {
    if (typeof value === "string" || typeof value === "number") return String(value);
    if (value && typeof value === "object") return String(value.name || value.value || "");
    return "";
  }

  function findProduct(value, depth) {
    if (!value || depth > 7) return null;
    if (Array.isArray(value)) {
      for (let i = 0; i < value.length; i += 1) {
        const found = findProduct(value[i], depth + 1);
        if (found) return found;
      }
      return null;
    }
    if (typeof value !== "object") return null;
    const type = value["@type"];
    if (type === "Product" || (Array.isArray(type) && type.indexOf("Product") >= 0)) return value;
    if (value["@graph"]) {
      const graph = findProduct(value["@graph"], depth + 1);
      if (graph) return graph;
    }
    if (value.itemListElement) return findProduct(value.itemListElement, depth + 1);
    return null;
  }

  function getOffer(product) {
    let offer = product && product.offers;
    if (Array.isArray(offer)) offer = offer[0];
    return offer && typeof offer === "object" ? offer : {};
  }

  function extractCoupons(text) {
    const found = [];
    const chunks = text.match(/.{0,60}(?:cupom|código promocional|codigo promocional|código de desconto|codigo de desconto|use o código|use o codigo).{0,100}/gi) || [];
    const stop = new Set(["CUPOM", "CUPONS", "DESCONTO", "CODIGO", "PROMOCIONAL", "USE", "OFICIAL", "APLICAR", "OFF"]);
    chunks.forEach(function (chunk) {
      const codes = chunk.toUpperCase().match(/\b[A-Z0-9][A-Z0-9_-]{3,19}\b/g) || [];
      codes.forEach(function (code) {
        if (stop.has(code) || found.some(function (item) { return item.code === code; })) return;
        found.push({ code: code, description: chunk.trim().slice(0, 150) });
      });
    });
    return found.slice(0, 6);
  }

  function conditionsFromText(text) {
    const freeShipping = /frete\s+(?:gr[aá]tis|gratis|gratuito|gratuita)|envio\s+gr[aá]tis|entrega\s+gr[aá]tis/i.test(text) ? true : null;
    const shippingChunks = text.match(/(?:frete|entrega|envio)[^.!?\n]{0,100}/gi) || [];
    const shippingText = (shippingChunks.find(function (chunk) {
      return /gr[aá]tis|gratis|R\$|calcular|consulte/i.test(chunk);
    }) || "").trim().slice(0, 220);
    const installmentMatch = text.match(/\b(\d{1,2})\s*x\s*(?:de\s*)?(?:R\$\s*)?([\d.]+,\d{2}|[\d,]+\.\d{2})?\s*(sem\s+juros|com\s+juros)?/i);
    let installmentCount = null, installmentAmount = null, installmentTotal = null, installmentInterest = null, installmentText = "";
    if (installmentMatch) {
      const count = Number(installmentMatch[1]);
      const amount = readPrice(installmentMatch[2]);
      if (count >= 1 && count <= 48) {
        installmentCount = count;
        installmentAmount = amount;
        installmentTotal = amount ? Math.round(amount * count * 100) / 100 : null;
        const interestText = String(installmentMatch[3] || "").toLowerCase();
        if (interestText.indexOf("sem juros") >= 0) installmentInterest = false;
        else if (interestText.indexOf("com juros") >= 0) installmentInterest = true;
        installmentText = installmentMatch[0].trim().slice(0, 180);
      }
    }
    return {
      free_shipping: freeShipping,
      shipping_text: shippingText,
      installment_count: installmentCount,
      installment_amount: installmentAmount,
      installment_total: installmentTotal,
      installment_interest: installmentInterest,
      installment_text: installmentText,
      coupons: extractCoupons(text)
    };
  }

  let product = null;
  const scripts = document.querySelectorAll('script[type="application/ld+json"]');
  for (let i = 0; i < scripts.length && !product; i += 1) {
    try { product = findProduct(JSON.parse(scripts[i].textContent || ""), 0); } catch (_) {}
  }

  const offer = getOffer(product || {});
  const priceSpec = offer.priceSpecification && typeof offer.priceSpecification === "object" ? offer.priceSpecification : {};
  const currency = String(offer.priceCurrency || priceSpec.priceCurrency || "BRL").toUpperCase();
  let price = readPrice(offer.price != null ? offer.price : (offer.lowPrice != null ? offer.lowPrice : priceSpec.price));
  if (currency !== "BRL") price = null;
  if (price == null) {
    const rawPrice = firstText([
      'meta[property="product:price:amount"]',
      'meta[property="og:price:amount"]',
      'meta[itemprop="price"]',
      '[itemprop="price"]',
      '[data-testid*="price"]',
      '[class*="price--promotional"]',
      '[class*="sales-price"]',
      '[class*="price-current"]'
    ]);
    if (currency === "BRL" || /R\$\s?/i.test(rawPrice)) price = readPrice(rawPrice);
  }

  const title = asString(product && product.name) ||
    firstText(['meta[property="og:title"]', 'meta[name="twitter:title"]', "h1"]) || document.title || "";
  const brand = asString(product && product.brand) || firstText(['meta[itemprop="brand"]']);
  const model = asString(product && (product.model || product.mpn)) || "";
  const ean = asString(product && (product.gtin13 || product.gtin14 || product.gtin12 || product.gtin8 || product.gtin)) ||
    asString(product && product.sku);
  const rawImage = product && product.image;
  let image = Array.isArray(rawImage) ? rawImage[0] : (rawImage && typeof rawImage === "object" ? rawImage.url : rawImage);
  image = asString(image) || firstText(['meta[property="og:image"]', 'meta[name="twitter:image"]']);
  try { if (image) image = new URL(image, location.href).href; } catch (_) { image = ""; }

  const pageText = String(document.body && document.body.innerText || "").replace(/\s+/g, " ").slice(0, 18000);
  const conditions = conditionsFromText(pageText);
  const canonical = document.querySelector('link[rel="canonical"]');
  let canonicalUrl = location.href;
  try {
    if (canonical && canonical.href && new URL(canonical.href).hostname === location.hostname) canonicalUrl = canonical.href;
  } catch (_) {}

  return {
    title: title.trim().slice(0, 300),
    url: canonicalUrl.slice(0, 2048),
    price: price,
    brand: brand.trim().slice(0, 150),
    model: model.trim().slice(0, 150),
    ean: ean.trim().slice(0, 32),
    image_url: image,
    source: location.hostname,
    free_shipping: conditions.free_shipping,
    shipping_text: conditions.shipping_text,
    installment_count: conditions.installment_count,
    installment_amount: conditions.installment_amount,
    installment_total: conditions.installment_total,
    installment_interest: conditions.installment_interest,
    installment_text: conditions.installment_text,
    coupons: conditions.coupons
  };
}

function extractCurrentTab() {
  return new Promise(function (resolve) {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      const tab = tabs && tabs[0];
      if (!tab || !tab.id || !tab.url || !/^https?:\/\//i.test(tab.url)) {
        resolve({ error: "Abra a página de um produto em uma loja e clique novamente na extensão." });
        return;
      }
      chrome.scripting.executeScript({ target: { tabId: tab.id }, func: extractProductFromPage }, function (results) {
        if (chrome.runtime.lastError) {
          resolve({ error: "O navegador não permite ler esta página. Abra a página normal da loja e tente de novo." });
          return;
        }
        const product = results && results[0] && results[0].result;
        if (!product || !product.url || !product.title) {
          resolve({ error: "Não consegui reconhecer um produto nesta página. Abra a página de detalhes do produto." });
          return;
        }
        try { product.source = new URL(tab.url).hostname; } catch (_) {}
        resolve({ product: product });
      });
    });
  });
}

function shortSource(offer) {
  if (offer && offer.source) return String(offer.source);
  try { return new URL(offer.url).hostname.replace(/^www\./, ""); } catch (_) { return "Loja"; }
}

function shippingLabel(offer) {
  if (offer && offer.free_shipping === true) return { text: "Frete grátis", kind: "good" };
  const delivery = String((offer && (offer.shipping_text || offer.delivery)) || "");
  if (/gr[aá]tis|gratis|free delivery/i.test(delivery)) return { text: "Frete grátis", kind: "good" };
  if (delivery) return { text: delivery.slice(0, 85), kind: "warn" };
  return { text: "Frete não confirmado", kind: "warn" };
}

function installmentLabel(offer) {
  const count = Number(offer && offer.installment_count);
  if (!count) return { text: "Parcelamento não identificado", kind: "warn" };
  const amount = Number(offer.installment_amount);
  let text = count + "×";
  if (Number.isFinite(amount) && amount > 0) text += " " + money(amount);
  if (offer.installment_interest === false) text += " sem juros";
  else if (offer.installment_interest === true) text += " com juros";
  else text += " · juros não informado";
  return { text: text, kind: offer.installment_interest === false ? "good" : "" };
}

function pageConditionChips(product) {
  const chips = [];
  const shipping = shippingLabel(product);
  chips.push('<span class="chip ' + shipping.kind + '">' + escapeHtml(shipping.text) + '</span>');
  const installment = installmentLabel(product);
  chips.push('<span class="chip ' + installment.kind + '">' + escapeHtml(installment.text) + '</span>');
  (product.coupons || []).slice(0, 3).forEach(function (coupon) {
    chips.push('<span class="chip coupon">Cupom ' + escapeHtml(coupon.code) + '</span>');
  });
  return chips.join("");
}

function renderProduct(product) {
  const section = document.getElementById("product-panel");
  section.classList.remove("hidden");
  document.getElementById("product-title").textContent = product.title || "Produto sem nome";
  document.getElementById("product-store").textContent = product.source || shortSource(product);
  document.getElementById("product-price").textContent = product.price ? money(product.price) : "Não detectado";
  document.getElementById("current-conditions").innerHTML = pageConditionChips(product);
  const image = document.getElementById("product-image");
  if (product.image_url && /^https:\/\//i.test(product.image_url)) {
    image.src = product.image_url;
    image.classList.remove("hidden");
    image.onerror = function () { image.classList.add("hidden"); };
  } else {
    image.classList.add("hidden");
  }
}

function normalizeUrlKey(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/^www\./, "");
    const path = url.pathname.replace(/\/+$/, "") || "/";
    return host + path;
  } catch (_) {
    return String(value || "").toLowerCase();
  }
}

function mergeOffers(groups) {
  const byKey = new Map();
  (groups || []).forEach(function (group) {
    (group || []).forEach(function (offer) {
      if (!offer || !offer.url) return;
      const key = normalizeUrlKey(offer.url);
      const old = byKey.get(key);
      if (!old) {
        byKey.set(key, Object.assign({}, offer));
        return;
      }
      const merged = Object.assign({}, old);
      Object.keys(offer).forEach(function (name) {
        const value = offer[name];
        if (value !== null && value !== undefined && value !== "" && !(Array.isArray(value) && !value.length)) {
          if (name === "coupons" && old.coupons && old.coupons.length) merged.coupons = old.coupons.concat(value).filter(function (item, index, arr) {
            return arr.findIndex(function (candidate) { return candidate.code === item.code; }) === index;
          });
          else merged[name] = value;
        }
      });
      byKey.set(key, merged);
    });
  });
  return Array.from(byKey.values()).sort(function (a, b) {
    const aPrice = Number(a.price) > 0 ? Number(a.price) : Infinity;
    const bPrice = Number(b.price) > 0 ? Number(b.price) : Infinity;
    return aPrice - bPrice;
  });
}

function renderCommunityHistory(events) {
  const panel = document.getElementById("history-panel");
  const box = document.getElementById("price-history");
  const count = document.getElementById("history-count");
  const rows = (events || []).filter(function (item) { return Number(item.price) > 0; }).slice(0, 8);
  if (!rows.length) {
    panel.classList.add("hidden");
    box.innerHTML = "";
    count.textContent = "";
    return;
  }
  panel.classList.remove("hidden");
  count.textContent = rows.length + " registro(s)";
  box.innerHTML = rows.map(function (item) {
    let when = "Data não informada";
    try {
      const date = new Date(item.observedAt);
      if (!Number.isNaN(date.getTime())) when = date.toLocaleDateString("pt-BR") + " " + date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    } catch (_) {}
    return '<div class="history-row"><div><div class="history-source">' +
      escapeHtml(item.source || "Loja") + '</div><div class="history-date">' +
      escapeHtml(when) + '</div></div><strong class="history-price">' +
      escapeHtml(money(item.price)) + '</strong></div>';
  }).join("");
}

function renderOffers(offers) {
  const box = document.getElementById("offers");
  if (!offers || !offers.length) {
    box.innerHTML = '<div class="empty">Ainda não encontramos outras ofertas para confirmar. A captura atual, quando tem preço, já contribui para a base comunitária.</div>';
    document.getElementById("summary-panel").classList.add("hidden");
    return;
  }
  const priced = offers.filter(function (offer) { return Number(offer.price) > 0; }).sort(function (a, b) { return Number(a.price) - Number(b.price); });
  const best = priced[0];
  const summary = document.getElementById("summary-panel");
  if (best) {
    summary.classList.remove("hidden");
    document.getElementById("best-price").textContent = money(best.price);
    document.getElementById("best-store").textContent = shortSource(best);
    const count = communityData && communityData.product
      ? Number(communityData.contributorCount || communityData.product.contributorCount || 0)
      : Number((communityData && communityData.contributorCount) || 0);
    const stores = new Set(offers.map(function (offer) { return shortSource(offer); })).size;
    document.getElementById("community-count").textContent = stores + " loja(s) · " + count + " colaborador(es) na base deste produto.";
  } else {
    summary.classList.add("hidden");
  }

  box.innerHTML = offers.slice(0, 15).map(function (offer, index) {
    const title = offer.title || offer.productTitle || "Oferta em " + shortSource(offer);
    const source = shortSource(offer);
    const price = Number(offer.price) > 0 ? money(offer.price) : "Preço não informado";
    const shipping = shippingLabel(offer);
    const installment = installmentLabel(offer);
    const img = offer.image_url && /^https:\/\//i.test(offer.image_url)
      ? '<img class="offer-image" src="' + escapeHtml(offer.image_url) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display=\'none\'">'
      : '<div class="offer-image offer-placeholder">🛍️</div>';
    const couponMarkup = (offer.coupons || []).slice(0, 4).map(function (coupon) {
      const code = String(coupon.code || "").trim();
      if (!code) return "";
      return '<button type="button" class="coupon-code" data-copy-coupon="' + escapeHtml(code) + '" title="' +
        escapeHtml(coupon.description || "Cupom identificado; confira as regras") + '">' + escapeHtml(code) + ' ⧉</button>';
    }).join("");
    const detailParts = [
      '<span class="offer-detail ' + shipping.kind + '">' + escapeHtml(shipping.text) + '</span>',
      '<span class="offer-detail ' + installment.kind + '">' + escapeHtml(installment.text) + '</span>'
    ];
    if (offer.installment_total) detailParts.push('<span class="offer-detail">Total parcelado: ' + escapeHtml(money(offer.installment_total)) + '</span>');
    if (offer.rating) detailParts.push('<span class="offer-detail">★ ' + escapeHtml(offer.rating) + (offer.reviews ? ' (' + escapeHtml(offer.reviews) + ')' : "") + '</span>');
    const label = offer.isCurrent ? "Página aberta agora" : (offer.community ? "Base da comunidade" : (offer.sourceType === "shopping" ? "Pesquisa de lojas" : "Oferta registrada"));
    const safeUrl = /^https:\/\//i.test(String(offer.url || "")) ? offer.url : "";
    return '<article class="offer">' + img + '<div class="offer-body">' +
      '<div class="offer-top"><div class="offer-title">' + (index === 0 && priced.length ? '🏷️ ' : '') + escapeHtml(title) + '</div><div class="offer-price">' + escapeHtml(price) + '</div></div>' +
      '<div class="offer-store">' + escapeHtml(source) + '</div>' +
      '<div class="offer-details">' + detailParts.join("") + '</div>' +
      (couponMarkup ? '<div class="offer-coupons">' + couponMarkup + '</div>' : '') +
      '<div class="offer-actions"><span class="offer-label">' + escapeHtml(label) + '</span>' +
      (safeUrl ? '<a class="offer-link" href="' + escapeHtml(safeUrl) + '" target="_blank" rel="noopener noreferrer">Abrir loja ↗</a>' : '') +
      '</div></div></article>';
  }).join("");
}

function makeSearchQuery(product) {
  const pieces = [product.brand, product.model, product.title].map(function (x) { return String(x || "").trim(); }).filter(Boolean);
  const unique = [];
  pieces.forEach(function (piece) { if (unique.indexOf(piece) < 0) unique.push(piece); });
  return unique.join(" ").replace(/\s+/g, " ").slice(0, 180);
}

async function runComparison() {
  if (!currentProduct || comparisonBusy) return;
  comparisonBusy = true;
  const button = document.getElementById("compare-again");
  button.disabled = true;
  setState("Capturando o preço e as condições desta página e atualizando a base comunitária…");
  renderProduct(currentProduct);
  try {
    communityData = await api("/community/observe", {
      method: "POST",
      body: JSON.stringify(currentProduct)
    });
    const query = makeSearchQuery(currentProduct);
    const [communityResult, shoppingResult] = await Promise.all([
      api("/community/search?q=" + encodeURIComponent(query)).catch(function (error) {
        return { products: [], error: error.message };
      }),
      api("/search?q=" + encodeURIComponent(query)).catch(function (error) {
        return { offers: [], error: error.message, coverageNote: "" };
      })
    ]);

    const matchedProduct = (communityResult.products || []).find(function (item) {
      return item && item.id === communityData.productKey;
    }) || (communityResult.products || []).find(function (item) {
      return item && Number(item.matchScore) >= 0.45;
    }) || null;
    communityData.searchMatch = matchedProduct;
    renderCommunityHistory(matchedProduct ? matchedProduct.history : []);

    const fromCommunity = [];
    (communityData.offers || []).forEach(function (offer) {
      fromCommunity.push(Object.assign({}, offer, {
        community: true,
        isCurrent: normalizeUrlKey(offer.url) === normalizeUrlKey(currentProduct.url),
        sourceType: "community"
      }));
    });
    (communityResult.products || []).filter(function (product) {
      return product && product.id !== communityData.productKey && Number(product.matchScore) >= 0.45;
    }).slice(0, 3).forEach(function (product) {
      (product.offers || []).forEach(function (offer) {
        fromCommunity.push(Object.assign({}, offer, {
          community: true,
          productTitle: product.title,
          sourceType: "community"
        }));
      });
    });

    const fromShopping = (shoppingResult.offers || []).filter(function (offer) {
      return offer && Number(offer.matchScore == null ? 1 : offer.matchScore) >= 0.3;
    }).map(function (offer) {
      return Object.assign({}, offer, { sourceType: "shopping" });
    });
    const current = [Object.assign({}, currentProduct, { isCurrent: true, sourceType: "current" })];
    combinedOffers = mergeOffers([fromCommunity, fromShopping, current]);

    renderOffers(combinedOffers);
    const messages = [];
    if (shoppingResult.error) messages.push("Pesquisa externa: " + shoppingResult.error);
    if (communityResult.error) messages.push("Base comunitária: " + communityResult.error);
    document.getElementById("coverage-note").textContent = messages.length
      ? messages.join(" ")
      : "A comparação combina ofertas pesquisadas e registros da comunidade Resolvei. Nem todas as lojas divulgam frete, parcelamento e cupons em dados públicos.";
    if (!shoppingResult.offers || !shoppingResult.offers.length) {
      document.getElementById("coverage-note").textContent += " As lojas e condições da pesquisa externa podem ficar indisponíveis; os registros comunitários continuam sendo exibidos.";
    }
    const numberOffers = combinedOffers.filter(function (offer) { return Number(offer.price) > 0; }).length;
    setState("Produto registrado na base comunitária. " + numberOffers + " oferta(s) com preço disponível para comparar.", "success");
    const couponOffers = combinedOffers.filter(function (offer) { return offer.coupons && offer.coupons.length; }).length;
    const couponNote = document.getElementById("coupon-note");
    if (couponOffers) {
      couponNote.classList.remove("hidden");
      couponNote.textContent = "Encontramos cupons em " + couponOffers + " oferta(s). Clique no código para copiá-lo e confira a validade e as regras na loja.";
    } else {
      couponNote.classList.add("hidden");
    }
  } catch (error) {
    renderOffers(combinedOffers);
    setState(error.message || "Não foi possível comparar as ofertas.", "error");
    if (/sessão|entrar|login/i.test(error.message || "")) showLogin(error.message, true);
  } finally {
    comparisonBusy = false;
    button.disabled = false;
  }
}

function launchGoogleLogin() {
  chrome.windows.create({
    url: chrome.runtime.getURL("login.html"),
    type: "popup",
    width: 460,
    height: 640
  });
}

function bindUI() {
  document.getElementById("login-form").addEventListener("submit", async function (event) {
    event.preventDefault();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const button = document.getElementById("login-email");
    button.disabled = true;
    button.textContent = "Entrando…";
    setState("Validando a conta do Resolvei…");
    try {
      await loginWithEmail(email, password);
      showApp();
      setState("Login concluído. Identificando a página do produto…", "success");
      if (currentProduct) await runComparison();
    } catch (error) {
      showLogin(error.message || "Não foi possível entrar.", true);
    } finally {
      button.disabled = false;
      button.textContent = "Entrar com e-mail";
    }
  });

  document.getElementById("login-google").addEventListener("click", launchGoogleLogin);

  document.getElementById("logout").addEventListener("click", async function () {
    const session = await storageGet(SESSION_KEY);
    if (session && session.apiToken) {
      fetch(API_BASE + "/extension/session/revoke", {
        method: "POST",
        headers: { "Authorization": "Bearer " + session.apiToken }
      }).catch(function () {});
    }
    await storageClear();
    activeUser = null;
    showLogin("Você saiu da conta do Resolvei.", false);
    document.getElementById("product-panel").classList.add("hidden");
  });

  document.getElementById("compare-again").addEventListener("click", function () {
    runComparison().catch(function () {});
  });

  document.getElementById("offers").addEventListener("click", async function (event) {
    const button = event.target.closest("[data-copy-coupon]");
    if (!button) return;
    const code = button.getAttribute("data-copy-coupon") || "";
    try {
      await navigator.clipboard.writeText(code);
      setState("Cupom " + code + " copiado. Confira as regras antes de aplicar.", "success");
    } catch (_) {
      setState("Código do cupom: " + code + ". Selecione e copie manualmente.", "");
    }
  });
}

async function initialize() {
  bindUI();
  let session = null;
  try {
    session = await storageGet(SESSION_KEY);
    if (session && session.apiToken && Number(session.expiresAt) > Date.now()) {
      activeUser = session.email || "";
      showApp();
    } else {
      if (session) await storageClear();
      activeUser = null;
      showLogin("Entre com sua conta para comparar os preços e compartilhar observações.");
    }
  } catch (error) {
    await storageClear();
    showLogin(error.message || "Entre novamente na conta do Resolvei.", true);
  }

  const capture = await extractCurrentTab();
  if (capture.product) {
    currentProduct = capture.product;
    renderProduct(currentProduct);
    if (activeUser) {
      await runComparison();
    } else {
      setState("Produto identificado. Entre na conta para comparar lojas e registrar os dados na base comunitária.");
    }
  } else {
    if (activeUser) {
      setState(capture.error || "Abra uma página de produto e tente novamente.");
      document.getElementById("offers").innerHTML = '<div class="empty">' + escapeHtml(capture.error || "Abra uma página de produto e tente novamente.") + '</div>';
    } else {
      setState(capture.error || "Entre na conta do Resolvei e abra uma página de produto.");
    }
  }
}

document.addEventListener("DOMContentLoaded", initialize);
