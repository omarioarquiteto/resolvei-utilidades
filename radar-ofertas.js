(function () {
"use strict";
var host = null, monitors = [], selectedMonitorId = "", editingId = "";
var brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
function esc(v) { return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) { return ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" })[c]; }); }
function money(v) { return v == null || !Number.isFinite(Number(v)) ? "—" : brl.format(Number(v)); }
function dt(v) { if (!v) return "Ainda não verificado"; var d = new Date(v); return Number.isNaN(d.getTime()) ? "Data indisponível" : d.toLocaleString("pt-BR", { dateStyle:"short", timeStyle:"short" }); }
function notice(message, type) { var el = document.getElementById("dor-notice"); if (!el) return; el.textContent = message; el.className = "dor-notice" + (type ? " " + type : ""); }
function getToken() {
  return new Promise(function (resolve, reject) {
    if (typeof window.resolveiToken !== "function") return reject(new Error("Entre na sua conta do Resolvei para usar o Radar de Ofertas."));
    window.resolveiToken().then(resolve).catch(reject);
  });
}
function api(path, options) {
  options = options || {};
  return getToken().then(function (token) {
    var headers = Object.assign({ Authorization: "Bearer " + token }, options.headers || {});
    if (options.body) headers["Content-Type"] = "application/json";
    return fetch("/api/deal-radar" + path, Object.assign({}, options, { headers: headers }));
  }).then(function (response) {
    return response.json().catch(function () { return {}; }).then(function (data) {
      if (!response.ok) throw new Error(data.detail || "Não foi possível concluir a operação.");
      return data;
    });
  });
}
function shell() {
  host.innerHTML =
    '<div class="dor-page">' +
      '<header class="dor-header"><div><div class="dor-eyebrow">RESOLVEI · COMPRAS INTELIGENTES</div><h1>Radar de Ofertas</h1><p>Encontre oportunidades em lojas específicas e publique no Telegram com seu link de afiliado. Cada monitor tem regras e modo de publicação próprios.</p></div><div class="dor-status"><span></span><b id="dor-status-text">Preparando radar</b></div></header>' +
      '<div id="dor-notice" class="dor-notice" role="status">Carregando o Radar de Ofertas...</div>' +
      '<div class="dor-overview" id="dor-overview"></div>' +
      '<div class="dor-columns">' +
        '<section class="dor-panel"><div class="dor-panel-title"><div><h2 id="dor-form-title">Criar monitoramento</h2><p>Escolha a loja, palavras-chave e os critérios que definem uma boa oferta.</p></div></div>' +
          '<form id="dor-monitor-form">' +
            '<div class="dor-field"><label for="dor-title">Nome do monitoramento</label><input id="dor-title" maxlength="100" required placeholder="Ex.: Consoles e acessórios"></div>' +
            '<div class="dor-field"><label for="dor-store">Loja específica</label><select id="dor-store"><option value="mercado_livre">Mercado Livre</option><option value="amazon">Amazon</option><option value="shopee">Shopee</option><option value="magalu">Magazine Luiza</option></select><small>O Radar consulta a fonte de ofertas disponível e mantém apenas resultados identificados nessa loja.</small></div>' +
            '<div class="dor-field"><label for="dor-keywords">Palavras-chave (até 5)</label><textarea id="dor-keywords" rows="3" required placeholder="console playstation 5&#10;controle dualsense&#10;playstation 5 slim"></textarea><small>Uma por linha ou separadas por vírgula. A pesquisa é ampliada, não exige título idêntico.</small></div>' +
            '<div class="dor-two">' +
              '<div class="dor-field"><label for="dor-discount">Desconto mínimo (%)</label><input id="dor-discount" type="number" min="0" max="90" step="0.5" value="10"></div>' +
              '<div class="dor-field"><label for="dor-max-price">Preço máximo (R$)</label><input id="dor-max-price" type="number" min="0.01" step="0.01" placeholder="Opcional"></div>' +
            '</div>' +
            '<div class="dor-two">' +
              '<div class="dor-field"><label for="dor-interval">Pesquisar a cada</label><select id="dor-interval"><option value="15">15 minutos</option><option value="30" selected>30 minutos</option><option value="60">1 hora</option><option value="180">3 horas</option><option value="360">6 horas</option></select></div>' +
              '<div class="dor-field"><label for="dor-mode">Modo de publicação</label><select id="dor-mode"><option value="approval">Com aprovação</option><option value="automatic">Automático</option></select></div>' +
            '</div>' +
            '<div class="dor-mode-help" id="dor-mode-help">As ofertas aparecem numa fila para você revisar antes de publicar.</div>' +
            '<div class="dor-actions"><button type="submit" class="dor-btn primary" id="dor-save-monitor">＋ Criar monitoramento</button><button type="button" class="dor-btn" id="dor-cancel-edit" hidden>Cancelar edição</button></div>' +
          '</form>' +
        '</section>' +
        '<section class="dor-panel dor-telegram-panel"><div class="dor-panel-title"><div><h2>Conectar Telegram</h2><p>O bot publicará no seu canal quando uma oferta cumprir as regras.</p></div><span class="dor-telegram-icon">➤</span></div>' +
          '<div id="dor-telegram-state" class="dor-telegram-state">Telegram ainda não conectado.</div>' +
          '<form id="dor-telegram-form">' +
            '<div class="dor-field"><label for="dor-bot-token">Token do bot (BotFather)</label><input id="dor-bot-token" type="password" autocomplete="new-password" placeholder="Cole o token do bot" required></div>' +
            '<div class="dor-field"><label for="dor-channel">Canal público do Telegram</label><input id="dor-channel" maxlength="80" placeholder="@meucanaldeofertas" required></div>' +
            '<div class="dor-telegram-note">Adicione o bot ao canal como administrador e permita publicar mensagens. O token é criptografado no servidor e não é exibido novamente.</div>' +
            '<div class="dor-actions"><button type="submit" class="dor-btn primary" id="dor-connect">Conectar canal</button><button type="button" class="dor-btn" id="dor-test-telegram" disabled>Enviar teste</button><button type="button" class="dor-btn danger" id="dor-disconnect" hidden>Desconectar</button></div>' +
          '</form>' +
        '</section>' +
      '</div>' +
      '<section class="dor-section"><div class="dor-section-head"><div><h2>Meus monitoramentos</h2><p>Configure o modo automático ou a aprovação individualmente em cada monitor.</p></div><button type="button" class="dor-btn" id="dor-refresh">↻ Atualizar</button></div><div class="dor-monitor-list" id="dor-monitors"><div class="dor-empty">Carregando monitoramentos...</div></div></section>' +
      '<section class="dor-section dor-opportunities-section" id="dor-opportunities-section" hidden><div class="dor-section-head"><div><h2 id="dor-opportunities-title">Oportunidades encontradas</h2><p>Cadastre o link de afiliado do produto para habilitar a publicação.</p></div><button type="button" class="dor-btn" id="dor-reload-opportunities">Atualizar oportunidades</button></div><div class="dor-affiliate-explainer">No Mercado Livre, gere o link pelo Portal ou pela Barra de Afiliados e cole aqui. O Resolvei não inventa nem transforma links comuns em links de afiliado.</div><div id="dor-opportunities" class="dor-opportunities"><div class="dor-empty">Selecione um monitoramento para ver as oportunidades.</div></div></section>' +
      '<footer class="dor-footnote">Os descontos são calculados a partir do preço anterior observado pelo Radar ou do preço de referência informado pela fonte, quando disponível. Preço, frete, vendedor, cupom e disponibilidade devem ser conferidos na página da loja antes de compartilhar.</footer>' +
    '</div>';
}
function monitorPayload() {
  var keywords = document.getElementById("dor-keywords").value.split(/[\n,;]+/).map(function (x) { return x.trim(); }).filter(Boolean);
  return {
    title: document.getElementById("dor-title").value.trim(),
    store: document.getElementById("dor-store").value,
    keywords: keywords,
    min_discount_percent: Number(document.getElementById("dor-discount").value || 0),
    max_price: document.getElementById("dor-max-price").value.trim() ? Number(document.getElementById("dor-max-price").value) : null,
    interval_minutes: Number(document.getElementById("dor-interval").value || 30),
    publish_mode: document.getElementById("dor-mode").value,
    active: true
  };
}
function resetMonitorForm() {
  editingId = "";
  document.getElementById("dor-monitor-form").reset();
  document.getElementById("dor-discount").value = "10";
  document.getElementById("dor-interval").value = "30";
  document.getElementById("dor-mode").value = "approval";
  document.getElementById("dor-form-title").textContent = "Criar monitoramento";
  document.getElementById("dor-save-monitor").textContent = "＋ Criar monitoramento";
  document.getElementById("dor-cancel-edit").hidden = true;
  updateModeHelp();
}
function updateModeHelp() {
  var el = document.getElementById("dor-mode-help");
  if (!el) return;
  el.textContent = document.getElementById("dor-mode").value === "automatic"
    ? "Quando uma oferta cumprir os critérios e tiver link de afiliado cadastrado, o Resolvei publicará automaticamente no Telegram."
    : "As oportunidades ficam numa fila. Você revisa o preço, salva o link de afiliado e decide quando publicar.";
}
function fillMonitorForm(m) {
  editingId = m.id;
  document.getElementById("dor-title").value = m.title || "";
  document.getElementById("dor-store").value = m.store || "mercado_livre";
  document.getElementById("dor-keywords").value = (m.keywords || []).join("\n");
  document.getElementById("dor-discount").value = m.minDiscountPercent == null ? 10 : m.minDiscountPercent;
  document.getElementById("dor-max-price").value = m.maxPrice == null ? "" : m.maxPrice;
  document.getElementById("dor-interval").value = String(m.intervalMinutes || 30);
  document.getElementById("dor-mode").value = m.publishMode || "approval";
  document.getElementById("dor-form-title").textContent = "Editar monitoramento";
  document.getElementById("dor-save-monitor").textContent = "Salvar alterações";
  document.getElementById("dor-cancel-edit").hidden = false;
  updateModeHelp();
  document.getElementById("dor-title").focus();
}
function stateLabel(m) {
  var s = m.lastScanSummary || {};
  if (m.active === false) return "Pausado";
  if (m.lastScanError) return "Atenção na última pesquisa";
  if (m.publishMode === "automatic") return "Publicação automática";
  return "Aprovação manual";
}
function renderOverview() {
  var el = document.getElementById("dor-overview");
  if (!el) return;
  var active = monitors.filter(function (m) { return m.active !== false; }).length;
  var count = monitors.reduce(function (n, m) { return n + Number((m.lastScanSummary || {}).resultsFound || 0); }, 0);
  var queued = monitors.reduce(function (n, m) { return n + Number((m.lastScanSummary || {}).pendingApproval || 0); }, 0);
  var published = monitors.reduce(function (n, m) { return n + Number((m.lastScanSummary || {}).published || 0); }, 0);
  el.innerHTML =
    '<div class="dor-stat"><span>Monitoramentos ativos</span><strong>' + active + '</strong></div>' +
    '<div class="dor-stat"><span>Produtos encontrados na última pesquisa</span><strong>' + count + '</strong></div>' +
    '<div class="dor-stat"><span>Aguardando aprovação</span><strong>' + queued + '</strong></div>' +
    '<div class="dor-stat"><span>Publicações na última pesquisa</span><strong>' + published + '</strong></div>';
}
function renderMonitors() {
  var el = document.getElementById("dor-monitors");
  if (!el) return;
  if (!monitors.length) { el.innerHTML = '<div class="dor-empty"><b>Nenhum monitoramento criado.</b>Crie seu primeiro radar ao lado para começar a encontrar oportunidades.</div>'; renderOverview(); return; }
  el.innerHTML = monitors.map(function (m) {
    var summary = m.lastScanSummary || {};
    var active = m.active !== false;
    var mode = m.publishMode === "automatic" ? "Automático" : "Com aprovação";
    return '<article class="dor-monitor-card ' + (selectedMonitorId === m.id ? "selected" : "") + '">' +
      '<div class="dor-monitor-top"><div><h3>' + esc(m.title || "Monitoramento") + '</h3><p>' + esc((m.storeLabel || m.store || "").replace(/_/g, " ")) + ' · ' + esc((m.keywords || []).join(" · ")) + '</p></div><span class="dor-mode ' + (m.publishMode === "automatic" ? "automatic" : "") + '">' + mode + '</span></div>' +
      '<div class="dor-monitor-meta"><span>' + Number(m.minDiscountPercent || 0).toLocaleString("pt-BR") + '% desconto mínimo</span><span>' + (m.maxPrice != null ? "Até " + money(m.maxPrice) : "Sem teto de preço") + '</span><span>A cada ' + Number(m.intervalMinutes || 30) + ' min</span></div>' +
      '<div class="dor-monitor-last">' + (summary.resultsFound != null ? Number(summary.resultsFound) + ' resultado(s) · ' + dt(m.lastScanAt) : "Aguardando primeira pesquisa") + (m.lastScanError ? ' · <span class="error">' + esc(m.lastScanError) + '</span>' : "") + '</div>' +
      '<div class="dor-monitor-actions"><button class="dor-btn primary" data-dor-scan="' + esc(m.id) + '" ' + (!active ? "disabled" : "") + '>↻ Pesquisar agora</button><button class="dor-btn" data-dor-view="' + esc(m.id) + '">Ver oportunidades</button><button class="dor-btn" data-dor-edit="' + esc(m.id) + '">Editar</button><button class="dor-btn" data-dor-toggle="' + esc(m.id) + '">' + (active ? "Pausar" : "Ativar") + '</button><button class="dor-btn danger" data-dor-delete="' + esc(m.id) + '">Excluir</button></div>' +
      '</article>';
  }).join("");
  renderOverview();
}
function loadMonitors() {
  return api("/monitors").then(function (data) {
    monitors = data.monitors || [];
    renderMonitors();
    if (selectedMonitorId && !monitors.some(function (m) { return m.id === selectedMonitorId; })) selectedMonitorId = "";
    return monitors;
  });
}
function loadTelegram() {
  return api("/telegram").then(function (data) {
    var connected = !!data.connected;
    document.getElementById("dor-channel").value = data.channelUsername || "";
    document.getElementById("dor-telegram-state").innerHTML = connected
      ? '<b class="ok">Conectado</b> · Bot @' + esc(String(data.botUsername || "").replace(/^@/, "")) + ' · Canal ' + esc(data.channelUsername || "")
      : 'Telegram ainda não conectado. Crie um bot no <b>@BotFather</b> e informe o canal público.';
    document.getElementById("dor-test-telegram").disabled = !connected;
    document.getElementById("dor-disconnect").hidden = !connected;
    document.getElementById("dor-connect").textContent = connected ? "Atualizar conexão" : "Conectar canal";
    document.getElementById("dor-status-text").textContent = connected ? "Telegram conectado" : "Radar pronto";
  });
}
function loadOpportunities(monitorId) {
  selectedMonitorId = monitorId;
  var section = document.getElementById("dor-opportunities-section");
  var box = document.getElementById("dor-opportunities");
  var monitor = monitors.find(function (m) { return m.id === monitorId; });
  if (!section || !box || !monitor) return Promise.resolve();
  section.hidden = false;
  document.getElementById("dor-opportunities-title").textContent = "Oportunidades · " + monitor.title;
  box.innerHTML = '<div class="dor-empty">Carregando oportunidades...</div>';
  return api("/monitors/" + encodeURIComponent(monitorId) + "/opportunities").then(function (data) {
    renderOpportunities(data.opportunities || [], monitor);
    document.querySelectorAll(".dor-monitor-card").forEach(function (card) { card.classList.toggle("selected", card.querySelector("[data-dor-view]") && card.querySelector("[data-dor-view]").getAttribute("data-dor-view") === monitorId); });
  }).catch(function (e) { box.innerHTML = '<div class="dor-empty error">' + esc(e.message) + '</div>'; });
}
function statusText(o) {
  var map = {
    watching: "Monitorando preço",
    awaiting_affiliate_link: "Aguardando link de afiliado",
    ready_to_publish: "Pronta para publicação",
    pending_approval: "Aguardando sua aprovação",
    published: "Publicada",
    publish_error: "Falha ao publicar",
    ignored: "Ignorada"
  };
  return map[o.status] || "Oportunidade encontrada";
}
function renderOpportunities(items, monitor) {
  var box = document.getElementById("dor-opportunities");
  if (!box) return;
  items.sort(function (a, b) { return String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")); });
  if (!items.length) { box.innerHTML = '<div class="dor-empty"><b>Nenhuma oportunidade encontrada até agora.</b>Execute uma pesquisa ou aguarde o próximo ciclo.</div>'; return; }
  box.innerHTML = items.map(function (o) {
    var price = o.currentPrice == null ? "—" : money(o.currentPrice);
    var image = o.image_url ? '<img src="' + esc(o.image_url) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : '<div class="dor-product-placeholder">🛍️</div>';
    var discount = o.discountPercent != null ? '<span class="dor-discount">' + Number(o.discountPercent).toLocaleString("pt-BR") + '% OFF</span>' : "";
    var old = o.originalPrice != null && Number(o.originalPrice) > Number(o.currentPrice) ? '<del>' + money(o.originalPrice) + '</del>' : "";
    var affiliate = o.affiliateUrl || "";
    var isManual = monitor.publishMode !== "automatic";
    var approve = isManual && o.eligible && o.status !== "published" && o.status !== "ignored"
      ? '<button class="dor-btn primary" data-dor-approve="' + esc(o.id) + '">Aprovar e publicar</button>' : "";
    var ignore = o.status !== "published" && o.status !== "ignored" ? '<button class="dor-btn danger" data-dor-ignore="' + esc(o.id) + '">Ignorar</button>' : "";
    var error = o.lastPublishError ? '<div class="dor-inline-error">' + esc(o.lastPublishError) + '</div>' : "";
    var note = o.eligible ? "Atende aos critérios deste monitor." : "Ainda não atende aos critérios configurados.";
    return '<article class="dor-offer-card"><div class="dor-offer-main">' + image + '<div class="dor-offer-info"><h3>' + esc(o.title || "Produto sem título") + '</h3><p>' + esc(o.source || monitor.storeLabel || "") + ' · <a href="' + esc(o.url || "#") + '" target="_blank" rel="noopener noreferrer">Ver anúncio original ↗</a></p><span class="dor-offer-status">' + esc(statusText(o)) + '</span></div></div>' +
      '<div class="dor-offer-prices"><div><span>Preço atual</span><strong>' + price + '</strong></div><div>' + old + discount + '</div></div>' +
      '<p class="dor-offer-note">' + note + (o.lastSentAt ? " · Publicada em " + dt(o.lastSentAt) : "") + '</p>' +
      '<div class="dor-affiliate-row"><label for="dor-aff-' + esc(o.id) + '">Seu link de afiliado</label><input id="dor-aff-' + esc(o.id) + '" type="url" maxlength="2048" placeholder="Cole o link gerado no Portal de Afiliados" value="' + esc(affiliate) + '"><button class="dor-btn" data-dor-affiliate="' + esc(o.id) + '">Salvar link</button></div>' +
      error + '<div class="dor-offer-actions">' + approve + ignore + (o.lastSentPrice != null ? '<span class="dor-last-published">Última publicação: ' + money(o.lastSentPrice) + '</span>' : "") + '</div></article>';
  }).join("");
}
function saveAffiliate(id) {
  var field = document.getElementById("dor-aff-" + id);
  if (!field) return;
  api("/monitors/" + encodeURIComponent(selectedMonitorId) + "/opportunities/" + encodeURIComponent(id) + "/affiliate", {
    method: "POST", body: JSON.stringify({ affiliate_url: field.value.trim() })
  }).then(function (r) {
    notice(r.published ? "Link salvo e oferta publicada automaticamente no Telegram." : "Link de afiliado salvo para esta oportunidade.", "success");
    return loadOpportunities(selectedMonitorId).then(loadMonitors);
  }).catch(function (e) { notice(e.message, "error"); });
}
function scanMonitor(id) {
  var m = monitors.find(function (x) { return x.id === id; });
  if (!m) return;
  notice("Pesquisando ofertas de " + (m.storeLabel || m.store) + ". A consulta pode levar alguns segundos.");
  var button = document.querySelector('[data-dor-scan="' + id + '"]');
  if (button) { button.disabled = true; button.textContent = "Pesquisando..."; }
  api("/monitors/" + encodeURIComponent(id) + "/scan", { method: "POST" }).then(function (result) {
    notice("Pesquisa concluída: " + result.resultsFound + " resultado(s), " + result.eligibleOffers + " oportunidade(s) dentro dos critérios e " + result.published + " publicação(ões).", "success");
    return loadMonitors().then(function () { return loadOpportunities(id); });
  }).catch(function (e) { notice(e.message, "error"); return loadMonitors(); }).finally(function () {
    var b = document.querySelector('[data-dor-scan="' + id + '"]');
    if (b) { b.disabled = false; b.textContent = "↻ Pesquisar agora"; }
  });
}
function toggleMonitor(id) {
  var m = monitors.find(function (x) { return x.id === id; });
  if (!m) return;
  var body = {
    title:m.title, store:m.store, keywords:m.keywords || [],
    min_discount_percent:Number(m.minDiscountPercent || 0), max_price:m.maxPrice == null ? null : Number(m.maxPrice),
    interval_minutes:Number(m.intervalMinutes || 30), publish_mode:m.publishMode || "approval", active:m.active === false
  };
  api("/monitors/" + encodeURIComponent(id), { method:"PUT", body:JSON.stringify(body) }).then(function () {
    notice(body.active ? "Monitoramento ativado." : "Monitoramento pausado.", "success");
    return loadMonitors();
  }).catch(function (e) { notice(e.message, "error"); });
}
function deleteMonitor(id) {
  var m = monitors.find(function (x) { return x.id === id; });
  if (!m || !window.confirm("Excluir o monitoramento “" + m.title + "” e as oportunidades associadas?")) return;
  api("/monitors/" + encodeURIComponent(id), { method:"DELETE" }).then(function () {
    if (selectedMonitorId === id) { selectedMonitorId = ""; document.getElementById("dor-opportunities-section").hidden = true; }
    notice("Monitoramento excluído.", "success");
    return loadMonitors();
  }).catch(function (e) { notice(e.message, "error"); });
}
function connectTelegram(e) {
  e.preventDefault();
  var token = document.getElementById("dor-bot-token").value.trim();
  var channel = document.getElementById("dor-channel").value.trim();
  var button = document.getElementById("dor-connect");
  if (!token || !channel) return notice("Informe o token do bot e o canal público.", "error");
  button.disabled = true;
  api("/telegram/connect", { method:"POST", body:JSON.stringify({ bot_token:token, channel_username:channel }) }).then(function () {
    document.getElementById("dor-bot-token").value = "";
    notice("Telegram conectado. O bot foi validado no canal.", "success");
    return loadTelegram();
  }).catch(function (err) { notice(err.message, "error"); }).finally(function () { button.disabled = false; });
}
function bind() {
  document.getElementById("dor-monitor-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var data = monitorPayload();
    if (!data.title || !data.keywords.length) return notice("Informe um nome e pelo menos uma palavra-chave.", "error");
    var path = editingId ? "/monitors/" + encodeURIComponent(editingId) : "/monitors";
    var method = editingId ? "PUT" : "POST";
    var button = document.getElementById("dor-save-monitor");
    button.disabled = true;
    api(path, { method:method, body:JSON.stringify(data) }).then(function (result) {
      var id = (result.monitor || {}).id || editingId;
      resetMonitorForm();
      notice(editingId ? "Monitoramento atualizado." : "Monitoramento criado.", "success");
      return loadMonitors().then(function () { if (id) return loadOpportunities(id); });
    }).catch(function (err) { notice(err.message, "error"); }).finally(function () { button.disabled = false; });
  });
  document.getElementById("dor-cancel-edit").addEventListener("click", resetMonitorForm);
  document.getElementById("dor-mode").addEventListener("change", updateModeHelp);
  document.getElementById("dor-telegram-form").addEventListener("submit", connectTelegram);
  document.getElementById("dor-test-telegram").addEventListener("click", function () {
    api("/telegram/test", { method:"POST" }).then(function () { notice("Mensagem de teste enviada ao canal.", "success"); }).catch(function (e) { notice(e.message, "error"); });
  });
  document.getElementById("dor-disconnect").addEventListener("click", function () {
    if (!window.confirm("Desconectar o bot deste canal?")) return;
    api("/telegram", { method:"DELETE" }).then(function () { notice("Telegram desconectado.", "success"); return loadTelegram(); }).catch(function (e) { notice(e.message, "error"); });
  });
  document.getElementById("dor-refresh").addEventListener("click", function () { loadMonitors().then(function () { notice("Monitoramentos atualizados.", "success"); }).catch(function (e) { notice(e.message, "error"); }); });
  document.getElementById("dor-reload-opportunities").addEventListener("click", function () { if (selectedMonitorId) loadOpportunities(selectedMonitorId); });
  document.getElementById("dor-monitors").addEventListener("click", function (e) {
    var scan = e.target.closest("[data-dor-scan]"), view = e.target.closest("[data-dor-view]");
    var edit = e.target.closest("[data-dor-edit]"), toggle = e.target.closest("[data-dor-toggle]"), del = e.target.closest("[data-dor-delete]");
    if (scan) scanMonitor(scan.getAttribute("data-dor-scan"));
    if (view) loadOpportunities(view.getAttribute("data-dor-view"));
    if (edit) { var m = monitors.find(function (x) { return x.id === edit.getAttribute("data-dor-edit"); }); if (m) fillMonitorForm(m); }
    if (toggle) toggleMonitor(toggle.getAttribute("data-dor-toggle"));
    if (del) deleteMonitor(del.getAttribute("data-dor-delete"));
  });
  document.getElementById("dor-opportunities").addEventListener("click", function (e) {
    var affiliate = e.target.closest("[data-dor-affiliate]"), approve = e.target.closest("[data-dor-approve]"), ignore = e.target.closest("[data-dor-ignore]");
    if (affiliate) saveAffiliate(affiliate.getAttribute("data-dor-affiliate"));
    if (approve) {
      var id = approve.getAttribute("data-dor-approve");
      api("/monitors/" + encodeURIComponent(selectedMonitorId) + "/opportunities/" + encodeURIComponent(id) + "/approve", { method:"POST" })
        .then(function () { notice("Oferta aprovada e publicada no Telegram.", "success"); return loadOpportunities(selectedMonitorId).then(loadMonitors); })
        .catch(function (err) { notice(err.message, "error"); });
    }
    if (ignore) {
      var ignored = ignore.getAttribute("data-dor-ignore");
      api("/monitors/" + encodeURIComponent(selectedMonitorId) + "/opportunities/" + encodeURIComponent(ignored) + "/ignore", { method:"POST" })
        .then(function () { notice("Oportunidade ignorada.", "success"); return loadOpportunities(selectedMonitorId); })
        .catch(function (err) { notice(err.message, "error"); });
    }
  });
}
function init() {
  host = document.getElementById("dealRadarToolHost");
  if (!host || host.dataset.initialized === "1") return;
  host.dataset.initialized = "1";
  shell();
  bind();
  updateModeHelp();
  Promise.all([loadMonitors(), loadTelegram()]).then(function () { notice("Radar de Ofertas pronto. Crie um monitoramento ou execute uma pesquisa.", "success"); }).catch(function (e) {
    notice(e.message, "error");
    document.getElementById("dor-status-text").textContent = "Faça login para começar";
  });
}
window.resolveiRadarOfertasInit = init;
})();