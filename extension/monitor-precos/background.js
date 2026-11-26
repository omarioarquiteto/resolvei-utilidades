"use strict";

const API_BASE = "https://resolvei-utilidades.onrender.com/api/price-monitor";
const SESSION_KEY = "resolveiPriceMonitorSession";
const ALERTS_KEY = "resolveiPriceMonitorAlertEvents";
const ALARM_NAME = "resolvei-price-target-check";
let checking = false;

function storageGet(keys) {
  return new Promise(function (resolve) {
    chrome.storage.local.get(keys, resolve);
  });
}

function storageSet(values) {
  return new Promise(function (resolve, reject) {
    chrome.storage.local.set(values, function () {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve();
    });
  });
}

async function fetchProducts(session) {
  const response = await fetch(API_BASE + "/products", {
    method: "GET",
    headers: {
      "Authorization": "Bearer " + session.apiToken,
      "Accept": "application/json"
    },
    cache: "no-store"
  });
  const payload = await response.json().catch(function () { return {}; });
  if (response.status === 401) {
    await chrome.storage.local.remove([SESSION_KEY]);
    return [];
  }
  if (!response.ok) {
    throw new Error(payload.detail || "Não foi possível consultar os preços monitorados.");
  }
  return Array.isArray(payload.products) ? payload.products : [];
}

function priceText(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0
    ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(number)
    : "Preço não identificado";
}

function openAlertTab(products) {
  const ids = products.map(function (product) { return String(product.id || ""); })
    .filter(Boolean).slice(0, 30);
  if (!ids.length) return;
  const url = chrome.runtime.getURL("alert.html?ids=" + encodeURIComponent(ids.join(",")));
  chrome.tabs.create({ url: url, active: true });
}

async function openProduct(productId) {
  const values = await storageGet([SESSION_KEY]);
  const session = values[SESSION_KEY];
  if (!session || !session.apiToken || Number(session.expiresAt) <= Date.now()) return;
  const products = await fetchProducts(session);
  const product = products.find(function (item) { return String(item.id) === String(productId); });
  if (!product) return;
  const destination = product.bestOfferUrl || product.url;
  if (destination && /^https:\/\//i.test(destination)) {
    chrome.tabs.create({ url: destination, active: true });
  }
}

async function checkPriceTargets() {
  if (checking) return;
  checking = true;
  try {
    const values = await storageGet([SESSION_KEY, ALERTS_KEY]);
    const session = values[SESSION_KEY];
    if (!session || !session.apiToken || !Number.isFinite(Number(session.expiresAt)) ||
        Number(session.expiresAt) <= Date.now()) return;

    const products = await fetchProducts(session);
    const seen = values[ALERTS_KEY] && typeof values[ALERTS_KEY] === "object"
      ? values[ALERTS_KEY] : {};
    const newlyReached = [];

    products.forEach(function (product) {
      if (!product || product.targetReached !== true || !(Number(product.targetPrice) > 0)) return;
      const eventKey = String(product.targetPrice) + "|" +
        String(product.targetReachedAt || product.lastCheckedAt || product.updatedAt || "");
      if (seen[String(product.id)] === eventKey) return;
      seen[String(product.id)] = eventKey;
      newlyReached.push(product);
    });

    if (!newlyReached.length) return;
    await storageSet({ [ALERTS_KEY]: seen });

    newlyReached.forEach(function (product) {
      const id = "resolvei-price-" + String(product.id);
      const current = Number(product.bestOfferPrice) > 0
        ? product.bestOfferPrice : product.price;
      const message = String(product.title || "Produto monitorado") + ": " +
        priceText(current) + " (meta " + priceText(product.targetPrice) + "). Clique para abrir a oferta.";
      chrome.notifications.create(id, {
        type: "basic",
        iconUrl: chrome.runtime.getURL("icon128.png"),
        title: "Resolvei — meta de preço atingida",
        message: message.slice(0, 240),
        priority: 2,
        requireInteraction: true
      });
    });

    // Uma única tela reúne os produtos que atingiram a meta no mesmo ciclo.
    openAlertTab(newlyReached);
  } catch (error) {
    // O worker pode ser encerrado pelo navegador; a próxima alarme fará nova tentativa.
    console.warn("Resolvei price monitor:", error && error.message ? error.message : "falha");
  } finally {
    checking = false;
  }
}

function ensureAlarm() {
  chrome.alarms.get(ALARM_NAME, function (alarm) {
    if (chrome.runtime.lastError || alarm) return;
    chrome.alarms.create(ALARM_NAME, {
      delayInMinutes: 1,
      periodInMinutes: 1
    });
  });
}

chrome.alarms.onAlarm.addListener(function (alarm) {
  if (alarm && alarm.name === ALARM_NAME) checkPriceTargets();
});

chrome.notifications.onClicked.addListener(function (notificationId) {
  const prefix = "resolvei-price-";
  if (!notificationId || notificationId.indexOf(prefix) !== 0) return;
  const productId = notificationId.slice(prefix.length);
  chrome.notifications.clear(notificationId);
  openProduct(productId).catch(function () {});
});

chrome.runtime.onInstalled.addListener(function () {
  ensureAlarm();
  checkPriceTargets();
});

chrome.runtime.onStartup.addListener(function () {
  ensureAlarm();
  checkPriceTargets();
});

ensureAlarm();
