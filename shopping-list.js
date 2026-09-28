/* Resolvei — Lista de Compras colaborativa, sem IA */
(function () {
  "use strict";

  var CATEGORIES = [
    {id:"hortifruti", title:"Hortifruti", icon:"🥬", order:10, words:["tomate","cebola","alho","batata","cenoura","banana","maca","maça","laranja","limao","limão","mamão","manga","abacaxi","melancia","uva","morango","alface","rucula","rúcula","couve","brocolis","brócolis","pimentao","pimentão","abobrinha","berinjela","pepino","mandioca","aipim","beterraba","repolho","espinafre","gengibre"]},
    {id:"carnes", title:"Carnes e peixes", icon:"🥩", order:20, words:["carne","patinho","acem","acém","contra file","contrafile","contrafilé","picanha","fraldinha","músculo","musculo","coxao","coxão","alcatra","maminha","figado","fígado","linguica","linguiça","frango","peito de frango","coxa","sobrecoxa","asa de frango","peixe","salmao","salmão","tilapia","tilápia","sardinha","atum fresco","camarao","camarão","bacon"]},
    {id:"frios-laticinios", title:"Frios e laticínios", icon:"🥛", order:30, words:["leite","queijo","mucarela","muçarela","mussarela","requeijao","requeijão","manteiga","margarina","iogurte","creme de leite","presunto","ricota","coalhada","nata"]},
    {id:"padaria", title:"Padaria e café", icon:"🥖", order:40, words:["pao","pão","pao frances","pão francês","pao de forma","pão de forma","torrada","bolo","croissant","rosca","sonho","cafe","café","capsula de cafe","cápsula de café"]},
    {id:"mercearia", title:"Mercearia", icon:"🍚", order:50, words:["arroz","feijao","feijão","macarrao","macarrão","farinha","acucar","açúcar","sal","oleo","óleo","azeite","molho","extrato de tomate","milho","ervilha","atum","sardinha","biscoito","bolacha","cereal","aveia","granola","farofa","temperos","caldo","maisena","maizena","fermento","vinagre","catchup","ketchup","maionese","mostarda","mel","geleia","goiabada","chocolate","achocolatado","leite em po","leite em pó","canela","pimenta"]},
    {id:"bebidas", title:"Bebidas", icon:"🥤", order:60, words:["agua","água","refrigerante","suco","cha","chá","isotonico","isotônico","energetico","energético","agua de coco","água de coco","bebida vegetal","vodka","whisky","uísque","vinho","cerveja"]},
    {id:"congelados", title:"Congelados", icon:"❄️", order:70, words:["pizza congelada","lasanha congelada","nuggets","hamburguer congelado","hambúrguer congelado","batata congelada","sorvete","açai","acai","picolé","legumes congelados"]},
    {id:"limpeza", title:"Limpeza", icon:"🧴", order:80, words:["detergente","sabao","sabão","sabao em po","sabão em pó","sabao liquido","sabão líquido","amaciante","desinfetante","agua sanitaria","água sanitária","multiuso","limpador","esponja","vassoura","rodo","balde","saco de lixo","lustra moveis","lustra-móveis","desengordurante","alvejante","mop","limpa vidro","limpa-vidros"]},
    {id:"higiene", title:"Higiene pessoal", icon:"🧻", order:90, words:["papel higienico","papel higiênico","sabonete","shampoo","xampu","condicionador","creme dental","pasta de dente","escova de dente","fio dental","desodorante","absorvente","algodao","algodão","cotonete","hidratante","protetor solar","barbeador","lâmina","lamina","fralda","lenço umedecido","lenco umedecido","lenço","lenco"]},
    {id:"casa", title:"Casa e descartáveis", icon:"🏠", order:100, words:["papel toalha","guardanapo","papel aluminio","papel alumínio","filme plastico","filme plástico","copo descartavel","copo descartável","prato descartavel","prato descartável","vela","fosforo","fósforo","pilha","lampada","lâmpada","saco zip","ziplock"]},
    {id:"pet", title:"Pets", icon:"🐾", order:110, words:["racao","ração","petisco","areia para gato","areia de gato","tapete higienico","tapete higiênico","antipulgas","shampoo pet"]},
    {id:"outros", title:"Outros", icon:"🛒", order:999, words:[]}
  ];

  var UNITS = [
    "kg","g","mg","l","ml","un","unidade","unidades","pct","pacote","pacotes",
    "cx","caixa","caixas","garrafa","garrafas","lata","latas","maço","maços",
    "maco","macos","rolo","rolos","duzia","dúzia","duzias","dúzias","barra","barras",
    "frasco","frascos","saco","sacos","pote","potes"
  ];

  var state = window.resolveiShoppingState || {
    listId: null,
    list: null,
    items: [],
    lists: [],
    unsubList: null,
    unsubItems: null,
    unsubLists: null,
    authBound: false,
    eventsBound: false,
    marketMode: false,
    itemsLoaded: false,
    editingId: null,
    editingTitle: false,
    toastTimer: null,
    legacyMigrationAttempted: {},
    classificationRules: {},
    classificationRulesLoaded: false,
    classificationRulesUserId: "",
    unsubClassificationRules: null
  };
  window.resolveiShoppingState = state;

  function db() {
    if (!window.firebase || !firebase.apps.length) return null;
    try { return firebase.firestore(); } catch (e) { return null; }
  }

  function user() {
    try { return firebase.auth().currentUser || null; } catch (e) { return null; }
  }

  function uid() {
    var u = user();
    return u ? u.uid : "";
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
    });
  }

  function normalize(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9\s-]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function titleCase(value) {
    return String(value || "").replace(/\S+/g, function (word) {
      if (word.length <= 3 && word === word.toUpperCase()) return word;
      return word.charAt(0).toUpperCase() + word.slice(1);
    });
  }

  function parseNumber(value) {
    var n = Number(String(value || "").replace(",", "."));
    return isFinite(n) ? n : 0;
  }

  function formatQty(qty) {
    var n = Number(qty);
    if (!isFinite(n)) return "1";
    return String(Math.round(n * 1000) / 1000).replace(".", ",");
  }

  function categoryFor(name) {
    var n = normalize(name);

    // A classificação aprendida pelo usuário sempre vence as regras genéricas.
    var learned = state.classificationRules[n];
    if (learned) return categoryById(learned);

    // Produtos compostos devem vencer palavras genéricas.
    // Ex.: "molho de tomate" é mercearia, mesmo contendo "tomate".
    var phraseRules = [
      ["molho de tomate", "mercearia"],
      ["extrato de tomate", "mercearia"],
      ["polpa de tomate", "mercearia"],
      ["tomate pelado", "mercearia"],
      ["pure de tomate", "mercearia"],
      ["purê de tomate", "mercearia"],
      ["geleia de fruta", "mercearia"],
      ["doce de leite", "mercearia"],
      ["leite condensado", "mercearia"],
      ["creme de leite", "mercearia"],
      ["leite em po", "mercearia"],
      ["leite em pó", "mercearia"],
      ["farinha de trigo", "mercearia"],
      ["farinha de mandioca", "mercearia"],
      ["sardinha em lata", "mercearia"],
      ["atum em lata", "mercearia"],
      ["hamburguer congelado", "congelados"],
      ["hambúrguer congelado", "congelados"],
      ["legumes congelados", "congelados"]
    ];
    for (var p = 0; p < phraseRules.length; p++) {
      if (n.indexOf(normalize(phraseRules[p][0])) !== -1) {
        return categoryById(phraseRules[p][1]);
      }
    }

    for (var i = 0; i < CATEGORIES.length; i++) {
      var cat = CATEGORIES[i];
      for (var j = 0; j < cat.words.length; j++) {
        var word = normalize(cat.words[j]);
        if (word && n.indexOf(word) !== -1) return cat;
      }
    }
    return CATEGORIES[CATEGORIES.length - 1];
  }

  function cleanRawLine(line) {
    return String(line || "")
      .replace(/^\s*(?:[-*•☐☑✔✓]|\d+[.)-])\s*/i, "")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/\s*[,;]\s*$/, "");
  }

  // Marcas comuns que, quando aparecem após vírgula, não devem virar outro produto.
  // A lista é deliberadamente simples e pode ser ampliada sem IA.
  var KNOWN_BRANDS = [
    "vigor","sadia","seara","perdigao","perdigão","qualy","nestle","nestlé",
    "itambe","itam bé","itambe","piracanjuba","toddynho","nescau","ninho",
    "coca cola","coca-cola","pepsi","guarana antarctica","guaraná antarctica",
    "heineken","brahma","skol","itaipava","yoki","kicaldo","camil","tio joao",
    "tio joão","urbano","predilecta","predilect a","elefante","hellmanns",
    "hellmann's","cepêra","cepera","arisco","knorr","maggi","sazón","sazon"
  ];

  function extractBrand(text) {
    var raw = String(text || "").trim();
    var parts = raw.split(/\s*,\s*/).map(function (x) { return x.trim(); }).filter(Boolean);
    if (parts.length === 2) {
      var second = normalize(parts[1]);
      if (KNOWN_BRANDS.indexOf(second) !== -1) {
        return { product: parts[0], brand: parts[1] };
      }
    }
    return { product: raw, brand: "" };
  }

  function looksLikeKnownBrand(text) {
    return KNOWN_BRANDS.indexOf(normalize(text)) !== -1;
  }

  function parseCommaSeparatedProducts(input) {
    var parts = String(input || "").split(/\s*,\s*/).map(function (x) { return x.trim(); }).filter(Boolean);
    if (parts.length < 2) return [String(input || "").trim()];

    // "Molho de tomate, Vigor" = um produto com marca, não dois produtos.
    if (parts.length === 2 && looksLikeKnownBrand(parts[1])) return [String(input || "").trim()];

    return parts;
  }

  function parseShoppingLine(raw) {
    var original = cleanRawLine(raw);
    if (!original) return null;

    var brandInfo = extractBrand(original);
    var text = brandInfo.product;
    var qty = 1;
    var unit = "un.";
    var match;

    var unitPattern = "(kg|g|mg|l|ml|unidades?|un|pct|pacotes?|caixas?|cx|garrafas?|latas?|ma[cç]os?|rolos?|duzias?|d[uú]zia|barras?|frascos?|sacos?|potes?)";
    match = text.match(new RegExp("^(.+?)\\s+(\\d+(?:[.,]\\d+)?)\\s*" + unitPattern + "\\s*$", "i"));
    if (match) {
      text = match[1].trim();
      qty = parseNumber(match[2]);
      unit = normalize(match[3]);
    } else {
      match = text.match(new RegExp("^(\\d+(?:[.,]\\d+)?)\\s*" + unitPattern + "\\s+(.+)$", "i"));
      if (match) {
        qty = parseNumber(match[1]);
        unit = normalize(match[2]);
        text = match[3].trim();
      } else {
        match = text.match(/^(\d+(?:[.,]\d+)?)\s+(.+)$/);
        if (match && normalize(match[2]).split(" ").length >= 1) {
          qty = parseNumber(match[1]);
          text = match[2].trim().replace(/^de\s+/i, "");
        }
      }
    }

    var unitMap = {
      kg:"kg", g:"g", mg:"mg", l:"L", ml:"ml", un:"un.", unidade:"un.", unidades:"un.",
      pct:"pct.", pacote:"pacote", pacotes:"pacotes", cx:"caixa", caixa:"caixa", caixas:"caixas",
      garrafa:"garrafa", garrafas:"garrafas", lata:"lata", latas:"latas", maço:"maço", maco:"maço",
      maços:"maços", macos:"maços", rolo:"rolo", rolos:"rolos", duzia:"dúzia", dúzia:"dúzia",
      duzias:"dúzias", dúzias:"dúzias", barra:"barra", barras:"barras", frasco:"frasco",
      frascos:"frascos", saco:"saco", sacos:"sacos", pote:"pote", potes:"potes"
    };
    unit = unitMap[unit] || unit || "un.";
    if (qty <= 0) qty = 1;

    return {
      raw: original,
      name: titleCase(text),
      brand: brandInfo.brand || "",
      qty: qty,
      unit: unit,
      categoryId: categoryFor(text).id
    };
  }

  function parseListText(raw) {
    var input = String(raw || "").trim();
    if (!input) return [];
    var lines = input.split(/\r?\n/).map(function (x) { return x.trim(); }).filter(Boolean);
    if (lines.length === 1 && /[,;]/.test(lines[0])) {
      lines = /;/.test(lines[0])
        ? lines[0].split(/\s*;\s*/).map(function (x) { return x.trim(); }).filter(Boolean)
        : parseCommaSeparatedProducts(lines[0]);
    }
    var result = [];
    lines.forEach(function (line) {
      var parsed = parseShoppingLine(line);
      if (parsed) result.push(parsed);
    });
    return result;
  }

  function getHashParams() {
    var hash = location.hash || "";
    var q = hash.indexOf("?") >= 0 ? hash.slice(hash.indexOf("?") + 1) : "";
    try { return new URLSearchParams(q); } catch (e) { return new URLSearchParams(); }
  }

  function getQueryListId() {
    return getHashParams().get("list") || "";
  }

  function hashForList(id) {
    return "#/ferramenta/lista-compras?list=" + encodeURIComponent(id);
  }

  function goList(id) {
    state.listId = id || null;
    location.hash = id ? hashForList(id) : "#/ferramenta/lista-compras";
  }

  function root() {
    return document.getElementById("shoppingState");
  }

  function toast(message) {
    var box = document.getElementById("shoppingToast");
    if (!box) return;
    box.textContent = message;
    box.hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(function () { box.hidden = true; }, 2800);
  }

  function userLabel() {
    var u = user();
    return u ? (u.displayName || u.email || "Você") : "";
  }

  function sortLists(a, b) {
    var ad = a.updatedAt && a.updatedAt.toMillis ? a.updatedAt.toMillis() : 0;
    var bd = b.updatedAt && b.updatedAt.toMillis ? b.updatedAt.toMillis() : 0;
    return bd - ad;
  }

  function sortItems(a, b) {
    var ap = typeof a.position === "number" ? a.position : 999999;
    var bp = typeof b.position === "number" ? b.position : 999999;
    if (ap !== bp) return ap - bp;
    var at = a.createdAt && a.createdAt.toMillis ? a.createdAt.toMillis() : 0;
    var bt = b.createdAt && b.createdAt.toMillis ? b.createdAt.toMillis() : 0;
    return at - bt;
  }

  function categoryById(id) {
    for (var i = 0; i < CATEGORIES.length; i++) if (CATEGORIES[i].id === id) return CATEGORIES[i];
    return CATEGORIES[CATEGORIES.length - 1];
  }

  function shareLink() {
    return location.origin + location.pathname + hashForList(state.listId);
  }

  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(function () { fallbackCopy(text); });
    }
    fallbackCopy(text);
    return Promise.resolve();
  }

  function renderAuthRequired() {
    root().innerHTML =
      '<section class="shopping-auth card panel">' +
        '<div class="shopping-big-icon">🛒</div>' +
        '<span class="eyebrow">LISTA COLABORATIVA</span>' +
        '<h2>Entre no Resolvei para criar e compartilhar listas</h2>' +
        '<p>As listas compartilhadas ficam salvas na conta e são atualizadas em tempo real. A organização é feita por regras do próprio Resolvei, sem IA.</p>' +
        '<div class="actions"><a class="btn primary" href="#/conta">Entrar / Criar conta</a></div>' +
      '</section>';
  }

  function listIsFinalized(list) {
    var count = Number(list.itemCount || 0);
    var done = Number(list.doneCount || 0);
    return count > 0 && done >= count;
  }

  function listHistoryRow(x, finalized) {
    var memberCount = Array.isArray(x.memberIds) ? x.memberIds.length : 1;
    var count = Number(x.itemCount || 0);
    var done = Number(x.doneCount || 0);
    var status = finalized ? (count + " " + (count === 1 ? "item" : "itens") + " · concluída") : (count + " " + (count === 1 ? "item" : "itens") + (done ? " · " + done + " comprados" : ""));
    return '<div class="shopping-history-item">' +
      '<button class="shopping-history-row" type="button" data-action="open-list" data-list-id="' + esc(x.id) + '">' +
        '<span class="shopping-history-icon">' + (finalized ? "✅" : "🛒") + '</span>' +
        '<span class="shopping-history-main"><strong>' + esc(x.title || "Lista de compras") + '</strong><small>' + esc(status) + ' · ' + memberCount + ' ' + (memberCount === 1 ? "pessoa" : "pessoas") + '</small></span>' +
        '<span class="shopping-history-arrow">›</span>' +
      '</button>' +
      '<div class="shopping-history-side-actions">' +
        (finalized ? '<button class="shopping-history-reuse" type="button" title="Reaproveitar lista" aria-label="Reaproveitar lista" data-action="reuse-list" data-list-id="' + esc(x.id) + '">↻</button>' : '') +
        (x.ownerId === uid() ? '<button class="shopping-history-delete" type="button" title="Excluir lista" aria-label="Excluir lista" data-action="delete-list" data-list-id="' + esc(x.id) + '">×</button>' : '') +
      '</div>' +
    '</div>';
  }

  function renderHome() {
    var active = state.lists.filter(function (x) { return !listIsFinalized(x); });
    var finalized = state.lists.filter(function (x) { return listIsFinalized(x); });

    var activeHtml = active.length
      ? active.map(function (x) { return listHistoryRow(x, false); }).join("")
      : '<div class="shopping-empty-history"><strong>Nenhuma lista ativa.</strong><span>Crie sua primeira lista ao lado.</span></div>';

    var finalizedHtml = finalized.length
      ? finalized.map(function (x) { return listHistoryRow(x, true); }).join("")
      : '<div class="shopping-empty-history"><strong>Nenhuma lista finalizada.</strong><span>Quando todos os itens forem comprados, a lista virá para cá.</span></div>';

    root().innerHTML =
      '<div class="shopping-header-block">' +
        '<div><span class="eyebrow">LISTA DE COMPRAS</span><h2>Monte sua lista e vá às compras</h2><p>Digite os produtos como você fala no dia a dia. O Resolvei organiza tudo por setor automaticamente.</p></div>' +
        '<span class="shopping-no-ai">⚡ Não usa IA</span>' +
      '</div>' +
      '<div class="shopping-create-grid">' +
        '<section class="card panel shopping-create-card">' +
          '<div class="shopping-step"><span>1</span><div><strong>Crie uma lista</strong><small>Dê um nome para encontrar depois.</small></div></div>' +
          '<label class="field"><span>Nome da lista</span><input id="shoppingTitle" maxlength="80" value="Compras" placeholder="Ex.: Compras da casa"></label>' +
          '<div class="shopping-step"><span>2</span><div><strong>Digite ou cole os produtos</strong><small>Um produto por linha funciona melhor.</small></div></div>' +
          '<label class="field"><span class="sr-only">Produtos</span><textarea id="shoppingInput" rows="11" placeholder="Arroz 5kg&#10;Feijão 2 pacotes&#10;Molho de tomate, Vigor&#10;Leite 1L&#10;Tomate 1kg&#10;Detergente"></textarea></label>' +
          '<div class="shopping-example"><strong>Dica:</strong> escreva quantidade e marca quando quiser. Ex.: <em>Molho de tomate, Vigor</em>.</div>' +
          '<div class="actions shopping-primary-action"><button class="btn primary full" type="button" data-action="create-list">🛒 Organizar e criar lista</button></div>' +
          '<div id="shoppingHomeMsg" class="notice" hidden></div>' +
        '</section>' +
        '<section class="card panel shopping-history-card">' +
          '<div class="shopping-section-title"><div><h3>Suas listas</h3><p>Você pode continuar uma lista ou reaproveitar uma finalizada.</p></div></div>' +
          '<div class="shopping-history-group"><div class="shopping-history-group-title"><span>🛒 Listas ativas</span><b>' + active.length + '</b></div><div class="shopping-history">' + activeHtml + '</div></div>' +
          '<div class="shopping-history-group"><div class="shopping-history-group-title finalized"><span>✅ Listas finalizadas</span><b>' + finalized.length + '</b></div><div class="shopping-history">' + finalizedHtml + '</div></div>' +
        '</section>' +
      '</div>';
  }

  function itemMarkup(item) {
    var doneClass = item.done ? " done" : "";
    var editing = state.editingId === item.id;
    if (editing) {
      return '<div class="shopping-edit-card" data-item-row="' + esc(item.id) + '">' +
        '<div class="shopping-edit-title">Editar / reclassificar produto</div>' +
        '<div class="shopping-edit-grid">' +
          '<label class="field"><span>Produto</span><input data-edit-name type="text" value="' + esc(item.name + (item.brand ? ", " + item.brand : "")) + '" maxlength="120"></label>' +
          '<label class="field"><span>Quantidade</span><input data-edit-qty type="number" min="0.001" step="any" value="' + esc(item.qty) + '"></label>' +
          '<label class="field"><span>Unidade</span><select data-edit-unit>' +
            ["un.","kg","g","L","ml","pct.","pacote","pacotes","caixa","caixas","garrafa","garrafas","lata","latas","maço","maços","rolo","rolos","dúzia","dúzias","barra","barras","frasco","frascos","saco","sacos","pote","potes"].map(function(u){ return '<option value="' + esc(u) + '"' + (u === (item.unit || "un.") ? " selected" : "") + '>' + esc(u) + '</option>'; }).join("") +
          '</select></label>' +
          '<label class="field"><span>Classificação</span><select data-edit-category>' +
            CATEGORIES.map(function(cat){ return '<option value="' + esc(cat.id) + '"' + (cat.id === categoryFor(item.name).id ? " selected" : "") + '>' + cat.icon + ' ' + esc(cat.title) + '</option>'; }).join("") +
          '</select></label>' +
        '</div>' +
        '<div class="shopping-edit-actions">' +
          '<button class="btn" type="button" data-action="ai-category" data-item-id="' + esc(item.id) + '">✨ Sugerir com IA</button>' +
          '<button class="btn primary" type="button" data-action="save-edit-item" data-item-id="' + esc(item.id) + '">Salvar</button><button class="btn ghost" type="button" data-action="cancel-edit">Cancelar</button></div>' +
        '<div class="shopping-edit-ai-msg" data-ai-msg hidden></div>' +
      '</div>';
    }
    return '<div class="shopping-item-row' + doneClass + '" data-item-row="' + esc(item.id) + '">' +
      '<label class="shopping-check-label">' +
        '<input type="checkbox" data-action="toggle-item" data-item-id="' + esc(item.id) + '"' + (item.done ? " checked" : "") + '>' +
        '<span class="shopping-check"></span>' +
        '<span class="shopping-item-text"><strong>' + esc(item.name) + (item.brand ? ' <em class="shopping-brand">(' + esc(item.brand) + ')</em>' : '') + '</strong><small>' + esc(formatQty(item.qty) + " " + (item.unit || "un.")) + '</small></span>' +
      '</label>' +
      '<div class="shopping-item-actions">' +
        '<button class="shopping-icon-btn" type="button" title="Editar / reclassificar item" aria-label="Editar / reclassificar item" data-action="edit-item" data-item-id="' + esc(item.id) + '">✎</button>' +
        '<button class="shopping-icon-btn danger" type="button" title="Excluir item" aria-label="Excluir item" data-action="delete-item" data-item-id="' + esc(item.id) + '">×</button>' +
      '</div>' +
    '</div>';
  }

  function renderList() {
    var items = state.items.slice().sort(sortItems);
    var visible = state.marketMode ? items.filter(function (x) { return !x.done; }) : items;
    var doneCount = items.filter(function (x) { return !!x.done; }).length;
    var memberCount = Array.isArray(state.list.memberIds) ? state.list.memberIds.length : 1;
    var groups = {};

    visible.forEach(function (item) {
      var cid = categoryFor(item.name).id;
      if (!groups[cid]) groups[cid] = [];
      groups[cid].push(item);
    });

    var groupHtml = CATEGORIES.filter(function (c) { return groups[c.id] && groups[c.id].length; }).map(function (cat) {
      return '<section class="shopping-category">' +
        '<div class="shopping-category-head"><div><span class="shopping-category-icon">' + cat.icon + '</span><h3>' + cat.title + '</h3></div><span>' + groups[cat.id].length + '</span></div>' +
        '<div class="shopping-items">' + groups[cat.id].map(itemMarkup).join("") + '</div>' +
      '</section>';
    }).join("");

    if (!groupHtml) {
      groupHtml = '<div class="shopping-no-items">' +
        (state.marketMode && doneCount ? '<strong>Você já colocou tudo no carrinho. 🎉</strong><span>Desative o Modo mercado para rever os itens comprados.</span>' : '<strong>Sua lista está vazia.</strong><span>Adicione um produto acima.</span>') +
      '</div>';
    }

    root().innerHTML =
      '<div class="shopping-list-shell">' +
        '<div class="shopping-list-top">' +
          '<button class="btn ghost" type="button" data-action="back-home">← Minhas listas</button>' +
          '<div class="shopping-list-title">' +
            '<span class="eyebrow">LISTA DE COMPRAS</span>' +
            (state.editingTitle
              ? '<div class="shopping-title-inline-edit"><input id="shoppingTitleEdit" type="text" maxlength="80" value="' + esc(state.list.title || "Lista de compras") + '" aria-label="Nome da lista"><button class="shopping-inline-save" type="button" data-action="save-title">Salvar</button><button class="shopping-inline-cancel" type="button" data-action="cancel-title">Cancelar</button></div>'
              : '<div class="shopping-title-edit-wrap"><h2>' + esc(state.list.title || "Lista de compras") + '</h2><button class="shopping-title-edit" type="button" data-action="rename-list" aria-label="Editar nome da lista">✎</button></div>') +
            '<p>' + memberCount + ' ' + (memberCount === 1 ? "pessoa" : "pessoas") + ' com acesso · 🟢 sincronização em tempo real</p>' +
          '</div>' +
          '<div class="shopping-list-top-actions">' +
            '<button class="btn" type="button" data-action="share">🔗 Compartilhar</button>' +
            (listIsFinalized(state.list) ? '<button class="btn" type="button" data-action="reuse-current-list">↻ Reaproveitar</button>' : '') +
            (state.list.ownerId === uid() ? '<button class="btn ghost" type="button" data-action="delete-current-list">🗑 Excluir</button>' : '') +
          '</div>' +
        '</div>' +
        '<div class="shopping-progress-card">' +
          '<div><strong>' + doneCount + ' de ' + items.length + ' itens</strong><span>' + (items.length ? Math.round(doneCount / items.length * 100) : 0) + '% concluído</span></div>' +
          '<div class="shopping-progress"><span style="width:' + (items.length ? Math.round(doneCount / items.length * 100) : 0) + '%"></span></div>' +
        '</div>' +
        '<div class="shopping-add-card">' +
          '<div class="shopping-add-heading"><strong>Adicionar produto</strong><span>Digite, toque em adicionar e continue.</span></div>' +
          '<div class="shopping-add-row">' +
            '<input id="shoppingAddInput" type="text" autocomplete="off" placeholder="Ex.: Café 500g, 2 pacotes de arroz, banana...">' +
            '<button class="btn primary" type="button" data-action="add-item">＋ Adicionar</button>' +
          '</div>' +
          '<details class="shopping-bulk-details">' +
            '<summary>Adicionar vários produtos de uma vez</summary>' +
            '<textarea id="shoppingBulkInput" rows="5" placeholder="Um por linha:&#10;Arroz 5kg&#10;Feijão 2 pacotes&#10;Molho de tomate, Vigor"></textarea>' +
            '<div class="actions"><button class="btn" type="button" data-action="add-bulk">Adicionar todos</button></div>' +
          '</details>' +
        '</div>' +
        '<div class="shopping-list-toolbar">' +
          '<div class="shopping-note-line">O Resolvei organiza os produtos automaticamente. O que não reconhecer vai para <strong>Outros</strong>.</div>' +
          '<button class="btn" type="button" data-action="toggle-market">' + (state.marketMode ? "👁 Mostrar comprados" : "🛒 Modo mercado") + '</button>' +
        '</div>' +
        '<div class="shopping-category-list">' + groupHtml + '</div>' +
        '<div class="shopping-bottom-actions">' +
          '<button class="btn ghost" type="button" data-action="clear-done"' + (doneCount ? "" : " disabled") + '>Limpar itens comprados</button>' +
          '<button class="btn ghost" type="button" data-action="rename-list">✎ Renomear lista</button>' +
        '</div>' +
      '</div>' +
      '<div id="shoppingToast" class="shopping-toast" hidden></div>';
  }

  function renderJoinList() {
    var memberCount = Array.isArray(state.list.memberIds) ? state.list.memberIds.length : 1;
    root().innerHTML =
      '<section class="shopping-join card panel">' +
        '<div class="shopping-big-icon">🔗</div>' +
        '<span class="eyebrow">LISTA COMPARTILHADA</span>' +
        '<h2>' + esc(state.list.title || "Lista de compras") + '</h2>' +
        '<p>Esta lista foi compartilhada com você. Ao entrar, você poderá adicionar, editar e marcar itens como comprados.</p>' +
        '<div class="shopping-join-meta">👥 ' + memberCount + ' ' + (memberCount === 1 ? "pessoa já tem" : "pessoas já têm") + ' acesso</div>' +
        '<div class="actions"><button class="btn primary" type="button" data-action="join-list">Entrar nesta lista</button><button class="btn ghost" type="button" data-action="back-home">Cancelar</button></div>' +
        '<div id="shoppingJoinMsg" class="notice" hidden></div>' +
      '</section>';
  }

  function renderLoading(text) {
    root().innerHTML = '<div class="shopping-loading card panel">⏳ ' + esc(text || "Carregando lista...") + '</div>';
  }

  function renderCurrent() {
    if (!root()) return;
    var current = user();
    if (!current) {
      renderAuthRequired();
      return;
    }
    if (!state.listId) {
      renderHome();
      return;
    }
    if (!state.list) {
      renderLoading("Abrindo lista...");
      return;
    }
    var members = Array.isArray(state.list.memberIds) ? state.list.memberIds : [];
    if (members.indexOf(current.uid) === -1) {
      renderJoinList();
      return;
    }
    renderList();
  }

  function cleanupEmptyList(id) {
    if (!id || !uid()) return Promise.resolve(false);
    return resolveiToken().then(function (token) {
      return fetch("/api/shopping/lists/" + encodeURIComponent(id) + "/cleanup", {
        method: "POST",
        headers: { Authorization: "Bearer " + token }
      });
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) throw new Error(data.detail || "Falha ao verificar a lista.");
        return !!data.deleted;
      });
    });
  }

  function normalizeEmbeddedItems(rawItems) {
    if (!Array.isArray(rawItems)) return [];
    return rawItems.map(function (x) {
      var item = Object.assign({}, x || {});
      item.id = item.id || ("legacy-" + Math.random().toString(36).slice(2));
      item.name = String(item.name || "").trim();
      item.brand = String(item.brand || "");
      item.qty = Number(item.qty) > 0 ? Number(item.qty) : 1;
      item.unit = item.unit || "un.";
      item.categoryId = categoryFor(item.name).id;
      item.done = !!item.done;
      item.position = typeof item.position === "number" ? item.position : 999999;
      return item;
    }).filter(function (x) { return !!x.name; }).sort(sortItems);
  }

  function stateFromEmbeddedList(data) {
    return normalizeEmbeddedItems(data && data.items);
  }

  function persistLegacyItems(listId, legacyItems, ref, data) {
    var clean = normalizeEmbeddedItems(legacyItems).map(function (item, index) {
      item.position = index;
      return item;
    });
    return ref.update({
      items: clean,
      itemCount: clean.length,
      doneCount: clean.filter(function (x) { return !!x.done; }).length,
      updatedAt: firebase.firestore.FieldValue.serverTimestamp()
    }).then(function () {
      return clean;
    });
  }

  function migrateLegacyItems(listId, ref, data) {
    if (Object.prototype.hasOwnProperty.call(data || {}, "items")) {
      return Promise.resolve(stateFromEmbeddedList(data));
    }
    if (state.legacyMigrationAttempted[listId]) return Promise.resolve([]);
    return ref.collection("items").get().then(function (snap) {
      var legacy = snap.docs.map(function (d) {
        var item = d.data() || {};
        item.id = d.id;
        return item;
      }).sort(sortItems);
      state.legacyMigrationAttempted[listId] = true;
      return persistLegacyItems(listId, legacy, ref, data);
    }).catch(function (error) {
      console.error("Resolvei legacy shopping migration:", error);
      toast("Não foi possível sincronizar os itens antigos desta lista. Tentando novamente quando a conexão voltar.");
      return null;
    });
  }

  function classificationRuleKey(name) {
    return normalize(name).replace(/[^a-z0-9_-]+/g, "_").slice(0, 120) || "produto";
  }

  function ingestClassificationRules(data) {
    var map = data && data.shoppingCategoryRules && typeof data.shoppingCategoryRules === "object"
      ? data.shoppingCategoryRules : {};
    state.classificationRules = {};
    Object.keys(map).forEach(function (key) {
      var entry = map[key];
      if (!entry || typeof entry !== "object") return;
      var product = normalize(entry.product || "");
      var categoryId = String(entry.categoryId || "");
      if (product && categoryId) state.classificationRules[product] = categoryId;
    });
    state.classificationRulesLoaded = true;
  }

  function subscribeClassificationRules() {
    if (!db() || !uid()) return;
    var currentUid = uid();
    if (state.unsubClassificationRules) state.unsubClassificationRules();
    state.classificationRulesUserId = currentUid;
    state.classificationRulesLoaded = false;
    state.unsubClassificationRules = db().collection("users").doc(currentUid).onSnapshot(function (snap) {
      if (state.classificationRulesUserId !== currentUid) return;
      ingestClassificationRules(snap.exists ? (snap.data() || {}) : {});
    }, function (error) {
      console.warn("Resolvei shopping classification rules:", error);
      state.classificationRules = {};
      state.classificationRulesLoaded = true;
    });
  }

  function ensureClassificationRules() {
    if (state.classificationRulesLoaded) return Promise.resolve();
    if (!db() || !uid()) return Promise.resolve();
    var currentUid = uid();
    return db().collection("users").doc(currentUid).get().then(function (snap) {
      if (state.classificationRulesUserId === currentUid) ingestClassificationRules(snap.exists ? (snap.data() || {}) : {});
    }).catch(function (error) {
      console.warn("Resolvei shopping classification rules load:", error);
      state.classificationRulesLoaded = true;
    });
  }

  function learnClassification(productName, categoryId) {
    var normalized = normalize(productName);
    if (!normalized || !categoryId || !uid() || !db()) return Promise.resolve();
    state.classificationRules[normalized] = categoryId;
    state.classificationRulesLoaded = true;
    var update = {};
    update["shoppingCategoryRules." + classificationRuleKey(normalized)] = {
      product: normalized,
      categoryId: categoryId,
      updatedAt: firebase.firestore.FieldValue.serverTimestamp()
    };
    return db().collection("users").doc(uid()).set(update, {merge:true});
  }

  function applyEmbeddedItems(items) {
    state.items = normalizeEmbeddedItems(items);
    state.itemsLoaded = true;
    if (state.list) {
      state.list.items = state.items.slice();
      state.list.itemCount = state.items.length;
      state.list.doneCount = state.items.filter(function (x) { return !!x.done; }).length;
    }
    renderCurrent();
  }

  // A lista completa fica no documento principal. Assim, todos os usuários
  // acompanham o mesmo snapshot em tempo real e as alterações usam transações,
  // evitando perda quando duas pessoas editam ao mesmo tempo.
  function subscribeItems() { return; }



  function subscribeList(id) {
    if (state.unsubList) { state.unsubList(); state.unsubList = null; }
    if (state.unsubItems) { state.unsubItems(); state.unsubItems = null; }
    state.listId = id;
    state.list = null;
    state.items = [];
    state.itemsLoaded = false;

    if (!id || !db() || !uid()) {
      renderCurrent();
      return;
    }

    renderLoading("Abrindo lista...");
    var listId = id;
    var ref = db().collection("shoppingLists").doc(id);

    state.unsubList = ref.onSnapshot(function (snap) {
      if (state.listId !== listId) return;

      if (!snap.exists) {
        state.list = null;
        state.items = [];
        state.itemsLoaded = false;
        renderLoading("Esta lista não existe ou foi removida.");
        return;
      }

      var data = snap.data() || {};
      data.id = snap.id;
      data._storedItemCount = Number(data.itemCount || 0);
      data._storedDoneCount = Number(data.doneCount || 0);
      state.list = data;

      var members = Array.isArray(data.memberIds) ? data.memberIds : [];
      if (members.indexOf(uid()) === -1) {
        state.items = [];
        state.itemsLoaded = false;
        renderCurrent();
        return;
      }

      if (!Object.prototype.hasOwnProperty.call(data, "items")) {
        renderLoading("Sincronizando itens da lista...");
        migrateLegacyItems(listId, ref, data).then(function (items) {
          if (state.listId !== listId || items === null) return;
          applyEmbeddedItems(items);
          if (!items.length) {
            cleanupEmptyList(listId).then(function (deleted) {
              if (!deleted || state.listId !== listId) return;
              toast("Lista vazia excluída automaticamente.");
            }).catch(function (error) {
              console.error("Resolvei auto-delete empty list:", error);
            });
          }
        });
        return;
      }

      var items = stateFromEmbeddedList(data);
      applyEmbeddedItems(items);

      // Listas sem itens são inválidas e devem desaparecer automaticamente.
      if (!items.length && state.listId === listId) {
        cleanupEmptyList(listId).then(function (deleted) {
          if (!deleted || state.listId !== listId) return;
          toast("Lista vazia excluída automaticamente.");
          if (state.unsubList) { state.unsubList(); state.unsubList = null; }
          state.listId = null;
          state.list = null;
          state.items = [];
          state.itemsLoaded = false;
          goList("");
        }).catch(function (error) {
          console.error("Resolvei auto-delete empty list:", error);
        });
      }
    }, function (error) {
      console.error("Resolvei shopping list:", error);
      renderLoading("Não foi possível abrir esta lista. " + (error.message || "Verifique o login e o link compartilhado."));
    });
  }



  function subscribeLists() {
    if (state.unsubLists) { state.unsubLists(); state.unsubLists = null; }
    if (!db() || !uid()) return;
    state.unsubLists = db().collection("shoppingLists")
      .where("memberIds", "array-contains", uid())
      .onSnapshot(function (snap) {
        state.lists = snap.docs.map(function (d) {
          var x = d.data() || {};
          x.id = d.id;
          return x;
        }).sort(sortLists);
        if (!state.listId) renderCurrent();
      }, function (error) {
        console.error("Resolvei shopping lists:", error);
      });
  }

  function createList() {
    var titleInput = document.getElementById("shoppingTitle");
    var input = document.getElementById("shoppingInput");
    var msg = document.getElementById("shoppingHomeMsg");
    var title = (titleInput ? titleInput.value.trim() : "") || "Compras";
    var parsed = parseListText(input ? input.value : "");

    if (!parsed.length) {
      if (msg) { msg.hidden = false; msg.textContent = "Digite pelo menos um produto para organizar a lista."; }
      return;
    }
    if (!db() || !uid()) {
      if (msg) { msg.hidden = false; msg.textContent = "Faça login para criar uma lista compartilhada."; }
      return;
    }

    var ref = db().collection("shoppingLists").doc();
    var now = Date.now();
    var initialItems = parsed.map(function (item, index) {
      return {
        id: ref.id + "-item-" + index + "-" + Math.random().toString(36).slice(2, 8),
        raw: item.raw,
        name: item.name,
        brand: item.brand || "",
        qty: item.qty,
        unit: item.unit,
        categoryId: item.categoryId,
        done: false,
        position: index,
        createdBy: uid(),
        createdAt: now,
        updatedAt: now
      };
    });

    var base = {
      title: title,
      ownerId: uid(),
      memberIds: [uid()],
      shareEnabled: true,
      items: initialItems,
      createdAt: firebase.firestore.FieldValue.serverTimestamp(),
      updatedAt: firebase.firestore.FieldValue.serverTimestamp(),
      itemCount: initialItems.length,
      doneCount: 0,
      schemaVersion: 2
    };

    var button = document.querySelector('[data-action="create-list"]');
    if (button) { button.disabled = true; button.textContent = "Organizando..."; }

    ref.set(base).then(function () {
      state.list = Object.assign({}, base, { id: ref.id, items: initialItems.slice(), memberIds: [uid()] });
      state.listId = ref.id;
      state.items = initialItems.slice();
      state.itemsLoaded = true;
      goList(ref.id);
    }).catch(function (error) {
      console.error("Resolvei create list:", error);
      if (msg) { msg.hidden = false; msg.textContent = "Não foi possível criar a lista: " + (error.message || "erro desconhecido."); }
    }).finally(function () {
      if (button) { button.disabled = false; button.textContent = "🛒 Organizar minha lista"; }
    });
  }



  function addBulkItems() {
    var input = document.getElementById("shoppingBulkInput");
    var raw = input ? input.value.trim() : "";
    if (!raw) {
      toast("Cole ou digite pelo menos um produto.");
      if (input) input.focus();
      return;
    }
    if (!state.listId || !uid() || !db()) {
      toast("Sua sessão não está pronta. Entre novamente no Resolvei.");
      return;
    }

    var lines = raw.split(/\r?\n/).map(function (x) { return x.trim(); }).filter(Boolean);
    var parsed = [];
    lines.forEach(function (line) {
      parseListText(line).forEach(function (item) {
        if (item && item.name) parsed.push(item);
      });
    });

    if (!parsed.length) {
      toast("Não encontrei produtos nessa lista.");
      return;
    }

    var listRef = db().collection("shoppingLists").doc(state.listId);
    var button = document.querySelector('[data-action="add-bulk"]');
    if (button) { button.disabled = true; button.textContent = "Adicionando..."; }

    var now = Date.now();
    db().runTransaction(function (tx) {
      return tx.get(listRef).then(function (snap) {
        if (!snap.exists) throw new Error("Lista não encontrada.");
        var data = snap.data() || {};
        var members = Array.isArray(data.memberIds) ? data.memberIds : [];
        if (members.indexOf(uid()) === -1) throw new Error("Você não participa desta lista.");
        var current = normalizeEmbeddedItems(data.items);
        var start = current.length;
        var additions = parsed.map(function (item, index) {
          return {
            id: state.listId + "-item-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8) + "-" + index,
            raw: item.raw,
            name: item.name,
            brand: item.brand || "",
            qty: item.qty,
            unit: item.unit,
            categoryId: item.categoryId,
            done: false,
            position: start + index,
            createdBy: uid(),
            createdAt: now,
            updatedAt: now
          };
        });
        var all = current.concat(additions);
        tx.update(listRef, {
          items: all,
          itemCount: all.length,
          doneCount: all.filter(function (x) { return !!x.done; }).length,
          updatedAt: firebase.firestore.FieldValue.serverTimestamp()
        });
        return all;
      });
    }).then(function (all) {
      applyEmbeddedItems(all);
      input.value = "";
      toast("✅ " + parsed.length + " " + (parsed.length === 1 ? "produto adicionado." : "produtos adicionados."));
    }).catch(function (error) {
      console.error("Resolvei add bulk:", error);
      toast("Não foi possível adicionar os produtos. " + (error.message || "Verifique sua conexão."));
    }).finally(function () {
      if (button) { button.disabled = false; button.textContent = "Adicionar todos"; }
    });
  }



  function addItem() {
    var input = document.getElementById("shoppingAddInput");
    if (!input) return;

    var raw = input.value.trim();
    if (!raw) {
      toast("Digite o nome do produto.");
      input.focus();
      return;
    }
    if (!state.listId || !uid() || !db()) {
      toast("Sua sessão não está pronta. Entre novamente no Resolvei.");
      return;
    }

    var parsed = parseShoppingLine(raw);
    if (!parsed || !parsed.name) {
      toast("Não consegui identificar esse produto. Tente escrever de outra forma.");
      return;
    }

    var listId = state.listId;
    var listRef = db().collection("shoppingLists").doc(listId);
    var button = document.querySelector('[data-action="add-item"]');
    if (button) { button.disabled = true; button.textContent = "Adicionando..."; }

    db().runTransaction(function (tx) {
      return tx.get(listRef).then(function (snap) {
        if (!snap.exists) throw new Error("Lista não encontrada.");
        var data = snap.data() || {};
        var members = Array.isArray(data.memberIds) ? data.memberIds : [];
        if (members.indexOf(uid()) === -1) throw new Error("Você não participa desta lista.");

        var current = normalizeEmbeddedItems(data.items);
        var item = {
          id: listId + "-item-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10),
          raw: parsed.raw,
          name: parsed.name,
          brand: parsed.brand || "",
          qty: parsed.qty,
          unit: parsed.unit,
          categoryId: parsed.categoryId,
          done: false,
          position: current.length,
          createdBy: uid(),
          createdAt: Date.now(),
          updatedAt: Date.now()
        };
        var all = current.concat([item]);
        tx.update(listRef, {
          items: all,
          itemCount: all.length,
          doneCount: all.filter(function (x) { return !!x.done; }).length,
          updatedAt: firebase.firestore.FieldValue.serverTimestamp()
        });
        return all;
      });
    }).then(function (all) {
      applyEmbeddedItems(all);
      input.value = "";
      input.focus();
      toast("✅ Produto adicionado à lista.");
    }).catch(function (error) {
      console.error("Resolvei add item:", error);
      var detail = error && error.code ? error.code + ": " : "";
      toast("Não foi possível adicionar. " + detail + (error.message || "Verifique sua conexão."));
    }).finally(function () {
      if (button) { button.disabled = false; button.textContent = "＋ Adicionar"; }
    });
  }



  function toggleItem(id, done) {
    if (!state.listId || !id || !uid() || !db()) return;
    var listRef = db().collection("shoppingLists").doc(state.listId);
    db().runTransaction(function (tx) {
      return tx.get(listRef).then(function (snap) {
        if (!snap.exists) throw new Error("Lista não encontrada.");
        var data = snap.data() || {};
        var members = Array.isArray(data.memberIds) ? data.memberIds : [];
        if (members.indexOf(uid()) === -1) throw new Error("Você não participa desta lista.");
        var items = normalizeEmbeddedItems(data.items);
        var found = false;
        items = items.map(function (item) {
          if (item.id !== id) return item;
          found = true;
          return Object.assign({}, item, {done: !!done, updatedAt: Date.now()});
        });
        if (!found) throw new Error("Item não encontrado.");
        tx.update(listRef, {
          items: items,
          itemCount: items.length,
          doneCount: items.filter(function (x) { return !!x.done; }).length,
          updatedAt: firebase.firestore.FieldValue.serverTimestamp()
        });
        return items;
      });
    }).then(applyEmbeddedItems).catch(function (error) {
      toast("Não foi possível atualizar o item.");
      console.error("Resolvei toggle item:", error);
    });
  }



  function editItem(id) {
    if (!state.items.some(function (x) { return x.id === id; })) return;
    state.editingId = id;
    renderList();
    setTimeout(function () {
      var input = document.querySelector('[data-item-row="' + CSS.escape(id) + '"] [data-edit-name]');
      if (input) { input.focus(); input.select(); }
    }, 0);
  }

  function cancelEdit() {
    state.editingId = null;
    renderList();
  }

  function saveEditItem(id) {
    var row = document.querySelector('[data-item-row="' + CSS.escape(id) + '"]');
    if (!row || !state.listId || !uid() || !db()) return;
    var name = row.querySelector('[data-edit-name]')?.value?.trim() || "";
    var qty = parseNumber(row.querySelector('[data-edit-qty]')?.value);
    var unit = row.querySelector('[data-edit-unit]')?.value || "un.";
    var selectedCategoryId = row.querySelector('[data-edit-category]')?.value || "";
    if (!name || qty <= 0) {
      toast("Informe um produto e uma quantidade válida.");
      return;
    }

    var brandInfo = extractBrand(name);
    var productName = brandInfo.product;
    var category = categoryById(selectedCategoryId || categoryFor(productName).id);
    var listRef = db().collection("shoppingLists").doc(state.listId);

    db().runTransaction(function (tx) {
      return tx.get(listRef).then(function (snap) {
        if (!snap.exists) throw new Error("Lista não encontrada.");
        var data = snap.data() || {};
        var members = Array.isArray(data.memberIds) ? data.memberIds : [];
        if (members.indexOf(uid()) === -1) throw new Error("Você não participa desta lista.");
        var items = normalizeEmbeddedItems(data.items).map(function (item) {
          if (item.id !== id) return item;
          return Object.assign({}, item, {
            name: titleCase(productName),
            brand: brandInfo.brand || "",
            qty: qty,
            unit: unit,
            raw: name + " " + formatQty(qty) + " " + unit,
            categoryId: category.id,
            updatedAt: Date.now()
          });
        });
        tx.update(listRef, {items:items,updatedAt:firebase.firestore.FieldValue.serverTimestamp()});
        return items;
      });
    }).then(function (items) {
      applyEmbeddedItems(items);
      return learnClassification(productName, category.id).then(function () {
        state.editingId = null;
        toast("✅ Item salvo. O Resolvei vai lembrar essa classificação.");
      });
    }).catch(function (error) {
      toast("Não foi possível editar o item.");
      console.error("Resolvei edit item:", error);
    });
  }



  function suggestAiCategory(id) {
    var item = state.items.find(function (x) { return x.id === id; });
    var row = document.querySelector('[data-item-row="' + CSS.escape(id) + '"]');
    if (!item || !row) return;
    var nameInput = row.querySelector("[data-edit-name]");
    var categorySelect = row.querySelector("[data-edit-category]");
    var msg = row.querySelector("[data-ai-msg]");
    var name = nameInput ? nameInput.value.trim() : item.name;
    if (!name || !categorySelect) return;

    var button = row.querySelector('[data-action="ai-category"]');
    if (button) { button.disabled = true; button.textContent = "⏳ Analisando..."; }
    if (msg) { msg.hidden = false; msg.textContent = "Consultando a IA para sugerir o setor..."; }

    resolveiToken().then(function (token) {
      return fetch("/api/shopping/classify", {
        method: "POST",
        headers: {"Content-Type":"application/json","Authorization":"Bearer " + token},
        body: JSON.stringify({item:name})
      });
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) throw new Error(data.detail || "Não foi possível consultar a IA.");
        return data;
      });
    }).then(function (data) {
      if (data.categoryId) categorySelect.value = data.categoryId;
      if (msg) msg.hidden = false, msg.textContent = "✨ Sugestão: " + (data.categoryTitle || data.categoryId) + (data.confidence ? " · confiança " + Math.round(Number(data.confidence) * 100) + "%" : "") + (data.reason ? " — " + data.reason : "");
    }).catch(function (error) {
      if (msg) { msg.hidden = false; msg.textContent = "⚠️ " + (error.message || "A IA não conseguiu classificar."); }
      console.error("Resolvei AI shopping category:", error);
    }).finally(function () {
      if (button) { button.disabled = false; button.textContent = "✨ Sugerir com IA"; }
    });
  }

  function deleteItem(id) {
    if (!window.confirm("Excluir este produto da lista?")) return;
    if (!state.listId || !uid() || !db()) return;
    var listRef = db().collection("shoppingLists").doc(state.listId);

    db().runTransaction(function (tx) {
      return tx.get(listRef).then(function (snap) {
        if (!snap.exists) throw new Error("Lista não encontrada.");
        var data = snap.data() || {};
        if ((data.memberIds || []).indexOf(uid()) === -1) throw new Error("Você não participa desta lista.");
        var items = normalizeEmbeddedItems(data.items).filter(function (item) { return item.id !== id; });
        tx.update(listRef, {
          items: items,
          itemCount: items.length,
          doneCount: items.filter(function (x) { return !!x.done; }).length,
          updatedAt: firebase.firestore.FieldValue.serverTimestamp()
        });
        return items;
      });
    }).then(function (items) {
      applyEmbeddedItems(items);
      toast("Item excluído.");
    }).catch(function (error) {
      toast("Não foi possível excluir o item.");
      console.error("Resolvei delete item:", error);
    });
  }



  function clearDone() {
    var done = state.items.filter(function (x) { return x.done; });
    if (!done.length) return;
    if (!window.confirm("Remover todos os itens já marcados como comprados?")) return;
    if (!state.listId || !uid() || !db()) return;

    var listRef = db().collection("shoppingLists").doc(state.listId);
    db().runTransaction(function (tx) {
      return tx.get(listRef).then(function (snap) {
        if (!snap.exists) throw new Error("Lista não encontrada.");
        var data = snap.data() || {};
        if ((data.memberIds || []).indexOf(uid()) === -1) throw new Error("Você não participa desta lista.");
        var items = normalizeEmbeddedItems(data.items).filter(function (item) { return !item.done; });
        tx.update(listRef, {
          items: items,
          itemCount: items.length,
          doneCount: 0,
          updatedAt: firebase.firestore.FieldValue.serverTimestamp()
        });
        return items;
      });
    }).then(function (items) {
      applyEmbeddedItems(items);
      toast("Itens comprados removidos.");
      if (!items.length) cleanupEmptyList(state.listId).catch(function (error) {
        console.error("Resolvei cleanup after clear:", error);
      });
    }).catch(function (error) {
      toast("Não foi possível limpar os itens.");
      console.error("Resolvei clear done:", error);
    });
  }



  function renameList() {
    state.editingTitle = true;
    renderList();
    setTimeout(function () {
      var input = document.getElementById("shoppingTitleEdit");
      if (input) { input.focus(); input.select(); }
    }, 0);
  }

  function cancelTitleEdit() {
    state.editingTitle = false;
    renderList();
  }

  function saveTitle() {
    var input = document.getElementById("shoppingTitleEdit");
    var value = input ? input.value.trim().slice(0, 80) : "";
    if (!value) {
      toast("Digite um nome para a lista.");
      if (input) input.focus();
      return;
    }
    db().collection("shoppingLists").doc(state.listId).update({
      title: value,
      updatedAt: firebase.firestore.FieldValue.serverTimestamp()
    }).then(function () {
      state.editingTitle = false;
      toast("✅ Nome da lista atualizado.");
    }).catch(function (error) {
      toast("Não foi possível renomear a lista.");
      console.error(error);
    });
  }

  function share() {
    if (!state.listId) return;
    var link = shareLink();
    copyText(link).then(function () {
      toast("Link da lista copiado. Envie para a outra pessoa.");
    });
  }

  function joinList() {
    if (!state.listId || !uid() || !db()) return;
    var button = document.querySelector('[data-action="join-list"]');
    var msg = document.getElementById("shoppingJoinMsg");
    if (button) { button.disabled = true; button.textContent = "Entrando..."; }
    db().collection("shoppingLists").doc(state.listId).update({
      memberIds: firebase.firestore.FieldValue.arrayUnion(uid()),
      updatedAt: firebase.firestore.FieldValue.serverTimestamp()
    }).then(function () {
      toast("Você entrou na lista.");
    }).catch(function (error) {
      console.error("Resolvei join list:", error);
      if (msg) { msg.hidden = false; msg.textContent = "Não foi possível entrar nesta lista. O link pode ter sido revogado."; }
    }).finally(function () {
      if (button) { button.disabled = false; button.textContent = "Entrar nesta lista"; }
    });
  }

  function deleteList(id) {
    var target = state.lists.find(function (x) { return x.id === id; }) || (state.listId === id ? state.list : null);
    if (!target) return;
    var u = user();
    if (!u || target.ownerId !== u.uid) {
      toast("Somente quem criou a lista pode excluí-la.");
      return;
    }
    if (!window.confirm("Excluir a lista " + (target.title || "de compras") + "? Esta ação não pode ser desfeita.")) return;

    var ref = db().collection("shoppingLists").doc(id);
    ref.collection("items").get().then(function (snap) {
      var batch = db().batch();
      snap.docs.forEach(function (d) { batch.delete(d.ref); });
      batch.delete(ref);
      return batch.commit();
    }).then(function () {
      toast("Lista excluída.");
      if (state.listId === id) {
        if (state.unsubList) { state.unsubList(); state.unsubList = null; }
        if (state.unsubItems) { state.unsubItems(); state.unsubItems = null; }
        state.listId = null;
        state.list = null;
        state.items = [];
        state.itemsLoaded = false;
        goList("");
      }
    }).catch(function (error) {
      console.error("Resolvei delete list:", error);
      toast("Não foi possível excluir a lista.");
    });
  }

  function reuseList(id) {
    if (!db() || !uid()) return;
    var source = state.lists.find(function (x) { return x.id === id; }) || (state.listId === id ? state.list : null);
    if (!source) return;

    var cloneFrom = function (items) {
      var sourceItems = normalizeEmbeddedItems(items);
      if (!sourceItems.length) {
        toast("Esta lista não possui itens para reaproveitar.");
        return Promise.resolve();
      }

      var ref = db().collection("shoppingLists").doc();
      var now = Date.now();
      var clonedItems = sourceItems.map(function (item, index) {
        return Object.assign({}, item, {
          id: ref.id + "-item-" + index + "-" + Math.random().toString(36).slice(2, 8),
          done: false,
          position: index,
          createdBy: uid(),
          createdAt: now,
          updatedAt: now
        });
      });
      var base = {
        title: (source.title || "Lista de compras") + " — nova",
        ownerId: uid(),
        memberIds: [uid()],
        shareEnabled: true,
        items: clonedItems,
        createdAt: firebase.firestore.FieldValue.serverTimestamp(),
        updatedAt: firebase.firestore.FieldValue.serverTimestamp(),
        itemCount: clonedItems.length,
        doneCount: 0,
        schemaVersion: 2,
        reusedFromId: id
      };

      return ref.set(base).then(function () {
        state.listId = ref.id;
        state.list = Object.assign({}, base, {id:ref.id});
        state.items = clonedItems.slice();
        state.itemsLoaded = true;
        goList(ref.id);
        toast("Nova lista criada a partir da lista anterior.");
      });
    };

    var sourceItems = Array.isArray(source.items) ? source.items : [];
    if (sourceItems.length) return cloneFrom(sourceItems);

    return db().collection("shoppingLists").doc(id).collection("items").get().then(function (snap) {
      var items = snap.docs.map(function (d) {
        var x = d.data() || {};
        x.id = d.id;
        return x;
      }).sort(sortItems);
      return cloneFrom(items);
    }).catch(function (error) {
      console.error("Resolvei fetch reuse items:", error);
      toast("Não foi possível carregar os itens da lista.");
    });
  }



  function newList() {
    goList("");
    state.list = null;
    state.items = [];
    state.itemsLoaded = false;
    renderHome();
  }

  function bindEvents() {
    var shell = document.getElementById("shoppingTool");
    if (!shell || shell.dataset.bound === "1") return;
    shell.dataset.bound = "1";
    state.eventsBound = true;

    shell.addEventListener("click", function (event) {
      var el = event.target.closest("[data-action]");
      if (!el) return;
      var action = el.getAttribute("data-action");
      if (action === "create-list") createList();
      else if (action === "open-list") subscribeList(el.getAttribute("data-list-id"));
      else if (action === "back-home") newList();
      else if (action === "new-list") newList();
      else if (action === "add-item") addItem();
      else if (action === "add-bulk") addBulkItems();
      else if (action === "toggle-market") { state.marketMode = !state.marketMode; renderList(); }
      else if (action === "toggle-item") {}
      else if (action === "edit-item") editItem(el.getAttribute("data-item-id"));
      else if (action === "ai-category") suggestAiCategory(el.getAttribute("data-item-id"));
      else if (action === "save-edit-item") saveEditItem(el.getAttribute("data-item-id"));
      else if (action === "cancel-edit") cancelEdit();
      else if (action === "delete-item") deleteItem(el.getAttribute("data-item-id"));
      else if (action === "clear-done") clearDone();
      else if (action === "rename-list") renameList();
      else if (action === "save-title") saveTitle();
      else if (action === "cancel-title") cancelTitleEdit();
      else if (action === "share") share();
      else if (action === "join-list") joinList();
      else if (action === "delete-list") deleteList(el.getAttribute("data-list-id"));
      else if (action === "reuse-list") reuseList(el.getAttribute("data-list-id"));
      else if (action === "reuse-current-list") reuseList(state.listId);
      else if (action === "delete-current-list") deleteList(state.listId);
    });

    shell.addEventListener("change", function (event) {
      var el = event.target.closest('[data-action="toggle-item"]');
      if (el) toggleItem(el.getAttribute("data-item-id"), el.checked);
    });

    shell.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") return;
      var input = event.target.closest("#shoppingAddInput");
      if (input) { event.preventDefault(); addItem(); return; }
      var title = event.target.closest("#shoppingTitleEdit");
      if (title) { event.preventDefault(); saveTitle(); }
    });
  }

  function initAuthBinding() {
    if (state.authBound || !window.firebase || !firebase.apps.length) return;
    try {
      firebase.auth().onAuthStateChanged(function (firebaseUser) {
        if (firebaseUser) subscribeClassificationRules();
        else {
          state.classificationRules = {};
          state.classificationRulesLoaded = false;
          state.classificationRulesUserId = "";
          if (state.unsubClassificationRules) { state.unsubClassificationRules(); state.unsubClassificationRules = null; }
        }
        subscribeLists();
        var requestedId = getQueryListId();
        if (requestedId) {
          if (state.listId !== requestedId || !state.list) subscribeList(requestedId);
          else renderCurrent();
        } else {
          if (state.listId) {
            if (!state.list || state.listId !== requestedId) {
              if (state.unsubList) { state.unsubList(); state.unsubList = null; }
              if (state.unsubItems) { state.unsubItems(); state.unsubItems = null; }
              state.listId = null;
              state.list = null;
              state.items = [];
            }
          }
          renderCurrent();
        }
      });
      state.authBound = true;
    } catch (e) {
      console.error("Resolvei shopping auth binding:", e);
    }
  }

  function init() {
    var currentRoot = root();
    if (!currentRoot) return;
    bindEvents();
    setTimeout(initAuthBinding, 0);

    var currentUser = user();
    if (!currentUser) {
      renderAuthRequired();
      return;
    }

    subscribeLists();
    subscribeClassificationRules();
    var requestedId = getQueryListId();
    if (requestedId) {
      if (state.listId !== requestedId) subscribeList(requestedId);
      else renderCurrent();
    } else if (state.listId) {
      subscribeList(state.listId);
    } else {
      renderHome();
    }
  }

  window.resolveiShoppingAppMarkup = function () {
    setTimeout(function () { init(); }, 0);
    return '<div id="shoppingTool" class="shopping-tool-wrap"><div id="shoppingState"></div></div>';
  };

  window.resolveiShoppingInit = init;
})();
