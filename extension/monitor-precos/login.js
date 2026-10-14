"use strict";

const SESSION_KEY = "resolveiPriceMonitorSession";
const RESOLVEI_ORIGIN = "https://resolvei-utilidades.onrender.com";
const API_BASE = RESOLVEI_ORIGIN + "/api/price-monitor";
let authWindow = null;
let savingSession = false;
const state = document.getElementById("login-state");
const button = document.getElementById("google-start");

function setState(message, type) {
  state.textContent = message;
  state.className = "state" + (type ? " " + type : "");
}

button.addEventListener("click", function () {
  const target = new URL(RESOLVEI_ORIGIN + "/");
  target.searchParams.set("resolveiExtensionOrigin", "chrome-extension://" + chrome.runtime.id);
  target.hash = "/conta";
  setState("Aguardando o login na página oficial do Resolvei…");
  button.disabled = true;
  authWindow = window.open(target.toString(), "resolvei-extension-google-login", "popup,width=470,height=720");
  if (!authWindow) {
    button.disabled = false;
    setState("O navegador bloqueou a janela de login. Permita pop-ups para esta extensão e tente novamente.", "error");
    return;
  }
  authWindow.focus();
});

window.addEventListener("message", async function (event) {
  if (event.origin !== RESOLVEI_ORIGIN || !authWindow || event.source !== authWindow || savingSession) return;
  const data = event.data || {};
  if (data.type !== "resolvei-extension-auth" || !data.idToken) return;
  savingSession = true;
  setState("Login confirmado. Protegendo a sessão da extensão…");
  try {
    const response = await fetch(API_BASE + "/extension/session", {
      method: "POST",
      headers: { "Authorization": "Bearer " + data.idToken }
    });
    const result = await response.json().catch(function () { return {}; });
    if (!response.ok || !result.accessToken) {
      throw new Error(result.detail || "O servidor não conseguiu iniciar a sessão da extensão.");
    }
    const session = {
      apiToken: result.accessToken,
      email: String(data.email || ""),
      expiresAt: Date.parse(result.expiresAt || "") || (Date.now() + 30 * 24 * 60 * 60 * 1000)
    };
    await new Promise(function (resolve, reject) {
      chrome.storage.local.set({ [SESSION_KEY]: session }, function () {
        if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
        else resolve();
      });
    });
    setState("Login concluído. Sua conta do Resolvei está conectada à extensão.", "success");
    if (authWindow && !authWindow.closed) authWindow.close();
    authWindow = null;
    window.setTimeout(function () { window.close(); }, 1200);
  } catch (error) {
    setState(error.message || "Não foi possível guardar a sessão. Tente novamente.", "error");
    button.disabled = false;
    savingSession = false;
  }
});
