(function () {
"use strict";
var host = null, monitors = [], selectedMonitorId = "", editingId = "", allOpportunityRows = [], queueFilter = "all", activeMonitorFilter = "all", noticeTimer = null;
var brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
function esc(v) { return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) { return ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" })[c]; }); }
function money(v) { return v == null || !Number.isFinite(Number(v)) ? "—" : brl.format(Number(v)); }
function dt(v) { if (!v) return "Ainda não verificado"; var d = new Date(v); return Number.isNaN(d.getTime()) ? "Data indisponível" : d.toLocaleString("pt-BR", { dateStyle:"short", timeStyle:"short" }); }
function notice(message, type) { var el = document.getElementById("dor-notice"); if (!el) return; el.textContent = message; el.className = "dor-notice" + (type ? " " + type : ""); el.hidden = false; if (noticeTimer) window.clearTimeout(noticeTimer); noticeTimer = window.setTimeout(function () { el.hidden = true; }, 6500); }
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
    '<div class="dor-page dor-admin-page">' +
      '<header class="dor-hero">' +
        '<div class="dor-hero-copy"><div class="dor-eyebrow">RESOLVEI · COMPRAS INTELIGENTES</div><h1>Central de Ofertas</h1><p>Gerencie seus monitoramentos, revise oportunidades e controle o que será publicado no Telegram.</p></div>' +
        '<div class="dor-hero-actions"><div class="dor-status"><span></span><b id="dor-status-text">Verificando Telegram</b></div><button type="button" class="dor-btn primary" id="dor-open-monitor">＋ Novo monitoramento</button><button type="button" class="dor-btn" id="dor-refresh-all">↻ Atualizar painel</button></div>' +
      '</header>' +
      '<div id="dor-notice" class="dor-notice" role="status" hidden></div>' +
      '<div class="dor-overview" id="dor-overview"></div>' +
      '<section class="dor-section dor-queue-section">' +
        '<div class="dor-section-head"><div><span class="dor-section-kicker">PUBLICAÇÃO</span><h2>Fila de ofertas</h2><p>Revise os produtos encontrados, cadastre seus links de afiliado e publique com segurança.</p></div><button type="button" class="dor-btn" id="dor-reload-opportunities">↻ Atualizar ofertas</button></div>' +
        '<div class="dor-queue-toolbar"><div class="dor-filter-tabs" id="dor-filter-tabs" role="tablist" aria-label="Filtrar ofertas">' +
          '<button type="button" class="active" data-dor-filter="all">Todas <b data-count="all">0</b></button>' +
          '<button type="button" data-dor-filter="pending">Para aprovar <b data-count="pending">0</b></button>' +
          '<button type="button" data-dor-filter="affiliate">Sem link <b data-count="affiliate">0</b></button>' +
          '<button type="button" data-dor-filter="published">Publicadas <b data-count="published">0</b></button>' +
          '<button type="button" data-dor-filter="errors">Com erro <b data-count="errors">0</b></button>' +
          '<button type="button" data-dor-filter="ignored">Ignoradas <b data-count="ignored">0</b></button>' +
        '</div><label class="dor-monitor-filter-wrap"><span>Monitoramento</span><select id="dor-monitor-filter"><option value="all">Todos os monitoramentos</option></select></label></div>' +
        '<div id="dor-opportunities" class="dor-opportunities"><div class="dor-empty">Carregando ofertas...</div></div>' +
      '</section>' +
      '<section class="dor-section dor-management-section">' +
        '<div class="dor-section-head"><div><span class="dor-section-kicker">AUTOMAÇÃO</span><h2>Seus monitoramentos</h2><p>Defina loja, palavras-chave, regras de preço e frequência de pesquisa.</p></div><button type="button" class="dor-btn" id="dor-refresh">↻ Atualizar</button></div>' +
        '<div class="dor-monitor-list" id="dor-monitors"><div class="dor-empty">Carregando monitoramentos...</div></div>' +
        '<details class="dor-config-panel" id="dor-monitor-form-panel"><summary><span class="dor-summary-icon">＋</span><span><b id="dor-form-title">Criar monitoramento</b><small>Configure uma nova busca de ofertas ou edite uma existente</small></span><span class="dor-summary-chevron">⌄</span></summary>' +
          '<form id="dor-monitor-form">' +
            '<div class="dor-form-grid">' +
              '<div class="dor-field"><label for="dor-title">Nome do monitoramento</label><input id="dor-title" maxlength="100" required placeholder="Ex.: Consoles e acessórios"></div>' +
              '<div class="dor-field"><label for="dor-store">Loja específica</label><select id="dor-store"><option value="mercado_livre">Mercado Livre</option><option value="amazon">Amazon</option><option value="shopee">Shopee</option><option value="magalu">Magazine Luiza</option></select><small>Os resultados serão filtrados para a loja escolhida.</small></div>' +
              '<div class="dor-field dor-field-wide"><label for="dor-keywords">Palavras-chave (até 5)</label><textarea id="dor-keywords" rows="3" required placeholder="console playstation 5&#10;controle dualsense&#10;playstation 5 slim"></textarea><small>Uma por linha ou separadas por vírgula. Cada palavra-chave gera uma consulta e consome cota da SerpApi.</small></div>' +
              '<div class="dor-field"><label for="dor-discount">Desconto mínimo (%)</label><input id="dor-discount" type="number" min="0" max="90" step="0.5" value="10"></div>' +
              '<div class="dor-field"><label for="dor-max-price">Preço máximo (R$)</label><input id="dor-max-price" type="number" min="0.01" step="0.01" placeholder="Sem limite"></div>' +
              '<div class="dor-field"><label for="dor-interval">Pesquisar a cada</label><select id="dor-interval"><option value="15">15 minutos</option><option value="30">30 minutos</option><option value="60" selected>1 hora</option><option value="180">3 horas</option><option value="360">6 horas</option></select></div>' +
              '<div class="dor-field"><label for="dor-mode">Modo de publicação</label><select id="dor-mode"><option value="approval">Com aprovação</option><option value="automatic">Automático</option></select></div>' +
            '</div>' +
            '<div class="dor-mode-help" id="dor-mode-help">As ofertas elegíveis aguardam sua aprovação e o link de afiliado.</div>' +
            '<div class="dor-actions"><button type="submit" class="dor-btn primary" id="dor-save-monitor">＋ Criar monitoramento</button><button type="button" class="dor-btn" id="dor-cancel-edit" hidden>Cancelar edição</button></div>' +
          '</form>' +
        '</details>' +
      '</section>' +
      '<section class="dor-section dor-telegram-section">' +
        '<details class="dor-config-panel" id="dor-telegram-settings">' +
          '<summary><span class="dor-summary-icon telegram">➤</span><span><b>Configuração do Telegram</b><small id="dor-telegram-summary">Confira o canal conectado e as permissões de publicação</small></span><span class="dor-summary-chevron">⌄</span></summary>' +
          '<div class="dor-telegram-content"><div id="dor-telegram-state" class="dor-telegram-state">Telegram ainda não conectado.</div>' +
            '<form id="dor-telegram-form"><div class="dor-form-grid">' +
              '<div class="dor-field"><label for="dor-bot-token">Token do bot (BotFather)</label><input id="dor-bot-token" type="password" autocomplete="new-password" placeholder="Cole o token para conectar ou atualizar" required></div>' +
              '<div class="dor-field"><label for="dor-channel">Canal público do Telegram</label><input id="dor-channel" maxlength="80" placeholder="@ResolveiOfertas ou -1001234567890" required></div>' +
            '</div>' +
            '<div class="dor-telegram-note">O bot precisa ser administrador com permissão para publicar mensagens. Ao conectar, será enviada uma confirmação ao canal. O token é criptografado no servidor e nunca é exibido novamente.</div>' +
            '<div class="dor-actions"><button type="submit" class="dor-btn primary" id="dor-connect">Conectar canal</button><button type="button" class="dor-btn" id="dor-test-telegram" disabled>Enviar teste</button><button type="button" class="dor-btn danger" id="dor-disconnect" hidden>Desconectar</button></div></form>' +
          '</div>' +
        '</details>' +
      '</section>' +
      '<footer class="dor-footnote">Antes de compartilhar, confira preço, frete, vendedor, cupom e disponibilidade na página da loja. Os descontos são estimativas calculadas com base nos preços observados pelo Radar ou informados pela fonte.</footer>' +
    '</div>';
}
function numericField(id, fallback) {
  var raw = String(document.getElementById(id).value || "").trim().replace(/\s/g, "");
  if (!raw) return fallback;
  if (raw.indexOf(",") >= 0) raw = raw.replace(/\./g, "").replace(",", ".");
  var value = Number(raw);
  return Number.isFinite(value) ? value : NaN;
}
function monitorPayload() {
  var keywords = document.getElementById("dor-keywords").value.split(/[\n,;]+/).map(function (x) { return x.trim(); }).filter(Boolean);
  return {
    title: document.getElementById("dor-title").value.trim(),
    store: document.getElementById("dor-store").value,
    keywords: keywords,
    min_discount_percent: numericField("dor-discount", 0),
    max_price: numericField("dor-max-price", null),
    interval_minutes: Number(document.getElementById("dor-interval").value || 30),
    publish_mode: document.getElementById("dor-mode").value,
    active: true
  };
}
function resetMonitorForm() {
  editingId = "";
  document.getElementById("dor-monitor-form").reset();
  document.getElementById("dor-discount").value = "10";
  document.getElementById("dor-interval").value = "60";
  document.getElementById("dor-mode").value = "approval";
  document.getElementById("dor-form-title").textContent = "Criar monitoramento";
  var panel = document.getElementById("dor-monitor-form-panel"); if (panel) panel.open = false;
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
  var panel = document.getElementById("dor-monitor-form-panel"); if (panel) { panel.open = true; panel.scrollIntoView({ behavior: "smooth", block: "center" }); }
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
function offerGroup(item) {
  if (item.status === "ignored") return "ignored";
  if (item.status === "published") return "published";
  if (item.status === "publish_error") return "errors";
  if (item.status === "awaiting_affiliate_link" || (item.eligible && item.publishMode === "automatic" && !item.affiliateUrl)) return "affiliate";
  if (item.eligible && item.publishMode !== "automatic" && item.status !== "published") return "pending";
  return "all";
}
function renderOverview() {
  var el = document.getElementById("dor-overview");
  if (!el) return;
  var active = monitors.filter(function (m) { return m.active !== false; }).length;
  var pending = allOpportunityRows.filter(function (o) { return offerGroup(o) === "pending"; }).length;
  var affiliate = allOpportunityRows.filter(function (o) { return offerGroup(o) === "affiliate"; }).length;
  var published = allOpportunityRows.filter(function (o) { return o.status === "published"; }).length;
  el.innerHTML =
    '<div class="dor-stat"><span>Monitoramentos ativos</span><strong>' + active + '</strong><small>Buscas em funcionamento</small></div>' +
    '<div class="dor-stat"><span>Ofertas para aprovar</span><strong>' + pending + '</strong><small>Elegíveis no modo manual</small></div>' +
    '<div class="dor-stat"><span>Aguardando link</span><strong>' + affiliate + '</strong><small>Precisam do seu link de afiliado</small></div>' +
    '<div class="dor-stat"><span>Publicações realizadas</span><strong>' + published + '</strong><small>Ofertas enviadas ao canal</small></div>';
}
function renderFilterCounts() {
  var counts = {
    all: allOpportunityRows.length,
    pending: allOpportunityRows.filter(function (o) { return offerGroup(o) === "pending"; }).length,
    affiliate: allOpportunityRows.filter(function (o) { return offerGroup(o) === "affiliate"; }).length,
    published: allOpportunityRows.filter(function (o) { return o.status === "published"; }).length,
    errors: allOpportunityRows.filter(function (o) { return o.status === "publish_error"; }).length,
    ignored: allOpportunityRows.filter(function (o) { return o.status === "ignored"; }).length
  };
  Object.keys(counts).forEach(function (key) {
    var node = document.querySelector('[data-count="' + key + '"]');
    if (node) node.textContent = counts[key];
  });
  document.querySelectorAll("[data-dor-filter]").forEach(function (button) {
    button.classList.toggle("active", button.getAttribute("data-dor-filter") === queueFilter);
  });
}
function renderMonitorFilter() {
  var select = document.getElementById("dor-monitor-filter");
  if (!select) return;
  var current = activeMonitorFilter;
  select.innerHTML = '<option value="all">Todos os monitoramentos</option>' + monitors.map(function (m) {
    return '<option value="' + esc(m.id) + '">' + esc(m.title || m.storeLabel || "Monitoramento") + '</option>';
  }).join("");
  select.value = monitors.some(function (m) { return m.id === current; }) ? current : "all";
  activeMonitorFilter = select.value;
}
function filteredOffers() {
  return allOpportunityRows.filter(function (o) {
    if (activeMonitorFilter !== "all" && o.monitorId !== activeMonitorFilter) return false;
    if (queueFilter === "all") return true;
    if (queueFilter === "pending" || queueFilter === "affiliate") return offerGroup(o) === queueFilter;
    return o.status === (queueFilter === "published" ? "published" : queueFilter === "errors" ? "publish_error" : "ignored");
  }).sort(function (a,b) { return String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")); });
}
function loadMonitors() {
  return api("/monitors").then(function (data) {
    monitors = data.monitors || [];
    renderMonitors();
    renderMonitorFilter();
    renderOverview();
    return monitors;
  });
}
function renderMonitors() {
  var el = document.getElementById("dor-monitors");
  if (!el) return;
  if (!monitors.length) {
    el.innerHTML = '<div class="dor-empty"><b>Nenhum monitoramento cadastrado.</b>Crie seu primeiro monitor para começar a encontrar ofertas.</div>';
    renderOverview();
    return;
  }
  el.innerHTML = monitors.map(function (m) {
    var summary = m.lastScanSummary || {};
    var active = m.active !== false;
    var automatic = m.publishMode === "automatic";
    var resultCount = Number(summary.resultsFound || 0);
    return '<article class="dor-monitor-card">' +
      '<div class="dor-monitor-top"><div><div class="dor-monitor-store">' + esc(m.storeLabel || m.store || "") + '</div><h3>' + esc(m.title || "Monitoramento") + '</h3><p>' + esc((m.keywords || []).join(" · ")) + '</p></div><span class="dor-mode ' + (automatic ? "automatic" : "") + '">' + (automatic ? "Automático" : "Com aprovação") + '</span></div>' +
      '<div class="dor-monitor-meta"><span>' + Number(m.minDiscountPercent || 0).toLocaleString("pt-BR") + '% desconto mínimo</span><span>' + (m.maxPrice != null ? "Até " + money(m.maxPrice) : "Sem teto de preço") + '</span><span>A cada ' + Number(m.intervalMinutes || 30) + ' min</span></div>' +
      '<div class="dor-monitor-last"><b>' + (active ? "Ativo" : "Pausado") + '</b> · ' + (summary.resultsFound != null ? resultCount + ' produto(s) na última busca · ' + dt(m.lastScanAt) : "Aguardando primeira pesquisa") + (m.lastScanError ? ' · <span class="error">' + esc(m.lastScanError) + '</span>' : "") + '</div>' +
      '<div class="dor-monitor-actions"><button class="dor-btn primary" data-dor-scan="' + esc(m.id) + '" ' + (!active ? "disabled" : "") + '>↻ Pesquisar agora</button><button class="dor-btn" data-dor-view="' + esc(m.id) + '">Ver ofertas</button><button class="dor-btn" data-dor-edit="' + esc(m.id) + '">Editar regras</button><button class="dor-btn" data-dor-toggle="' + esc(m.id) + '">' + (active ? "Pausar" : "Ativar") + '</button><button class="dor-btn danger" data-dor-delete="' + esc(m.id) + '">Excluir</button></div>' +
      '</article>';
  }).join("");
  renderOverview();
}
function loadAllOpportunities() {
  var jobs = monitors.map(function (monitor) {
    return api("/monitors/" + encodeURIComponent(monitor.id) + "/opportunities").then(function (data) {
      return (data.opportunities || []).map(function (o) {
        return Object.assign({}, o, { monitorId: monitor.id, monitorTitle: monitor.title || "Monitoramento", storeLabel: monitor.storeLabel || monitor.store || "", publishMode: monitor.publishMode || "approval" });
      });
    }).catch(function (error) {
      notice("Não foi possível carregar as ofertas de " + (monitor.title || "um monitor") + ": " + error.message, "error");
      return [];
    });
  });
  return Promise.all(jobs).then(function (groups) {
    allOpportunityRows = [].concat.apply([], groups);
    renderMonitorFilter();
    renderOpportunities();
    renderOverview();
    return allOpportunityRows;
  });
}
function loadTelegram() {
  return api("/telegram").then(function (data) {
    var connected = !!data.connected;
    document.getElementById("dor-channel").value = data.channelUsername || "";
    document.getElementById("dor-telegram-state").innerHTML = connected
      ? '<b class="ok">Conectado</b> · Bot @' + esc(String(data.botUsername || "").replace(/^@/, "")) + ' · Canal ' + esc(data.channelTitle || data.channelUsername || "")
      : 'Telegram ainda não conectado. Crie um bot no <b>@BotFather</b> e informe o canal público.';
    document.getElementById("dor-test-telegram").disabled = !connected;
    document.getElementById("dor-disconnect").hidden = !connected;
    document.getElementById("dor-connect").textContent = connected ? "Atualizar conexão" : "Conectar canal";
    document.getElementById("dor-status-text").textContent = connected ? "Telegram conectado" : "Telegram não conectado";
    var summary = document.getElementById("dor-telegram-summary"); if (summary) summary.textContent = connected ? "Conectado ao canal " + (data.channelTitle || data.channelUsername || "") + " · Bot @" + (data.botUsername || "") : "Conecte um bot para publicar suas ofertas";
  });
}
function loadOpportunities(monitorId) {
  activeMonitorFilter = monitorId || "all";
  queueFilter = "all";
  var select = document.getElementById("dor-monitor-filter");
  if (select) select.value = activeMonitorFilter;
  renderFilterCounts();
  renderOpportunities();
  var section = document.querySelector(".dor-queue-section");
  if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
  return Promise.resolve();
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
function renderOpportunities() {
  var box = document.getElementById("dor-opportunities");
  if (!box) return;
  var items = filteredOffers();
  renderFilterCounts();
  if (!items.length) {
    var emptyTitle = allOpportunityRows.length ? "Nenhuma oferta nesta visualização." : "Ainda não há ofertas encontradas.";
    var emptyHelp = allOpportunityRows.length ? "Altere os filtros ou aguarde uma nova pesquisa dos monitoramentos." : "Execute uma pesquisa em um monitoramento ativo para preencher sua fila de ofertas.";
    box.innerHTML = '<div class="dor-empty"><b>' + emptyTitle + '</b>' + emptyHelp + '</div>';
    return;
  }
  box.innerHTML = items.map(function (o) {
    var price = o.currentPrice == null ? "—" : money(o.currentPrice);
    var image = o.image_url ? '<img src="' + esc(o.image_url) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : '<div class="dor-product-placeholder">🛍️</div>';
    var discount = o.discountPercent != null ? '<span class="dor-discount">' + Number(o.discountPercent).toLocaleString("pt-BR") + '% OFF</span>' : "";
    var old = o.originalPrice != null && Number(o.originalPrice) > Number(o.currentPrice) ? '<del>' + money(o.originalPrice) + '</del>' : "";
    var hasCoupon = !!(o.couponCode || o.couponInfo || (o.couponPrice && Number(o.couponPrice) < Number(o.listedPrice || o.currentPrice)));
    var couponMarkup = hasCoupon
      ? '<div class="dor-coupon-box"><span>🏷 ' + (o.couponCode ? 'CUPOM DISPONÍVEL' : 'CONDIÇÃO PROMOCIONAL') + '</span>' +
        (o.couponCode ? '<b>' + esc(o.couponCode) + '</b>' : '') +
        '<small>' + esc(o.couponInfo || 'Confira as condições e a elegibilidade do cupom na página da loja.') + '</small>' +
        (o.couponPrice && Number(o.couponPrice) < Number(o.listedPrice || o.currentPrice) ? '<strong>Preço com cupom: ' + money(o.couponPrice) + '</strong>' : '') +
        '</div>' : "";
    var offerConditions = [];
    if (o.freeShipping) offerConditions.push('<span>🚚 Frete grátis</span>');
    if (o.installmentText) offerConditions.push('<span>💳 ' + esc(o.installmentText) + '</span>');
    if (o.seller) offerConditions.push('<span>Vendedor: ' + esc(o.seller) + '</span>');
    var conditionsMarkup = offerConditions.length ? '<div class="dor-offer-details">' + offerConditions.join('') + '</div>' : "";
    var affiliate = o.affiliateUrl || "";
    var ignored = o.status === "ignored";
    var published = o.status === "published";
    var manual = o.publishMode !== "automatic";
    var canApprove = manual && !!o.eligible && !ignored && !published;
    var statusClass = ignored ? "ignored" : published ? "published" : o.status === "publish_error" ? "error" : o.eligible ? "eligible" : "watching";
    var statusLabel = statusText(o);
    var note = ignored
      ? "Esta oferta foi arquivada. Reative-a para voltar a avaliar os critérios e liberar as ações."
      : !o.eligible
        ? "Ainda não atende aos critérios deste monitor. O desconto mínimo ou o preço máximo pode não ter sido atingido."
        : manual && !affiliate
          ? "Oferta elegível. Cadastre seu link de afiliado para habilitar o botão de publicação."
          : manual
            ? "Oferta elegível e pronta para sua revisão. Confira o anúncio antes de publicar."
            : !affiliate
              ? "Oferta elegível, mas falta cadastrar o link de afiliado para o envio automático."
              : "Oferta elegível. O Resolvei fará a publicação conforme o próximo ciclo de pesquisa.";
    var affiliateRow = !ignored && !published
      ? '<div class="dor-affiliate-row"><label for="dor-aff-' + esc(o.monitorId) + '-' + esc(o.id) + '">Link de afiliado</label><input id="dor-aff-' + esc(o.monitorId) + '-' + esc(o.id) + '" type="url" maxlength="2048" placeholder="Cole aqui o link gerado no programa de afiliados" value="' + esc(affiliate) + '"><button class="dor-btn" data-dor-affiliate="' + esc(o.monitorId) + '" data-opportunity="' + esc(o.id) + '">Salvar link</button></div>'
      : published && affiliate
        ? '<div class="dor-published-link">Link de afiliado cadastrado para esta publicação.</div>'
        : "";
    var primaryAction = "";
    if (ignored) {
      primaryAction = '<button class="dor-btn primary" data-dor-restore="' + esc(o.monitorId) + '" data-opportunity="' + esc(o.id) + '">↶ Reativar oferta</button>';
    } else if (canApprove) {
      primaryAction = '<button class="dor-btn primary dor-publish-btn" data-dor-approve="' + esc(o.monitorId) + '" data-opportunity="' + esc(o.id) + '"' + (!affiliate ? ' disabled title="Cadastre o link de afiliado primeiro"' : "") + '>✓ Aprovar e publicar</button>';
    } else if (o.status === "publish_error" && o.eligible && affiliate) {
      primaryAction = '<button class="dor-btn primary dor-publish-btn" data-dor-approve="' + esc(o.monitorId) + '" data-opportunity="' + esc(o.id) + '">Tentar publicar novamente</button>';
    } else if (!published && !ignored && !o.eligible) {
      primaryAction = '<span class="dor-action-hint">Aguardando atingir os critérios</span>';
    }
    var ignoreAction = !published && !ignored ? '<button class="dor-btn danger" data-dor-ignore="' + esc(o.monitorId) + '" data-opportunity="' + esc(o.id) + '">Ignorar</button>' : "";
    var error = o.lastPublishError ? '<div class="dor-inline-error">' + esc(o.lastPublishError) + '</div>' : "";
    return '<article class="dor-offer-card">' +
      '<div class="dor-offer-card-top"><span class="dor-offer-status ' + statusClass + '">' + esc(statusLabel) + '</span><span class="dor-offer-monitor">' + esc(o.monitorTitle) + ' · ' + esc(o.storeLabel) + '</span></div>' +
      '<div class="dor-offer-main">' + image + '<div class="dor-offer-info"><h3>' + esc(o.title || "Produto sem título") + '</h3><p><a href="' + esc(o.url || "#") + '" target="_blank" rel="noopener noreferrer">Ver anúncio original ↗</a> · Atualizado ' + esc(dt(o.updatedAt)) + '</p></div></div>' +
      '<div class="dor-offer-prices"><div><span>' + (o.couponPrice && Number(o.couponPrice) < Number(o.listedPrice || o.currentPrice) ? 'Preço efetivo' : 'Preço atual') + '</span><strong>' + price + '</strong></div><div>' + old + discount + '</div></div>' +
      couponMarkup + conditionsMarkup +
      '<p class="dor-offer-note">' + note + (o.lastSentAt ? " · Publicada em " + dt(o.lastSentAt) : "") + '</p>' +
      affiliateRow + error +
      '<div class="dor-offer-actions">' + primaryAction + ignoreAction + (o.lastSentPrice != null ? '<span class="dor-last-published">Última publicação: ' + money(o.lastSentPrice) + '</span>' : "") + '</div>' +
    '</article>';
  }).join("");
}
function saveAffiliate(monitorId, id) {
  var field = document.getElementById("dor-aff-" + monitorId + "-" + id);
  if (!field) return;
  api("/monitors/" + encodeURIComponent(monitorId) + "/opportunities/" + encodeURIComponent(id) + "/affiliate", {
    method: "POST", body: JSON.stringify({ affiliate_url: field.value.trim() })
  }).then(function (r) {
    notice(r.published ? "Link salvo e oferta publicada no Telegram." : "Link de afiliado salvo. Confira se a oferta está elegível para publicação.", "success");
    return loadAllOpportunities().then(loadMonitors);
  }).catch(function (e) { notice(e.message, "error"); });
}
function scanMonitor(id) {
  var m = monitors.find(function (x) { return x.id === id; });
  if (!m) return;
  notice("Pesquisando ofertas de " + (m.storeLabel || m.store) + ". A consulta pode levar alguns segundos.");
  var button = document.querySelector('[data-dor-scan="' + id + '"]');
  if (button) { button.disabled = true; button.textContent = "Pesquisando..."; }
  api("/monitors/" + encodeURIComponent(id) + "/scan", { method: "POST" }).then(function (result) {
    notice("Pesquisa direta em " + (result.store || m.storeLabel || m.store) + " concluída: " + result.resultsFound + " produto(s) encontrados, " + result.offersSaved + " salvos, " + result.eligibleOffers + " elegíveis e " + result.published + " publicados. Cupons identificados são exibidos no cartão da oferta.", "success");
    return loadMonitors().then(loadAllOpportunities);
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
    return loadMonitors().then(loadAllOpportunities);
  }).catch(function (e) { notice(e.message, "error"); });
}
function deleteMonitor(id) {
  var m = monitors.find(function (x) { return x.id === id; });
  if (!m || !window.confirm("Excluir o monitoramento “" + m.title + "” e as oportunidades associadas?")) return;
  api("/monitors/" + encodeURIComponent(id), { method:"DELETE" }).then(function () {
    if (activeMonitorFilter === id) activeMonitorFilter = "all";
    notice("Monitoramento excluído.", "success");
    return loadMonitors().then(loadAllOpportunities);
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
    var wasEditing = !!editingId;
    if (!data.title || !data.keywords.length) return notice("Informe um nome e pelo menos uma palavra-chave.", "error");
    if (data.keywords.length > 5) return notice("Use no máximo cinco palavras-chave por monitoramento.", "error");
    if (!Number.isFinite(data.min_discount_percent) || data.min_discount_percent < 0 || data.min_discount_percent > 90) return notice("O desconto mínimo deve ficar entre 0% e 90%.", "error");
    if (data.max_price !== null && (!Number.isFinite(data.max_price) || data.max_price <= 0)) return notice("Informe um preço máximo válido.", "error");
    var path = editingId ? "/monitors/" + encodeURIComponent(editingId) : "/monitors";
    var method = editingId ? "PUT" : "POST";
    var button = document.getElementById("dor-save-monitor");
    button.disabled = true;
    api(path, { method:method, body:JSON.stringify(data) }).then(function (result) {
      var id = (result.monitor || {}).id || editingId;
      resetMonitorForm();
      notice(wasEditing ? "Monitoramento atualizado." : "Monitoramento criado.", "success");
      return loadMonitors().then(loadAllOpportunities).then(function () {
        if (id) loadOpportunities(id);
      });
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
  document.getElementById("dor-open-monitor").addEventListener("click", function () {
    var panel = document.getElementById("dor-monitor-form-panel");
    if (panel) { panel.open = true; panel.scrollIntoView({ behavior:"smooth", block:"center" }); }
    document.getElementById("dor-title").focus();
  });
  document.getElementById("dor-refresh-all").addEventListener("click", function () {
    notice("Atualizando central de ofertas...");
    loadMonitors().then(loadAllOpportunities).then(function () { notice("Painel atualizado.", "success"); }).catch(function (e) { notice(e.message, "error"); });
  });
  document.getElementById("dor-refresh").addEventListener("click", function () {
    loadMonitors().then(loadAllOpportunities).then(function () { notice("Monitoramentos atualizados.", "success"); }).catch(function (e) { notice(e.message, "error"); });
  });
  document.getElementById("dor-reload-opportunities").addEventListener("click", function () {
    loadAllOpportunities().then(function () { notice("Fila de ofertas atualizada.", "success"); }).catch(function (e) { notice(e.message, "error"); });
  });
  document.getElementById("dor-monitor-filter").addEventListener("change", function () {
    activeMonitorFilter = this.value || "all";
    renderOpportunities();
  });
  document.getElementById("dor-filter-tabs").addEventListener("click", function (e) {
    var button = e.target.closest("[data-dor-filter]");
    if (!button) return;
    queueFilter = button.getAttribute("data-dor-filter");
    renderOpportunities();
  });
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
    var affiliate = e.target.closest("[data-dor-affiliate]");
    var approve = e.target.closest("[data-dor-approve]");
    var ignore = e.target.closest("[data-dor-ignore]");
    var restore = e.target.closest("[data-dor-restore]");
    if (affiliate) saveAffiliate(affiliate.getAttribute("data-dor-affiliate"), affiliate.getAttribute("data-opportunity"));
    if (approve) {
      var mid = approve.getAttribute("data-dor-approve"), oid = approve.getAttribute("data-opportunity");
      api("/monitors/" + encodeURIComponent(mid) + "/opportunities/" + encodeURIComponent(oid) + "/approve", { method:"POST" })
        .then(function () { notice("Oferta publicada com sucesso no Telegram.", "success"); return loadAllOpportunities().then(loadMonitors); })
        .catch(function (err) { notice(err.message, "error"); });
    }
    if (ignore) {
      var ignoreMid = ignore.getAttribute("data-dor-ignore"), ignoreId = ignore.getAttribute("data-opportunity");
      api("/monitors/" + encodeURIComponent(ignoreMid) + "/opportunities/" + encodeURIComponent(ignoreId) + "/ignore", { method:"POST" })
        .then(function () { notice("Oferta movida para Ignoradas. Você poderá reativá-la depois.", "success"); return loadAllOpportunities(); })
        .catch(function (err) { notice(err.message, "error"); });
    }
    if (restore) {
      var restoreMid = restore.getAttribute("data-dor-restore"), restoreId = restore.getAttribute("data-opportunity");
      api("/monitors/" + encodeURIComponent(restoreMid) + "/opportunities/" + encodeURIComponent(restoreId) + "/restore", { method:"POST" })
        .then(function (data) { notice(data.eligible ? "Oferta reativada e liberada para avaliação." : "Oferta reativada, mas ainda não atende aos critérios do monitor.", data.eligible ? "success" : ""); return loadAllOpportunities(); })
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
  Promise.all([loadMonitors(), loadTelegram()]).then(loadAllOpportunities).then(function () { notice("Central de ofertas pronta. Acompanhe a fila e os monitoramentos abaixo.", "success"); }).catch(function (e) {
    notice(e.message, "error");
    document.getElementById("dor-status-text").textContent = "Faça login para começar";
  });
}
window.resolveiRadarOfertasInit = init;
})();