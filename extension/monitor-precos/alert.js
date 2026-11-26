"use strict";

const API_BASE = "https://resolvei-utilidades.onrender.com/api/price-monitor";
const SESSION_KEY = "resolveiPriceMonitorSession";
const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
    return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch];
  });
}

function price(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? money.format(number) : "Preço não identificado";
}

function storageGet(key) {
  return new Promise(function (resolve) {
    chrome.storage.local.get([key], function (data) { resolve(data && data[key] ? data[key] : null); });
  });
}

async function load() {
  const box = document.getElementById("alert-products");
  try {
    const session = await storageGet(SESSION_KEY);
    if (!session || !session.apiToken || Number(session.expiresAt) <= Date.now()) {
      throw new Error("Sua sessão da extensão expirou. Entre novamente no Resolvei.");
    }
    const response = await fetch(API_BASE + "/products", {
      headers: { "Authorization": "Bearer " + session.apiToken, "Accept": "application/json" },
      cache: "no-store"
    });
    const data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.detail || "Não foi possível carregar o produto.");
    const params = new URLSearchParams(location.search);
    const ids = (params.get("ids") || params.get("productId") || "").split(",").filter(Boolean);
    const products = (data.products || []).filter(function (item) {
      return ids.indexOf(String(item.id)) >= 0 && item.targetReached === true;
    });
    if (!products.length) {
      box.innerHTML = '<div class="error">O alerta foi registrado, mas o produto não está mais disponível nesta lista.</div>';
      return;
    }
    box.innerHTML = products.map(function (product) {
      const current = Number(product.bestOfferPrice) > 0 ? product.bestOfferPrice : product.price;
      const destination = /^https:\/\//i.test(product.bestOfferUrl || "")
        ? product.bestOfferUrl : product.url;
      return '<article class="alert-product">' +
        '<div class="product-title">' + escapeHtml(product.title || "Produto monitorado") + '</div>' +
        '<div class="store">' + escapeHtml(product.bestOfferSource || (function () {
          try { return new URL(product.url).hostname.replace(/^www\./, ""); } catch (_) { return "Loja"; }
        })()) + '</div>' +
        '<div class="price-row"><div><span class="price-label">Preço encontrado</span><strong class="price">' + escapeHtml(price(current)) + '</strong></div>' +
        '<div class="target">Sua meta<strong>' + escapeHtml(price(product.targetPrice)) + '</strong></div></div>' +
        '<a class="open-offer" href="' + escapeHtml(destination) + '" target="_blank" rel="noopener">Abrir produto na loja ↗</a>' +
        '</article>';
    }).join("");
  } catch (error) {
    box.innerHTML = '<div class="error">' + escapeHtml(error.message || "Não foi possível abrir o alerta.") + '</div>';
  }
}

document.addEventListener("DOMContentLoaded", load);
