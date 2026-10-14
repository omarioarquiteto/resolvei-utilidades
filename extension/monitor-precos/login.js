"use strict";

const SESSION_KEY = "resolveiPriceMonitorSession";
const RESOLVEI_ORIGIN = "https://resolvei-utilidades.onrender.com";
let authWindow = null;
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

window.addEventListener("message", function (event) {
  if (event.origin !== RESOLVEI_ORIGIN || !authWindow || event.source !== authWindow) return;
  const data = event.data || {};
  if (data.type !== "resolvei-extension-auth" || !data.idToken) return;
  const session = {
    idToken: data.idToken,
    email: String(data.email || ""),
    expiresAt: Number(data.expiresAt || (Date.now() + 3500000))
  };
  chrome.storage.local.set({ [SESSION_KEY]: session }, function () {
    if (chrome.runtime.lastError) {
      setState("O login funcionou, mas não consegui salvar a sessão: " + chrome.runtime.lastError.message, "error");
      button.disabled = false;
      return;
    }
    setState("Login concluído. A sessão do Resolvei foi conectada à extensão.", "success");
    if (authWindow && !authWindow.closed) authWindow.close();
    authWindow = null;
    window.setTimeout(function () { window.close(); }, 1200);
  });
});
