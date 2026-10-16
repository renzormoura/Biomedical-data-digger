/* Biomedical Data Digger — frontend sem dependências.
   O HTML de resultado vem do servidor já sanitizado (markdown_lite escapa todo texto);
   todo o resto é montado com textContent/DOM, nunca com innerHTML de dados externos. */
(() => {
  "use strict";

  const HISTORY_KEY = "bdd.history";
  const THEME_KEY = "bdd.theme";
  const HISTORY_LIMIT = 10;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  // ---------- armazenamento (tolerante a falhas) ----------
  const store = {
    get(key, fallback) {
      try {
        const raw = localStorage.getItem(key);
        return raw === null ? fallback : JSON.parse(raw);
      } catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* modo privado */ }
    },
  };

  // ---------- API ----------
  async function api(path, body) {
    let response;
    try {
      response = await fetch(path, {
        method: body === undefined ? "GET" : "POST",
        headers: body === undefined ? {} : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        credentials: "same-origin",
      });
    } catch {
      throw new Error("Sem conexão com o servidor. Verifique sua internet e tente novamente.");
    }
    let data = {};
    try { data = await response.json(); } catch { /* corpo vazio */ }
    if (!response.ok) {
      const detail = Array.isArray(data.detail) ? "Dados inválidos. Revise os campos." : null;
      const error = new Error(data.error || detail || `Erro ${response.status}.`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  // ---------- toast ----------
  let toastTimer;
  function toast(message) {
    const el = $("#toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 2200);
  }

  // ---------- tema ----------
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    $("#theme-toggle").textContent = theme === "dark" ? "☀️ Claro" : "🌙 Escuro";
  }
  applyTheme(store.get(THEME_KEY, "dark"));
  $("#theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    store.set(THEME_KEY, next);
  });

  // ---------- abas ----------
  const tabs = $$(".tab");
  function selectTab(key, focus = false) {
    const target = tabs.find((tab) => tab.dataset.target === key) || tabs[0];
    tabs.forEach((tab) => {
      const active = tab === target;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      $("#panel-" + tab.dataset.target).hidden = !active;
    });
    if (focus) target.focus();
    target.scrollIntoView({ inline: "center", block: "nearest" });
    history.replaceState(null, "", "#" + target.dataset.target);
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(tab.dataset.target));
    tab.addEventListener("keydown", (event) => {
      const moves = { ArrowRight: 1, ArrowLeft: -1 };
      if (event.key in moves) {
        event.preventDefault();
        selectTab(tabs[(index + moves[event.key] + tabs.length) % tabs.length].dataset.target, true);
      } else if (event.key === "Home") { event.preventDefault(); selectTab(tabs[0].dataset.target, true); }
      else if (event.key === "End") { event.preventDefault(); selectTab(tabs[tabs.length - 1].dataset.target, true); }
    });
  });
  selectTab(location.hash.slice(1));
  window.addEventListener("hashchange", () => selectTab(location.hash.slice(1)));

  // ---------- histórico (local ao navegador) ----------
  function loadHistory() { return store.get(HISTORY_KEY, []).filter((x) => x && x.id); }
  function renderHistory() {
    const items = loadHistory();
    $$('[data-role="history"]').forEach((list) => {
      list.replaceChildren();
      if (!items.length) {
        const li = document.createElement("li");
        li.className = "muted";
        li.textContent = "Nenhum artigo consultado ainda.";
        list.append(li);
        return;
      }
      items.forEach((item) => {
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = item.title.length > 70 ? item.title.slice(0, 70) + "…" : item.title;
        button.title = item.id;
        button.addEventListener("click", () => {
          const panel = list.closest(".panel");
          $('[data-role="article"]', panel).value = item.id;
          $('[data-role="article"]', panel).focus();
        });
        li.append(button);
        list.append(li);
      });
    });
  }
  function remember(id, title) {
    if (!id || !title) return;
    const items = loadHistory().filter((x) => x.id !== id);
    items.unshift({ id, title });
    store.set(HISTORY_KEY, items.slice(0, HISTORY_LIMIT));
    renderHistory();
  }
  renderHistory();

  // ---------- execução das análises ----------
  function setBusy(panel, busy) {
    $$(".btn", panel).forEach((button) => {
      if (busy) { button.dataset.wasDisabled = button.disabled ? "1" : ""; button.disabled = true; }
      else { button.disabled = button.dataset.wasDisabled === "1"; delete button.dataset.wasDisabled; }
    });
    const output = $('[data-role="output"]', panel);
    output.setAttribute("aria-busy", String(busy));
  }

  function showLoading(panel, label) {
    const output = $('[data-role="output"]', panel);
    output.replaceChildren();
    const box = document.createElement("div");
    box.className = "loading";
    const spinner = document.createElement("div");
    spinner.className = "spinner";
    spinner.setAttribute("aria-hidden", "true");
    const text = document.createElement("span");
    text.textContent = `${label}… isso pode levar alguns segundos.`;
    box.append(spinner, text);
    output.append(box);
    $('[data-role="output-title"]', panel).textContent = label;
  }

  function showError(panel, message) {
    const output = $('[data-role="output"]', panel);
    $('[data-role="output-meta"]', panel).textContent = "";
    output.replaceChildren();
    const box = document.createElement("div");
    box.className = "error-box";
    box.setAttribute("role", "alert");
    const strong = document.createElement("strong");
    strong.textContent = "Não foi possível concluir. ";
    box.append(strong, document.createTextNode(message));
    output.append(box);
  }

  function describeMeta(meta) {
    if (!meta) return "";
    const parts = [];
    parts.push(meta.cached ? "⚡ resultado em cache (sem custo)" : meta.tokens ? `≈ ${meta.tokens.toLocaleString("pt-BR")} tokens` : "");
    if (meta.quota_remaining !== null && meta.quota_remaining !== undefined) {
      parts.push(`cota restante hoje: ${meta.quota_remaining.toLocaleString("pt-BR")}`);
    }
    return parts.filter(Boolean).join(" · ");
  }

  function showResult(panel, label, data) {
    const output = $('[data-role="output"]', panel);
    output.innerHTML = data.html; // sanitizado no servidor (markdown_lite)
    panel.dataset.lastMarkdown = data.markdown;
    $('[data-role="output-title"]', panel).textContent = label;
    $('[data-role="output-meta"]', panel).textContent = describeMeta(data.meta);
    $$('[data-action="copy"], [data-action="print"]', panel).forEach((b) => { b.disabled = false; });
    output.scrollIntoView({ behavior: "smooth", block: "nearest" });
    if (data.title) remember(data.article_id, data.title);
  }

  async function run(panel, label, path, payload) {
    setBusy(panel, true);
    showLoading(panel, label);
    try {
      showResult(panel, label, await api(path, payload));
    } catch (error) {
      showError(panel, error.message);
    } finally {
      setBusy(panel, false);
    }
  }

  const value = (panel, role) => $(`[data-role="${role}"]`, panel).value.trim();
  function filters(panel) {
    const out = {};
    $$("[data-filter]", panel).forEach((select) => { out[select.dataset.filter] = select.value; });
    return out;
  }
  function requireArticle(panel) {
    if (!value(panel, "article")) {
      showError(panel, "Cole um ID ou URL de artigo antes de gerar a análise.");
      $('[data-role="article"]', panel).focus();
      return false;
    }
    return true;
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const panel = button.closest(".panel");
    if (!panel) return;
    const action = button.dataset.action;
    const page = panel.dataset.page;

    if (action === "analyze") {
      if (!requireArticle(panel)) return;
      run(panel, button.textContent.trim(), "/api/analyze", {
        page, button: button.dataset.button,
        article_id: value(panel, "article"), model: value(panel, "model"), filters: filters(panel),
      });
    } else if (action === "cite") {
      if (!requireArticle(panel)) return;
      run(panel, `Referência ${button.dataset.style}`, "/api/cite", {
        article_id: value(panel, "article"), style: button.dataset.style,
      });
    } else if (action === "audit") {
      if (!panel.dataset.lastMarkdown) { showError(panel, "Gere uma análise antes de executar a auditoria."); return; }
      if (!requireArticle(panel)) return;
      run(panel, "Auditoria da Resposta", "/api/audit", {
        article_id: value(panel, "article"), model: value(panel, "model"), previous: panel.dataset.lastMarkdown, page,
      });
    } else if (action === "compare") {
      if (!value(panel, "cmp-a") || !value(panel, "cmp-b")) {
        showError(panel, "Informe os dois IDs ou URLs para comparar os artigos.");
        return;
      }
      run(panel, "Comparação entre Artigos", "/api/compare", {
        article_a: value(panel, "cmp-a"), article_b: value(panel, "cmp-b"),
        analysis: value(panel, "cmp-type"), model: value(panel, "model"),
        clinical: panel.dataset.clinical === "true", page,
      });
    } else if (action === "clear-filters") {
      $$("[data-filter]", panel).forEach((select) => { select.value = ""; });
    } else if (action === "copy") {
      navigator.clipboard.writeText(panel.dataset.lastMarkdown || "")
        .then(() => toast("Copiado!"), () => toast("Não foi possível copiar."));
    } else if (action === "print") {
      window.print();
    }
  });

  // Enter no campo de artigo dispara o primeiro botão de análise da aba.
  $$('[data-role="article"]').forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      const panel = input.closest(".panel");
      const first = $('[data-action="analyze"]', panel);
      if (first) first.click();
    });
  });

  // ---------- pesquisa ----------
  const searchForm = $("#search-form");
  const searchOutput = $("#search-output");
  searchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    searchOutput.setAttribute("aria-busy", "true");
    searchOutput.replaceChildren();
    const loading = document.createElement("p");
    loading.className = "placeholder";
    loading.textContent = "Buscando nas fontes…";
    searchOutput.append(loading);
    try {
      const data = await api("/api/search", {
        query: $("#search-query").value.trim(),
        area: $("#search-area").value,
        limit: Number($("#search-limit").value),
      });
      renderResults(data.results);
    } catch (error) {
      searchOutput.replaceChildren();
      const box = document.createElement("div");
      box.className = "error-box";
      box.setAttribute("role", "alert");
      box.textContent = error.message;
      searchOutput.append(box);
    } finally {
      searchOutput.setAttribute("aria-busy", "false");
    }
  });

  function renderResults(results) {
    const list = document.createElement("ol");
    list.className = "result-list";
    results.forEach((item) => {
      const li = document.createElement("li");
      li.className = "result-item";
      const heading = document.createElement("h3");
      if (item.url) {
        const link = document.createElement("a");
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = item.title;
        heading.append(link);
      } else {
        heading.textContent = item.title;
      }
      const meta = document.createElement("div");
      meta.className = "result-meta";
      meta.textContent = [item.journal, item.year, item.pmid && `PMID ${item.pmid}`, item.source].filter(Boolean).join(" · ");
      const score = document.createElement("span");
      score.className = "score";
      score.textContent = `${item.reliability} · ${Number(item.score).toFixed(2)}`;
      li.append(heading, meta, score);

      const identifier = item.doi || item.pmid;
      if (identifier) {
        const actions = document.createElement("div");
        actions.className = "result-actions";
        const use = document.createElement("button");
        use.type = "button";
        use.className = "btn btn-secondary btn-sm";
        use.textContent = "Analisar este artigo";
        use.addEventListener("click", () => {
          selectTab("geral");
          const input = $('#panel-geral [data-role="article"]');
          input.value = identifier;
          input.focus();
        });
        actions.append(use);
        li.append(actions);
      }
      list.append(li);
    });
    searchOutput.replaceChildren(list);
  }

  // ---------- conta ----------
  const dialog = $("#auth-dialog");
  const accountButton = $("#account-button");
  const authError = $("#auth-error");
  const logoutButton = $("#logout-button");

  function setUser(user) {
    accountButton.dataset.user = user || "";
    accountButton.textContent = user ? `👤 ${user}` : "👤 Entrar";
    logoutButton.hidden = !user;
    $$("[data-auth='login'], [data-auth='register'], #auth-form .field").forEach((el) => { el.hidden = Boolean(user); });
  }
  setUser(accountButton.dataset.user);

  accountButton.addEventListener("click", () => {
    authError.hidden = true;
    dialog.showModal();
  });

  async function authenticate(kind) {
    const email = $("#auth-email").value.trim();
    const password = $("#auth-password").value;
    if (!email || !password) { authError.textContent = "Informe e-mail e senha."; authError.hidden = false; return; }
    try {
      const data = await api(`/api/auth/${kind}`, { email, password });
      $("#auth-password").value = "";
      setUser(data.user);
      dialog.close();
      toast(kind === "register" ? "Conta criada!" : "Login realizado!");
    } catch (error) {
      authError.textContent = error.message;
      authError.hidden = false;
    }
  }
  $("[data-auth='login']").addEventListener("click", () => authenticate("login"));
  $("[data-auth='register']").addEventListener("click", () => authenticate("register"));
  $("[data-auth='cancel']").addEventListener("click", () => dialog.close());
  logoutButton.addEventListener("click", async () => {
    try { await api("/api/auth/logout", {}); } catch { /* sessão já inválida */ }
    setUser("");
    dialog.close();
    toast("Você saiu da conta.");
  });
})();
