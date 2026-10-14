"use strict";

var currentProduct = null;
var brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function parsePrice(value) {
  if (typeof value === "number") return value > 0 ? Math.round(value * 100) / 100 : null;
  var text = String(value == null ? "" : value).replace(/[^\d,.\-]/g, "").trim();
  if (!text) return null;
  if (text.indexOf(",") >= 0 && text.indexOf(".") >= 0) {
    text = text.lastIndexOf(",") > text.lastIndexOf(".")
      ? text.replace(/\./g, "").replace(",", ".")
      : text.replace(/,/g, "");
  } else if (text.indexOf(",") >= 0) text = text.replace(/\./g, "").replace(",", ".");
  else if ((text.match(/\./g) || []).length > 1) {
    var pieces = text.split(".");
    text = pieces.slice(0, -1).join("") + "." + pieces[pieces.length - 1];
  }
  var number = Number(text);
  return Number.isFinite(number) && number > 0 ? Math.round(number * 100) / 100 : null;
}

function extractProductFromPage() {
  function firstText(selectors) {
    for (var i = 0; i < selectors.length; i += 1) {
      var el = document.querySelector(selectors[i]);
      if (!el) continue;
      var value = el.getAttribute("content") || el.getAttribute("data-price") || el.getAttribute("value") || el.textContent || "";
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
      for (var i = 0; i < value.length; i += 1) {
        var found = findProduct(value[i], depth + 1);
        if (found) return found;
      }
      return null;
    }
    if (typeof value !== "object") return null;
    var type = value["@type"];
    if (type === "Product" || (Array.isArray(type) && type.indexOf("Product") >= 0)) return value;
    if (value["@graph"]) {
      var graph = findProduct(value["@graph"], depth + 1);
      if (graph) return graph;
    }
    if (value.itemListElement) {
      var item = findProduct(value.itemListElement, depth + 1);
      if (item) return item;
    }
    return null;
  }
  function findOffer(product) {
    var offer = product && product.offers;
    if (Array.isArray(offer)) offer = offer[0];
    return offer && typeof offer === "object" ? offer : {};
  }

  var product = null;
  var scripts = document.querySelectorAll('script[type="application/ld+json"]');
  for (var i = 0; i < scripts.length && !product; i += 1) {
    try { product = findProduct(JSON.parse(scripts[i].textContent || ""), 0); } catch (_) {}
  }
  var offer = findOffer(product || {});
  var currency = String(offer.priceCurrency || (offer.priceSpecification && offer.priceSpecification.priceCurrency) || "BRL").toUpperCase();
  var price = parsePrice(offer.price != null ? offer.price : offer.lowPrice);
  if (currency !== "BRL") price = null;
  if (price == null) {
    var rawPrice = firstText([
      'meta[property="product:price:amount"]',
      'meta[property="og:price:amount"]',
      'meta[itemprop="price"]',
      '[itemprop="price"]',
      '[data-testid*="price"]',
      '[class*="price--promotional"]',
      '[class*="sales-price"]'
    ]);
    if (currency === "BRL" || /R\$\s?/.test(rawPrice)) price = parsePrice(rawPrice);
  }
  var title = asString(product && product.name) ||
    firstText(['meta[property="og:title"]', 'meta[name="twitter:title"]', "h1"]) || document.title || "";
  var brand = asString(product && product.brand) || firstText(['meta[itemprop="brand"]']);
  var model = asString(product && (product.model || product.mpn)) || "";
  var ean = asString(product && (product.gtin13 || product.gtin14 || product.gtin12 || product.gtin8 || product.gtin)) ||
    asString(product && product.sku);
  var rawImage = product && product.image;
  var image = Array.isArray(rawImage) ? rawImage[0] : (rawImage && typeof rawImage === "object" ? rawImage.url : rawImage);
  image = asString(image) || firstText(['meta[property="og:image"]', 'meta[name="twitter:image"]']);
  try { if (image) image = new URL(image, location.href).href; } catch (_) { image = ""; }
  var canonical = document.querySelector('link[rel="canonical"]');
  var canonicalUrl = location.href;
  try {
    if (canonical && canonical.href && new URL(canonical.href).hostname === location.hostname) canonicalUrl = canonical.href;
  } catch (_) {}
  return {
    title: title.trim().slice(0, 300),
    url: canonicalUrl,
    price: price,
    brand: brand.trim().slice(0, 150),
    model: model.trim().slice(0, 150),
    ean: ean.trim().slice(0, 32),
    image_url: image,
    source: location.hostname
  };
}

function setState(message, error) {
  var state = document.getElementById("state");
  state.textContent = message;
  state.className = "state" + (error ? " error" : "");
}
function renderProduct(product) {
  currentProduct = product;
  document.getElementById("product").classList.remove("hidden");
  document.getElementById("title").textContent = product.title || "Produto sem nome identificado";
  document.getElementById("store").textContent = product.source || new URL(product.url).hostname;
  document.getElementById("price").textContent = product.price == null ? "Não identificado" : brl.format(product.price);
  var image = document.getElementById("image");
  if (product.image_url) {
    image.src = product.image_url;
    image.classList.remove("hidden");
    image.onerror = function () { image.classList.add("hidden"); };
  }
  document.getElementById("manual-price").value = product.price == null ? "" : String(product.price);
  document.getElementById("send").disabled = !product.title || !product.url;
}
function extractCurrentTab() {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    var tab = tabs && tabs[0];
    if (!tab || !tab.id || !tab.url || !/^https?:\/\//i.test(tab.url)) {
      setState("Abra uma página HTTPS de um produto em uma loja e clique novamente na extensão.", true);
      return;
    }
    chrome.scripting.executeScript({ target: { tabId: tab.id }, func: extractProductFromPage }, function (results) {
      if (chrome.runtime.lastError) {
        setState("O navegador não permite ler esta página. Abra a página normal da loja e tente novamente.", true);
        return;
      }
      var product = results && results[0] && results[0].result;
      if (!product || !product.url || !product.title) {
        setState("Não consegui identificar o produto automaticamente. Tente a página de detalhes do produto.", true);
        return;
      }
      product.source = new URL(tab.url).hostname;
      renderProduct(product);
      setState(product.price == null
        ? "Produto identificado. O preço não foi detectado; informe-o abaixo se desejar."
        : "Produto identificado. Confira os dados antes de continuar.", false);
    });
  });
}
document.addEventListener("DOMContentLoaded", function () {
  extractCurrentTab();
  document.getElementById("send").addEventListener("click", function () {
    if (!currentProduct) return;
    var manual = parsePrice(document.getElementById("manual-price").value);
    if (manual != null) currentProduct.price = manual;
    var destination = "https://resolvei-utilidades.onrender.com/#/ferramenta/monitor-precos";
    destination += "?capture=" + encodeURIComponent(JSON.stringify(currentProduct));
    chrome.tabs.create({ url: destination });
    setState("Abrindo o Resolvei. Confira os dados e clique em “Monitorar produto” para salvar.", false);
  });
});