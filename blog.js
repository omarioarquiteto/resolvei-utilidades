(function () {
  "use strict";

  const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[ch]));
  const $ = (selector, root = document) => root.querySelector(selector);
  let isAdmin = false;
  let adminCheckSequence = 0;
  let adminPosts = [];
  let editingSlug = null;
  let slugWasEdited = false;
  let savedEditorRange = null;

  function currentUser() {
    try { return window.firebase?.auth?.().currentUser || null; } catch (_) { return null; }
  }

  async function api(path, options = {}, authRequired = false, userOverride = null) {
    const headers = new Headers(options.headers || {});
    const user = userOverride || currentUser();
    if (authRequired) {
      if (!user) throw new Error("Entre na sua conta do Resolvei para continuar.");
      headers.set("Authorization", "Bearer " + await user.getIdToken());
    }
    const response = await fetch(path, { ...options, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.error || "Não foi possível concluir a solicitação.");
    return data;
  }

  function dateLabel(value) {
    if (!value) return "Publicação recente";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Publicação recente";
    return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "long", year: "numeric" }).format(date);
  }

  function safeImage(value) {
    try {
      const url = new URL(String(value || ""), location.origin);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_) {
      return "";
    }
  }

  function imageMarkup(post, className) {
    const url = safeImage(post.coverImage);
    return url
      ? '<img class="' + className + '" src="' + esc(url) + '" alt="' + esc(post.title || "Imagem do review") + '" loading="lazy">'
      : '<div class="' + className + ' blog-image-placeholder" aria-hidden="true"><span>RESOLVEI</span><b>REVIEWS</b></div>';
  }

  function articleUrl(slug) {
    return "/blog/" + encodeURIComponent(slug || "");
  }

  function postCard(post) {
    return '<article class="blog-post-card">' +
      '<a class="blog-post-card-image" href="' + articleUrl(post.slug) + '">' + imageMarkup(post, "blog-card-image") + '</a>' +
      '<div class="blog-post-card-copy"><span class="blog-category-label">' + esc(post.category || "Review") + '</span>' +
      '<h3><a href="' + articleUrl(post.slug) + '">' + esc(post.title) + '</a></h3>' +
      '<p>' + esc(post.excerpt || "") + '</p>' +
      '<time>' + esc(dateLabel(post.publishedAt || post.createdAt)) + '</time></div></article>';
  }

  function renderHome(root, posts) {
    const categories = [...new Set(posts.map(post => String(post.category || "").trim()).filter(Boolean))];
    const featured = posts[0];
    const sidePosts = posts.slice(1, 5);
    const adminAction = '<a class="blog-editor-shortcut" href="#/blogger"' + (isAdmin ? "" : " hidden") + '>✍️ Escrever review <span>→</span></a>';
    const featureMarkup = featured
      ? '<section class="blog-lead-layout"><article class="blog-lead-card">' +
        '<a class="blog-lead-image" href="' + articleUrl(featured.slug) + '">' + imageMarkup(featured, "blog-lead-img") + '</a>' +
        '<div class="blog-lead-copy"><span class="blog-category-label">' + esc(featured.category || "Review") + ' · DESTAQUE</span>' +
        '<h2><a href="' + articleUrl(featured.slug) + '">' + esc(featured.title) + '</a></h2>' +
        '<p>' + esc(featured.excerpt || "") + '</p><div class="blog-meta"><time>' + esc(dateLabel(featured.publishedAt || featured.createdAt)) + '</time><a href="' + articleUrl(featured.slug) + '">Leia o review <b>→</b></a></div></div></article>' +
        '<aside class="blog-latest-panel"><div class="blog-panel-heading"><span>NO RADAR</span><h2>Mais recentes</h2></div>' +
        (sidePosts.length ? sidePosts.map((post, index) =>
          '<article class="blog-latest-item"><span class="blog-latest-number">' + String(index + 2).padStart(2, "0") + '</span><div><span class="blog-category-label">' + esc(post.category || "Review") + '</span><h3><a href="' + articleUrl(post.slug) + '">' + esc(post.title) + '</a></h3><time>' + esc(dateLabel(post.publishedAt || post.createdAt)) + '</time></div></article>'
        ).join("") : '<p class="blog-latest-empty">Novos reviews aparecerão aqui.</p>') +
        '</aside></section>'
      : '<section class="blog-welcome"><div class="blog-welcome-mark">R</div><div><span class="blog-kicker">UM NOVO OLHAR SOBRE PRODUTOS</span><h2>Reviews para ajudar você a escolher melhor.</h2><p>Celulares, eletrodomésticos, tecnologia e produtos do dia a dia. As análises publicadas aparecerão aqui, com fotos, pontos positivos, limitações e nossa avaliação.</p>' +
        (isAdmin ? '<a class="btn primary" href="#/blogger">Criar o primeiro review →</a>' : '<span class="blog-welcome-note">Estamos preparando este espaço editorial.</span>') +
        '</div></section>';

    root.innerHTML =
      '<div class="blog-home">' +
        '<header class="blog-home-heading"><div><span class="blog-kicker">CONTEÚDO · ANÁLISES · GUIAS DE COMPRA</span><h1>Reviews Resolvei</h1><p>Informação prática para comprar com mais confiança.</p></div>' + adminAction + '</header>' +
        '<nav class="blog-topic-nav" aria-label="Categorias do blog"><button class="active" type="button" data-blog-filter="*">Todos os reviews</button>' +
          categories.map(category => '<button type="button" data-blog-filter="' + esc(category) + '">' + esc(category) + '</button>').join("") +
        '</nav>' +
        featureMarkup +
        (posts.length
          ? '<section class="blog-feed-section"><div class="blog-section-heading"><div><span class="blog-kicker">DIRETO DA REDAÇÃO</span><h2>Últimos reviews</h2></div><span class="blog-result-count">' + posts.length + ' publicação(ões)</span></div>' +
            '<div class="blog-post-grid" id="blogPostGrid">' + posts.map(postCard).join("") + '</div></section>'
          : '<section class="blog-empty-feed"><h2>O próximo review começa aqui.</h2><p>Quando um artigo for publicado, ele aparecerá nesta página automaticamente.</p></section>') +
        '<footer class="blog-home-footer"><span>RESOLVEI · REVIEWS</span><span>Escolhas melhores começam com informação.</span></footer>' +
      '</div>';

    root.querySelectorAll("[data-blog-filter]").forEach(button => {
      button.addEventListener("click", () => {
        root.querySelectorAll("[data-blog-filter]").forEach(item => item.classList.toggle("active", item === button));
        const category = button.dataset.blogFilter;
        const filtered = category === "*" ? posts : posts.filter(post => (post.category || "") === category);
        const grid = $("#blogPostGrid", root);
        if (grid) grid.innerHTML = filtered.length ? filtered.map(postCard).join("") : '<div class="blog-empty-feed">Nenhum review publicado nesta categoria.</div>';
        const count = $(".blog-result-count", root);
        if (count) count.textContent = filtered.length + " publicação(ões)";
      });
    });
  }

  async function initHome() {
    const root = $("#resolveiBlogHome");
    if (!root || root.dataset.loaded === "1") return;
    root.dataset.loaded = "1";
    try {
      const data = await api("/api/blog/posts");
      renderHome(root, Array.isArray(data.posts) ? data.posts : []);
    } catch (error) {
      root.innerHTML = '<div class="blog-load-error"><strong>Não foi possível carregar os reviews.</strong><p>' + esc(error.message) + '</p><button class="btn" type="button" id="blogRetry">Tentar novamente</button></div>';
      $("#blogRetry", root)?.addEventListener("click", () => { root.dataset.loaded = ""; initHome(); });
    }
  }

  async function initArticle() {
    const root = $("#resolveiBlogArticle");
    if (!root || root.dataset.loaded === "1") return;
    root.dataset.loaded = "1";
    const slug = root.dataset.slug || "";
    try {
      const data = await api("/api/blog/posts/" + encodeURIComponent(slug));
      const post = data.post;
      if (!post) throw new Error("Este review não está disponível.");
      document.title = post.seoTitle || post.title + " | Reviews Resolvei";
      const description = $("meta[name='description']");
      if (description) description.setAttribute("content", post.seoDescription || post.excerpt || post.title);
      const image = safeImage(post.coverImage);
      const imageBlock = image ? '<img class="blog-article-cover" src="' + esc(image) + '" alt="' + esc(post.title) + '">' : "";
      const productUrl = safeImage(post.productLink);
      const productCta = productUrl
        ? '<aside class="blog-product-cta"><div><span>PRODUTO DO REVIEW</span><strong>Consulte preço e disponibilidade</strong></div><a href="' + esc(productUrl) + '" target="_blank" rel="sponsored nofollow noopener">Ver oferta →</a></aside>'
        : "";
      root.innerHTML =
        '<article class="blog-article">' +
          '<a class="blog-back-link" href="/">← Todos os reviews</a>' +
          '<header class="blog-article-header"><span class="blog-category-label">' + esc(post.category || "Review") + '</span>' +
            '<h1>' + esc(post.title) + '</h1><p class="blog-article-excerpt">' + esc(post.excerpt || "") + '</p>' +
            '<div class="blog-article-byline"><span>Por Equipe Resolvei</span><time>' + esc(dateLabel(post.publishedAt || post.createdAt)) + '</time></div></header>' +
          imageBlock +
          productCta +
          '<div class="blog-article-body">' + (post.bodyHtml || "") + '</div>' +
          '<div class="blog-article-bottom"><a href="/">← Voltar aos reviews</a><span>RESOLVEI · REVIEWS</span></div>' +
        '</article>';
    } catch (error) {
      root.innerHTML = '<div class="blog-load-error"><strong>Review não encontrado.</strong><p>' + esc(error.message) + '</p><a class="btn" href="/">Voltar à página inicial</a></div>';
    }
  }

  function adminShell() {
    return '<div class="blog-admin-page" id="blogAdminPage">' +
      '<header class="blog-admin-header"><div><span class="blog-kicker">ÁREA RESTRITA · ADMINISTRADOR</span><h1>Painel editorial</h1><p>Crie, revise, salve como rascunho e publique os artigos do Blog Resolvei.</p></div><a class="btn" href="/">Ver blog →</a></header>' +
      '<div id="blogAdminMessage" class="blog-admin-message">Verificando autorização...</div>' +
      '<div id="blogAdminWorkspace" class="blog-admin-layout" hidden>' +
        '<aside class="blog-admin-posts"><div class="blog-admin-posts-head"><div><span class="blog-kicker">CONTEÚDO</span><h2>Suas publicações</h2></div><button class="btn primary" type="button" id="blogNewPost">＋ Novo post</button></div>' +
          '<div id="blogAdminPostList" class="blog-admin-post-list"></div></aside>' +
        '<main class="blog-editor-panel"><form id="blogEditorForm">' +
          '<div class="blog-editor-title-row"><div><span class="blog-kicker">EDITOR DE ARTIGOS</span><h2 id="blogEditorHeading">Novo review</h2></div><span id="blogEditorState" class="blog-status-pill">Novo</span></div>' +
          '<div class="blog-editor-fields">' +
            '<label class="blog-field blog-field-full"><span>Título do post</span><input id="blogTitle" maxlength="140" required placeholder="Ex.: Testamos o celular X: vale a pena?"></label>' +
            '<label class="blog-field"><span>Endereço (slug)</span><input id="blogSlug" maxlength="120" required placeholder="review-celular-x"></label>' +
            '<label class="blog-field"><span>Categoria</span><select id="blogCategory"><option>Celulares</option><option>Informática</option><option>Eletrodomésticos</option><option>Casa inteligente</option><option>Áudio e vídeo</option><option>Games</option><option>Guias de compra</option><option>Outros produtos</option></select></label>' +
            '<label class="blog-field blog-field-full"><span>Resumo / linha fina</span><textarea id="blogExcerpt" maxlength="320" rows="3" placeholder="Apresente em poucas linhas o que o leitor vai encontrar neste review."></textarea></label>' +
            '<div class="blog-field blog-field-full"><span>Imagem de capa</span><div class="blog-cover-upload"><input id="blogCoverImage" type="url" placeholder="URL da imagem de capa"><input id="blogCoverFile" type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden><button class="btn" type="button" id="blogCoverUpload">Enviar imagem</button></div><small>Use uma imagem horizontal, de preferência com boa resolução.</small></div>' +
            '<label class="blog-field blog-field-full"><span>Link para consultar ou comprar o produto (opcional)</span><input id="blogProductLink" type="url" placeholder="Cole seu link de afiliado do Mercado Livre ou de outra loja"><small>Quando preenchido, será exibido um botão no artigo para o leitor consultar a oferta. O Resolvei não gera links de afiliado automaticamente.</small></label>' +
            '<div class="blog-field blog-field-full"><span>Conteúdo do artigo</span>' +
              '<div class="blog-editor-toolbar" role="toolbar" aria-label="Formatação do artigo">' +
                '<button type="button" data-blog-command="bold" title="Negrito"><b>B</b></button><button type="button" data-blog-command="italic" title="Itálico"><i>I</i></button><button type="button" data-blog-command="underline" title="Sublinhado"><u>U</u></button>' +
                '<span></span><button type="button" data-blog-command="formatBlock" data-blog-value="h2">Título 2</button><button type="button" data-blog-command="formatBlock" data-blog-value="h3">Título 3</button><button type="button" data-blog-command="formatBlock" data-blog-value="p">Parágrafo</button>' +
                '<span></span><button type="button" data-blog-command="insertUnorderedList">• Lista</button><button type="button" data-blog-command="insertOrderedList">1. Lista</button><button type="button" data-blog-command="formatBlock" data-blog-value="blockquote">Citação</button>' +
                '<span></span><button type="button" id="blogInsertLink">Inserir link</button><button type="button" id="blogInsertImage">Inserir imagem</button><input id="blogInlineFile" type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden>' +
              '</div>' +
              '<div id="blogBodyEditor" class="blog-rich-editor" contenteditable="true" data-placeholder="Comece a escrever seu review aqui. Você pode formatar títulos, parágrafos, listas, citações, links e imagens."></div>' +
              '<small>O conteúdo aceita formatação e imagens. Evite copiar textos de terceiros sem autorização.</small>' +
            '</div>' +
            '<label class="blog-field blog-field-full"><span>Tags (separadas por vírgula)</span><input id="blogTags" placeholder="celular, tecnologia, análise"></label>' +
            '<details class="blog-seo-fields"><summary>Configurações de busca (SEO)</summary><div class="blog-editor-fields">' +
              '<label class="blog-field"><span>Título para buscadores</span><input id="blogSeoTitle" maxlength="160" placeholder="Opcional"></label>' +
              '<label class="blog-field"><span>Descrição para buscadores</span><input id="blogSeoDescription" maxlength="240" placeholder="Opcional"></label>' +
            '</div></details>' +
          '</div>' +
          '<div class="blog-editor-actions"><div><button type="button" class="btn" id="blogPreviewButton">Pré-visualizar</button><button type="button" class="btn danger-outline" id="blogDeleteButton" hidden>Excluir</button></div><div><button type="button" class="btn" id="blogSaveDraft">Salvar rascunho</button><button type="button" class="btn primary" id="blogPublish">Publicar</button></div></div>' +
          '<div id="blogEditorNotice" class="blog-editor-notice" hidden></div>' +
          '<section id="blogEditorPreview" class="blog-editor-preview" hidden></section>' +
        '</form></main>' +
      '</div>' +
    '</div>';
  }

  function slugify(value) {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 120);
  }

  function adminMessage(message, type = "info") {
    const box = $("#blogAdminMessage");
    if (!box) return;
    box.className = "blog-admin-message " + type;
    box.textContent = message;
    box.hidden = false;
  }

  function editorNotice(message, type = "success") {
    const box = $("#blogEditorNotice");
    if (!box) return;
    box.className = "blog-editor-notice " + type;
    box.textContent = message;
    box.hidden = false;
  }

  function renderAdminPostList() {
    const list = $("#blogAdminPostList");
    if (!list) return;
    if (!adminPosts.length) {
      list.innerHTML = '<div class="blog-admin-list-empty">Ainda não há posts. Clique em “Novo post” para começar.</div>';
      return;
    }
    list.innerHTML = adminPosts.map(post =>
      '<button type="button" class="blog-admin-post-item ' + (post.slug === editingSlug ? "active" : "") + '" data-blog-edit="' + esc(post.slug) + '">' +
        '<span class="blog-admin-post-status ' + esc(post.status) + '">' + (post.status === "published" ? "Publicado" : "Rascunho") + '</span>' +
        '<strong>' + esc(post.title || "Sem título") + '</strong><small>' + esc(post.category || "Sem categoria") + ' · ' + esc(dateLabel(post.updatedAt || post.createdAt)) + '</small></button>'
    ).join("");
    list.querySelectorAll("[data-blog-edit]").forEach(button => button.addEventListener("click", () => {
      const post = adminPosts.find(item => item.slug === button.dataset.blogEdit);
      if (post) fillEditor(post);
    }));
  }

  function fillEditor(post = null) {
    editingSlug = post?.slug || null;
    slugWasEdited = !!post;
    $("#blogTitle").value = post?.title || "";
    $("#blogSlug").value = post?.slug || "";
    $("#blogCategory").value = post?.category || "Celulares";
    $("#blogExcerpt").value = post?.excerpt || "";
    $("#blogCoverImage").value = post?.coverImage || "";
    $("#blogProductLink").value = post?.productLink || "";
    $("#blogTags").value = Array.isArray(post?.tags) ? post.tags.join(", ") : "";
    $("#blogSeoTitle").value = post?.seoTitle || "";
    $("#blogSeoDescription").value = post?.seoDescription || "";
    $("#blogBodyEditor").innerHTML = post?.bodyHtml || "";
    $("#blogEditorHeading").textContent = post ? "Editar review" : "Novo review";
    $("#blogEditorState").textContent = post?.status === "published" ? "Publicado" : post ? "Rascunho" : "Novo";
    $("#blogDeleteButton").hidden = !post;
    $("#blogEditorPreview").hidden = true;
    $("#blogPreviewButton").textContent = "Pré-visualizar";
    $("#blogEditorNotice").hidden = true;
    renderAdminPostList();
  }

  async function uploadImage(file) {
    if (!file) return null;
    const form = new FormData();
    form.append("file", file);
    const result = await api("/api/blog/upload", { method: "POST", body: form }, true);
    return result.url;
  }

  function bindAdminEditor() {
    const title = $("#blogTitle");
    const slug = $("#blogSlug");
    title.addEventListener("input", () => {
      if (!slugWasEdited) slug.value = slugify(title.value);
    });
    slug.addEventListener("input", () => { slugWasEdited = true; slug.value = slugify(slug.value); });

    $("#blogNewPost").addEventListener("click", () => fillEditor());
    $("#blogSaveDraft").addEventListener("click", () => savePost("draft"));
    $("#blogPublish").addEventListener("click", () => savePost("published"));
    $("#blogDeleteButton").addEventListener("click", async () => {
      if (!editingSlug || !confirm("Excluir este post permanentemente?")) return;
      try {
        await api("/api/blog/posts/" + encodeURIComponent(editingSlug), { method: "DELETE" }, true);
        adminPosts = adminPosts.filter(post => post.slug !== editingSlug);
        fillEditor();
        editorNotice("Post excluído.", "success");
        renderAdminPostList();
      } catch (error) { editorNotice(error.message, "error"); }
    });

    document.querySelectorAll("[data-blog-command]").forEach(button => button.addEventListener("click", () => {
      const command = button.dataset.blogCommand;
      const value = button.dataset.blogValue || null;
      $("#blogBodyEditor").focus();
      document.execCommand(command, false, value);
    }));

    $("#blogInsertLink").addEventListener("click", () => {
      const url = prompt("Cole o endereço do link (https://...):");
      if (!url) return;
      try {
        const parsed = new URL(url);
        if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
        $("#blogBodyEditor").focus();
        document.execCommand("createLink", false, parsed.href);
      } catch (_) { editorNotice("Informe um endereço HTTP ou HTTPS válido.", "error"); }
    });

    $("#blogInsertImage").addEventListener("click", () => {
      const editor = $("#blogBodyEditor");
      editor.focus();
      const selection = window.getSelection();
      if (selection?.rangeCount) savedEditorRange = selection.getRangeAt(0).cloneRange();
      $("#blogInlineFile").click();
    });

    $("#blogInlineFile").addEventListener("change", async event => {
      const file = event.target.files?.[0];
      if (!file) return;
      try {
        editorNotice("Enviando imagem...", "info");
        const url = await uploadImage(file);
        const editor = $("#blogBodyEditor");
        editor.focus();
        const selection = window.getSelection();
        if (savedEditorRange && selection) {
          selection.removeAllRanges();
          selection.addRange(savedEditorRange);
        }
        document.execCommand("insertHTML", false, '<figure><img src="' + esc(url) + '" alt="' + esc(file.name) + '"><figcaption>' + esc(file.name) + '</figcaption></figure>');
        editorNotice("Imagem inserida no artigo.", "success");
      } catch (error) { editorNotice(error.message, "error"); }
      finally { event.target.value = ""; }
    });

    $("#blogCoverUpload").addEventListener("click", () => $("#blogCoverFile").click());
    $("#blogCoverFile").addEventListener("change", async event => {
      const file = event.target.files?.[0];
      if (!file) return;
      try {
        editorNotice("Enviando imagem de capa...", "info");
        $("#blogCoverImage").value = await uploadImage(file);
        editorNotice("Imagem de capa enviada.", "success");
      } catch (error) { editorNotice(error.message, "error"); }
      finally { event.target.value = ""; }
    });

    $("#blogPreviewButton").addEventListener("click", () => {
      const preview = $("#blogEditorPreview");
      const shouldShow = preview.hidden;
      if (shouldShow) {
        preview.innerHTML = '<article class="blog-article"><header class="blog-article-header"><span class="blog-category-label">' + esc($("#blogCategory").value) + '</span><h1>' + esc($("#blogTitle").value || "Sem título") + '</h1><p class="blog-article-excerpt">' + esc($("#blogExcerpt").value) + '</p></header><div class="blog-article-body">' + $("#blogBodyEditor").innerHTML + '</div></article>';
      }
      preview.hidden = !shouldShow;
      $("#blogPreviewButton").textContent = shouldShow ? "Fechar prévia" : "Pré-visualizar";
      if (shouldShow) preview.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  async function savePost(status) {
    const title = $("#blogTitle").value.trim();
    const slug = slugify($("#blogSlug").value);
    if (title.length < 3) { editorNotice("Informe um título com pelo menos 3 caracteres.", "error"); return; }
    if (slug.length < 3) { editorNotice("O endereço do post precisa ter pelo menos 3 caracteres.", "error"); return; }
    const payload = {
      title, slug, category: $("#blogCategory").value,
      excerpt: $("#blogExcerpt").value.trim(),
      coverImage: $("#blogCoverImage").value.trim(),
      productLink: $("#blogProductLink").value.trim(),
      bodyHtml: $("#blogBodyEditor").innerHTML,
      tags: $("#blogTags").value.split(",").map(tag => tag.trim()).filter(Boolean),
      seoTitle: $("#blogSeoTitle").value.trim(),
      seoDescription: $("#blogSeoDescription").value.trim(),
      status
    };
    if (!payload.bodyHtml.trim()) { editorNotice("Escreva o conteúdo do review antes de salvar.", "error"); return; }
    const button = status === "published" ? $("#blogPublish") : $("#blogSaveDraft");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = status === "published" ? "Publicando..." : "Salvando...";
    try {
      const url = editingSlug
        ? "/api/blog/posts/" + encodeURIComponent(editingSlug)
        : "/api/blog/posts";
      const method = editingSlug ? "PUT" : "POST";
      const result = await api(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }, true);
      editingSlug = result.post.slug;
      slugWasEdited = true;
      await loadAdminPosts();
      const post = adminPosts.find(item => item.slug === editingSlug);
      if (post) fillEditor(post);
      editorNotice(status === "published" ? "Review publicado com sucesso. Ele já está disponível no blog." : "Rascunho salvo com sucesso.", "success");
    } catch (error) {
      editorNotice(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function loadAdminPosts() {
    const data = await api("/api/blog/admin/posts", {}, true);
    adminPosts = Array.isArray(data.posts) ? data.posts : [];
    renderAdminPostList();
  }

  function waitForAuthUser() {
    const auth = window.firebase?.auth?.();
    if (!auth) return Promise.resolve(null);
    if (auth.currentUser) return Promise.resolve(auth.currentUser);
    return new Promise(resolve => {
      let unsubscribe = () => {};
      let settled = false;
      const finish = user => {
        if (settled) return;
        settled = true;
        unsubscribe();
        resolve(user || null);
      };
      unsubscribe = auth.onAuthStateChanged(finish, () => finish(null));
    });
  }

  async function initAdmin() {
    const root = $("#blogAdminPage");
    if (!root || root.dataset.loaded === "1") return;
    root.dataset.loaded = "1";
    const user = await waitForAuthUser();
    if (!user) {
      adminMessage("Faça login na sua conta do Resolvei para acessar o painel editorial.", "warning");
      return;
    }
    try {
      const status = await api("/api/blog/admin-status", {}, true, user);
      if (!status.configured) {
        adminMessage("O painel ainda não foi habilitado. Configure BLOG_ADMIN_EMAIL ou BLOG_ADMIN_UID nas variáveis de ambiente do serviço Resolvei no Render.", "warning");
        return;
      }
      if (!status.isAdmin) {
        adminMessage("Acesso restrito. Esta área está disponível somente para a conta administradora do blog.", "error");
        return;
      }
      isAdmin = true;
      document.querySelectorAll("[data-blog-admin-link]").forEach(link => { link.hidden = false; });
      $("#blogAdminWorkspace").hidden = false;
      $("#blogAdminMessage").hidden = true;
      bindAdminEditor();
      await loadAdminPosts();
      fillEditor();
    } catch (error) {
      adminMessage(error.message, "error");
    }
  }

  async function initRoute() {
    let route = location.pathname.replace(/^\/+|\/+$/g, "");
    if (!route || route === "index.html") route = (location.hash || "").replace(/^#\/?/, "");
    const parts = (route.split("?")[0] || "").split("/").filter(Boolean);
    if (!parts.length) return initHome();
    if (parts[0] === "blog" && parts[1]) return initArticle();
    if (parts[0] === "blogger") return initAdmin();
  }

  function updateAdminLinks(value) {
    isAdmin = !!value;
    document.querySelectorAll("[data-blog-admin-link], .blog-editor-shortcut").forEach(link => { link.hidden = !isAdmin; });
  }

  window.resolveiBlogHomePage = () => '<div class="blog-home-host" id="resolveiBlogHome"><div class="blog-loading">Carregando os reviews...</div></div>';
  window.resolveiBlogArticlePage = slug => '<div class="blog-article-host" id="resolveiBlogArticle" data-slug="' + esc(slug) + '"><div class="blog-loading">Carregando o artigo...</div></div>';
  window.resolveiBlogAdminPage = () => adminShell();
  window.resolveiBlogInitRoute = initRoute;
  window.resolveiBlogIsAdmin = () => isAdmin;
  window.resolveiBlogOnAuthStateChanged = async user => {
    const sequence = ++adminCheckSequence;
    updateAdminLinks(false);
    if (!user) return;
    try {
      const status = await api("/api/blog/admin-status", {}, true, user);
      if (sequence === adminCheckSequence) updateAdminLinks(!!status.isAdmin);
    } catch (_) {
      if (sequence === adminCheckSequence) updateAdminLinks(false);
    }
  };
})();