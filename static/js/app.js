(() => {
  "use strict";

  const REFUSAL_MESSAGE = "I cannot find this in the documents.";
  const STORAGE_QUOTA_MB = 500; // cosmetic quota for the "Storage" ring — the backend has no per-user quota.
  const ALLOWED_EXT = ["pdf", "md"];

  const state = {
    user: null,
    documents: [],
    conversations: [],
    scopeDocumentIds: [], // [] == all documents
    activeConversationId: null,
    streaming: false,
    abortController: null,
    pollTimer: null,
    activity: [],
    searchTerm: "",
    currentRenameId: null,
    currentDeleteId: null,
    currentShareId: null,
  };

  const el = (id) => document.getElementById(id);

  // ---------------------------------------------------------------------
  // Utils
  // ---------------------------------------------------------------------
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function humanFileSize(bytes) {
    if (!bytes) return "0 MB";
    const mb = bytes / (1024 * 1024);
    if (mb < 1) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    if (mb < 1024) return `${mb.toFixed(1)} MB`;
    return `${(mb / 1024).toFixed(2)} GB`;
  }

  function relativeTime(isoString) {
    const then = new Date(isoString).getTime();
    const diffMs = Date.now() - then;
    const mins = Math.round(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.round(hours / 24);
    if (days < 7) return `${days}d ago`;
    return new Date(isoString).toLocaleDateString();
  }

  function isToday(isoString) {
    const d = new Date(isoString);
    const now = new Date();
    return d.toDateString() === now.toDateString();
  }

  // ---------------------------------------------------------------------
  // Toasts
  // ---------------------------------------------------------------------
  const ICONS = {
    success: "fa-circle-check",
    error: "fa-circle-exclamation",
    info: "fa-circle-info",
  };

  function showToast(message, type = "info") {
    const container = el("toastContainer");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `<i class="fa-solid ${ICONS[type] || ICONS.info}"></i><span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.classList.add("fade-out");
      setTimeout(() => toast.remove(), 250);
    }, 3800);
  }

  // ---------------------------------------------------------------------
  // Activity log (session-only — the backend has no activity feed endpoint)
  // ---------------------------------------------------------------------
  function pushActivity(icon, text) {
    state.activity.unshift({ icon, text, at: new Date() });
    state.activity = state.activity.slice(0, 8);
    renderActivity();
  }

  function renderActivity() {
    const list = el("activityList");
    if (!state.activity.length) {
      list.innerHTML = `<li class="activity-empty">No recent activity yet.</li>`;
      return;
    }
    list.innerHTML = state.activity
      .map((a) => `<li><i class="fa-solid ${a.icon}"></i> ${escapeHtml(a.text)}</li>`)
      .join("");
  }

  // ---------------------------------------------------------------------
  // Particles (ambient background)
  // ---------------------------------------------------------------------
  function generateParticles() {
    const container = el("particles");
    if (!container || container.childElementCount) return;
    const count = 22;
    for (let i = 0; i < count; i++) {
      const p = document.createElement("span");
      p.className = "particle";
      const size = 2 + Math.random() * 4;
      p.style.width = `${size}px`;
      p.style.height = `${size}px`;
      p.style.left = `${Math.random() * 100}%`;
      p.style.animationDuration = `${10 + Math.random() * 14}s`;
      p.style.animationDelay = `${Math.random() * 10}s`;
      container.appendChild(p);
    }
  }

  // ---------------------------------------------------------------------
  // Dark mode
  // ---------------------------------------------------------------------
  const THEME_KEY = "documind_theme";
  function applyTheme(theme) {
    document.body.classList.toggle("dark", theme === "dark");
    const icon = el("darkModeBtn").querySelector("i");
    icon.className = theme === "dark" ? "fa-solid fa-sun" : "fa-regular fa-moon";
  }
  el("darkModeBtn").addEventListener("click", () => {
    const next = document.body.classList.contains("dark") ? "light" : "dark";
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  });
  applyTheme(localStorage.getItem(THEME_KEY) || "light");

  // ---------------------------------------------------------------------
  // Generic modal helpers
  // ---------------------------------------------------------------------
  function openModal(id) {
    document.querySelectorAll(".modal.visible").forEach((m) => m.classList.remove("visible"));
    el(id).classList.add("visible");
  }
  function closeModal(id) {
    el(id).classList.remove("visible");
  }
  document.querySelectorAll(".modal").forEach((modal) => {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.remove("visible");
    });
    modal.querySelectorAll(".closeModal").forEach((btn) => {
      btn.addEventListener("click", () => modal.classList.remove("visible"));
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.querySelectorAll(".modal.visible").forEach((m) => m.classList.remove("visible"));
  });

  // ---------------------------------------------------------------------
  // Auth
  // ---------------------------------------------------------------------
  const authOverlay = el("authOverlay");
  const appRoot = el("appRoot");
  const loadingOverlay = el("loadingOverlay");

  function showLoading(title) {
    if (title) el("loadingTitle").textContent = title;
    loadingOverlay.classList.remove("hidden");
  }
  function hideLoading() {
    loadingOverlay.classList.add("hidden");
  }

  function showAuth() {
    authOverlay.classList.remove("hidden");
    appRoot.classList.add("hidden");
  }
  function showApp() {
    authOverlay.classList.add("hidden");
    appRoot.classList.remove("hidden");
  }

  document.querySelectorAll(".auth-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".auth-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const isLogin = tab.dataset.tab === "login";
      el("loginForm").classList.toggle("hidden", !isLogin);
      el("registerForm").classList.toggle("hidden", isLogin);
    });
  });

  el("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    el("loginError").textContent = "";
    try {
      const data = await Api.login({
        username: form.get("identifier"),
        password: form.get("password"),
      });
      Api.setToken(data.token);
      await bootApp(data.user);
    } catch (err) {
      el("loginError").textContent = err.message;
    }
  });

  el("registerForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    el("registerError").textContent = "";
    try {
      const data = await Api.register({
        username: form.get("username"),
        email: form.get("email"),
        password: form.get("password"),
        role: form.get("role"),
      });
      Api.setToken(data.token);
      await bootApp(data.user);
    } catch (err) {
      el("registerError").textContent = err.message;
    }
  });

  el("logoutBtn").addEventListener("click", async () => {
    try {
      await Api.logout();
    } catch (e) {
      /* ignore network errors on logout */
    }
    Api.setToken(null);
    stopPolling();
    Voice.stop();
    state.user = null;
    state.documents = [];
    state.conversations = [];
    state.activity = [];
    showAuth();
  });

  // ---------------------------------------------------------------------
  // Sidebar nav — smooth scroll to sections on the same page
  // ---------------------------------------------------------------------
  document.querySelectorAll(".sidebar nav a").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      document.querySelectorAll(".sidebar nav a").forEach((a) => a.classList.remove("active"));
      link.classList.add("active");
      const view = link.dataset.view;
      if (view === "history" || view === "settings") {
        showToast(`${view === "history" ? "History" : "Settings"} is coming soon.`, "info");
        return;
      }
      const targetId = link.getAttribute("href").slice(1) || "top";
      const target = document.getElementById(targetId) || el("top");
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  el("heroUploadBtn").addEventListener("click", () => {
    el("upload").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  el("heroAskBtn").addEventListener("click", () => {
    el("chat").scrollIntoView({ behavior: "smooth", block: "start" });
    if (!el("questionInput").disabled) el("questionInput").focus();
  });
  el("aiAssistant").addEventListener("click", () => {
    el("chat").scrollIntoView({ behavior: "smooth", block: "start" });
    if (!el("questionInput").disabled) el("questionInput").focus();
  });

  el("notifBtn").addEventListener("click", () => {
    const ready = state.documents.filter((d) => d.status === "ready").length;
    const working = state.documents.filter((d) => !["ready", "failed"].includes(d.status)).length;
    const failed = state.documents.filter((d) => d.status === "failed").length;
    showToast(`${ready} ready · ${working} processing · ${failed} failed`, "info");
  });

  // ---------------------------------------------------------------------
  // Search
  // ---------------------------------------------------------------------
  el("searchInput").addEventListener("input", (e) => {
    state.searchTerm = e.target.value.trim().toLowerCase();
    renderDocumentsGrid();
  });
  el("viewAllBtn").addEventListener("click", () => {
    state.searchTerm = "";
    el("searchInput").value = "";
    renderDocumentsGrid();
    el("library").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  // ---------------------------------------------------------------------
  // Upload
  // ---------------------------------------------------------------------
  const dropZone = el("dropZone");
  const fileInput = el("fileInput");

  el("chooseFileBtn").addEventListener("click", () => fileInput.click());
  el("headerBrowseBtn").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    handleFiles(fileInput.files);
    fileInput.value = "";
  });

  ["dragenter", "dragover"].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
    })
  );
  dropZone.addEventListener("drop", (e) => handleFiles(e.dataTransfer.files));

  function handleFiles(fileList) {
    Array.from(fileList).forEach((file) => {
      const ext = file.name.toLowerCase().split(".").pop();
      if (!ALLOWED_EXT.includes(ext)) {
        showToast(`"${file.name}" isn't a .pdf or .md file.`, "error");
        return;
      }
      uploadOneFile(file);
    });
  }

  function setProgress(pct, label) {
    const section = el("progressSection");
    section.classList.remove("hidden");
    el("progressFill").style.width = `${pct}%`;
    el("progressValue").textContent = `${pct}%`;
    if (label) el("progressLabel").textContent = label;
  }
  function hideProgressSoon() {
    setTimeout(() => el("progressSection").classList.add("hidden"), 900);
  }

  async function uploadOneFile(file) {
    setProgress(0, `Uploading ${file.name}`);
    try {
      await Api.uploadDocument(file, (pct) => {
        setProgress(pct, pct >= 100 ? `Processing ${file.name}` : `Uploading ${file.name}`);
      });
      setProgress(100, `${file.name} uploaded`);
      hideProgressSoon();
      showToast(`${file.name} uploaded — indexing now.`, "success");
      pushActivity("fa-cloud-arrow-up", `Uploaded ${file.name}`);
      await refreshDocuments();
      startPolling();
    } catch (err) {
      showToast(`Upload failed: ${err.message}`, "error");
      hideProgressSoon();
    }
  }

  // ---------------------------------------------------------------------
  // Documents: fetch, render grid, dashboard stats
  // ---------------------------------------------------------------------
  async function refreshDocuments() {
    try {
      const data = await Api.listDocuments();
      state.documents = data.documents;
      renderDocumentsGrid();
      renderDashboardStats();
      updateChatAvailability();
    } catch (err) {
      showToast(`Couldn't load documents: ${err.message}`, "error");
    }
  }

  function statusClassFor(status) {
    if (status === "ready") return "ready";
    if (status === "failed") return "failed";
    return "working";
  }

  function renderDocumentsGrid() {
    const grid = el("documentsGrid");
    const empty = el("documentsEmpty");
    const term = state.searchTerm;
    const docs = term
      ? state.documents.filter((d) => d.filename.toLowerCase().includes(term))
      : state.documents;

    if (state.documents.length === 0) {
      grid.innerHTML = "";
      empty.classList.remove("hidden");
      empty.querySelector("p").textContent = "Nothing indexed yet — upload a PDF or Markdown file to get started.";
      return;
    }
    if (docs.length === 0) {
      grid.innerHTML = "";
      empty.classList.remove("hidden");
      empty.querySelector("p").textContent = `No documents match "${term}".`;
      return;
    }
    empty.classList.add("hidden");

    grid.innerHTML = docs
      .map((doc) => {
        const iconClass = doc.file_type === "pdf" ? "fa-solid fa-file-pdf pdf-icon" : "fa-brands fa-markdown md-icon";
        const badge = statusClassFor(doc.status);
        const errorLine =
          doc.status === "failed" && doc.error_message
            ? `<p class="status-error">${escapeHtml(doc.error_message)}</p>`
            : "";
        return `
          <div class="document-card" data-id="${doc.id}">
            <div class="document-top">
              <i class="${iconClass}"></i>
              <div class="menu" data-id="${doc.id}"><i class="fa-solid fa-ellipsis"></i></div>
            </div>
            <h3>${escapeHtml(doc.filename)}</h3>
            <span class="status-badge ${badge}">${escapeHtml(doc.status)}</span>
            ${errorLine}
            <p class="doc-meta">${doc.page_count || "—"} pages · ${doc.chunk_count || "—"} chunks · ${relativeTime(doc.uploaded_at)}</p>
            <div class="document-footer">
              <button data-action="preview" data-id="${doc.id}"><i class="fa-solid fa-eye"></i> Preview</button>
              <button data-action="ask" data-id="${doc.id}" ${doc.status !== "ready" ? "disabled title='Wait until this document is ready'" : ""}><i class="fa-solid fa-comments"></i> Ask AI</button>
            </div>
          </div>
        `;
      })
      .join("");
  }

  function renderDashboardStats() {
    el("totalDocs").textContent = state.documents.length;
    el("totalChats").textContent = state.conversations.length;
    const totalBytes = state.documents.reduce((sum, d) => sum + (d.size_bytes || 0), 0);
    el("storageUsed").textContent = humanFileSize(totalBytes);
    el("todayUploads").textContent = state.documents.filter((d) => isToday(d.uploaded_at)).length;

    const pct = Math.min(100, Math.round((totalBytes / (STORAGE_QUOTA_MB * 1024 * 1024)) * 100));
    const circle = el("storageCircle");
    circle.style.background = `conic-gradient(var(--accent) ${pct}%, var(--border-color) ${pct}%)`;
    circle.innerHTML = `<span>${pct}%</span>`;
  }

  async function refreshConversationCount() {
    try {
      const data = await Api.listConversations();
      state.conversations = data.conversations;
      el("totalChats").textContent = state.conversations.length;
    } catch (err) {
      /* non-critical for the dashboard */
    }
  }

  // ---------------------------------------------------------------------
  // Document card actions (preview / ask / menu: rename / retry / share / delete)
  // ---------------------------------------------------------------------
  el("documentsGrid").addEventListener("click", async (e) => {
    const menuIcon = e.target.closest(".menu");
    if (menuIcon) {
      e.stopPropagation();
      toggleDocMenu(menuIcon);
      return;
    }
    const menuItem = e.target.closest(".doc-menu-item");
    if (menuItem) {
      e.stopPropagation();
      const { action, id } = menuItem.dataset;
      closeAllDocMenus();
      await handleDocAction(action, id);
      return;
    }
    const actionBtn = e.target.closest("button[data-action]");
    if (actionBtn) {
      const { action, id } = actionBtn.dataset;
      if (action === "preview") openSourcePreview(id, 1, null, null);
      if (action === "ask") setAskScope(id);
    }
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".menu") && !e.target.closest(".doc-menu-list")) closeAllDocMenus();
  });

  function closeAllDocMenus() {
    document.querySelectorAll(".doc-menu-list").forEach((m) => m.remove());
  }

  function toggleDocMenu(menuIcon) {
    const existing = menuIcon.querySelector(".doc-menu-list");
    closeAllDocMenus();
    if (existing) return; // it was already open — just closed above
    const id = menuIcon.dataset.id;
    const doc = state.documents.find((d) => d.id === id);
    if (!doc) return;
    const list = document.createElement("div");
    list.className = "doc-menu-list";
    list.innerHTML = `
      <button class="doc-menu-item" data-action="rename" data-id="${id}"><i class="fa-solid fa-pen"></i> Rename</button>
      ${doc.status === "failed" ? `<button class="doc-menu-item" data-action="retry" data-id="${id}"><i class="fa-solid fa-rotate-right"></i> Retry</button>` : ""}
      <button class="doc-menu-item" data-action="share" data-id="${id}"><i class="fa-solid fa-share-nodes"></i> Share</button>
      <button class="doc-menu-item danger" data-action="delete" data-id="${id}"><i class="fa-solid fa-trash"></i> Delete</button>
    `;
    menuIcon.appendChild(list);
  }

  async function handleDocAction(action, id) {
    const doc = state.documents.find((d) => d.id === id);
    if (!doc) return;
    if (action === "rename") {
      state.currentRenameId = id;
      el("renameInput").value = doc.filename;
      openModal("renameModal");
      el("renameInput").focus();
    } else if (action === "delete") {
      state.currentDeleteId = id;
      openModal("deleteModal");
    } else if (action === "share") {
      state.currentShareId = id;
      el("shareInput").value = "";
      openModal("shareModal");
      el("shareInput").focus();
    } else if (action === "retry") {
      try {
        await Api.retryDocument(id);
        showToast(`Retrying ${doc.filename}…`, "info");
        pushActivity("fa-rotate-right", `Retrying ${doc.filename}`);
        await refreshDocuments();
        startPolling();
      } catch (err) {
        showToast(`Retry failed: ${err.message}`, "error");
      }
    }
  }

  el("renameSaveBtn").addEventListener("click", async () => {
    const newName = el("renameInput").value.trim();
    if (!newName || !state.currentRenameId) return;
    try {
      await Api.renameDocument(state.currentRenameId, newName);
      showToast("Document renamed.", "success");
      pushActivity("fa-pen", `Renamed a document to ${newName}`);
      closeModal("renameModal");
      await refreshDocuments();
    } catch (err) {
      showToast(`Rename failed: ${err.message}`, "error");
    }
  });

  el("cancelDelete").addEventListener("click", () => closeModal("deleteModal"));
  el("confirmDelete").addEventListener("click", async () => {
    if (!state.currentDeleteId) return;
    const doc = state.documents.find((d) => d.id === state.currentDeleteId);
    try {
      await Api.deleteDocument(state.currentDeleteId);
      showToast("Document deleted.", "success");
      pushActivity("fa-trash", `Deleted ${doc ? doc.filename : "a document"}`);
      closeModal("deleteModal");
      if (state.scopeDocumentIds.includes(state.currentDeleteId)) resetAskScope();
      await refreshDocuments();
    } catch (err) {
      showToast(`Delete failed: ${err.message}`, "error");
    }
  });

  el("shareSaveBtn").addEventListener("click", async () => {
    const username = el("shareInput").value.trim();
    if (!username || !state.currentShareId) return;
    try {
      const res = await Api.shareDocument(state.currentShareId, username);
      showToast(res.detail || "Shared.", "success");
      pushActivity("fa-share-nodes", `Shared a document with ${username}`);
      closeModal("shareModal");
    } catch (err) {
      showToast(`Share failed: ${err.message}`, "error");
    }
  });

  function setAskScope(id) {
    const doc = state.documents.find((d) => d.id === id);
    if (!doc) return;
    state.scopeDocumentIds = [id];
    el("chatScopeLabel").innerHTML = `Scoped to <strong>${escapeHtml(doc.filename)}</strong> · <a href="#" id="resetScopeLink">reset</a>`;
    el("resetScopeLink").addEventListener("click", (e) => {
      e.preventDefault();
      resetAskScope();
    });
    el("chat").scrollIntoView({ behavior: "smooth", block: "start" });
    if (!el("questionInput").disabled) el("questionInput").focus();
  }
  function resetAskScope() {
    state.scopeDocumentIds = [];
    el("chatScopeLabel").textContent = "Powered by Groq AI • Verified Answers";
  }

  // ---------------------------------------------------------------------
  // Polling for in-progress documents
  // ---------------------------------------------------------------------
  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(() => {
      const stillProcessing = state.documents.some((d) => !["ready", "failed"].includes(d.status));
      if (stillProcessing) refreshDocuments();
      else stopPolling();
    }, 1500);
  }
  function stopPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = null;
  }

  // ---------------------------------------------------------------------
  // Chat availability
  // ---------------------------------------------------------------------
  function updateChatAvailability() {
    const readyCount = state.documents.filter((d) => d.status === "ready").length;
    const input = el("questionInput");
    const sendBtn = el("sendQuestionBtn");
    const hint = el("chatInputHint");
    document.querySelectorAll(".prompt-btn").forEach((b) => (b.disabled = readyCount === 0));
    if (readyCount === 0 && !state.streaming) {
      input.disabled = true;
      sendBtn.disabled = true;
      hint.classList.remove("hidden");
    } else if (!state.streaming) {
      input.disabled = false;
      sendBtn.disabled = false;
      hint.classList.add("hidden");
    }
  }

  // ---------------------------------------------------------------------
  // Voice — read an assistant answer aloud (Web Speech API, no API key)
  // ---------------------------------------------------------------------
  const Voice = (() => {
    const supported = "speechSynthesis" in window;
    let currentBtn = null;

    function stop() {
      if (supported) window.speechSynthesis.cancel();
      if (currentBtn) setBtnState(currentBtn, "idle");
      currentBtn = null;
    }
    function setBtnState(btn, mode) {
      btn.dataset.state = mode;
      btn.classList.toggle("speaking", mode === "speaking");
      btn.innerHTML =
        mode === "speaking" ? `<span class="voice-icon">◼</span> Stop` : `<span class="voice-icon">🔊</span> Listen`;
    }
    function speak(text, btn) {
      if (!supported) return;
      if (currentBtn === btn && window.speechSynthesis.speaking) {
        stop();
        return;
      }
      stop();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.onend = () => stop();
      utterance.onerror = () => stop();
      currentBtn = btn;
      setBtnState(btn, "speaking");
      window.speechSynthesis.speak(utterance);
    }
    return { supported, speak, stop };
  })();

  // ---------------------------------------------------------------------
  // Chat thread + SSE streaming
  // ---------------------------------------------------------------------
  const chatMessages = el("chatMessages");
  const questionInput = el("questionInput");
  const sendBtn = el("sendQuestionBtn");
  const stopBtn = el("stopQuestionBtn");
  const typingIndicator = el("typingIndicator");

  sendBtn.addEventListener("click", sendQuestion);
  questionInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !state.streaming) {
      e.preventDefault();
      sendQuestion();
    }
  });
  stopBtn.addEventListener("click", () => {
    if (state.abortController) state.abortController.abort();
  });

  document.querySelectorAll(".prompt-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.disabled) return;
      questionInput.value = btn.textContent.trim();
      sendQuestion();
    });
  });

  el("clearChatBtn").addEventListener("click", () => {
    if (state.streaming) return;
    state.activeConversationId = null;
    chatMessages.innerHTML = `
      <div class="message ai">
        <div class="message-avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="message-content">
          <h4>DocuMind AI</h4>
          <p>👋 Hello! Upload a document and ask me anything. I'll answer using only information found inside your files.</p>
        </div>
      </div>`;
    el("sourcesContainer").innerHTML = `<div class="source-empty" id="sourcesEmpty">Citation snippets will appear here once you ask a question.</div>`;
    showToast("Chat cleared.", "info");
  });

  function appendUserMessage(text) {
    const div = document.createElement("div");
    div.className = "message user";
    div.innerHTML = `
      <div class="message-avatar"><i class="fa-solid fa-user"></i></div>
      <div class="message-content"><p>${escapeHtml(text)}</p></div>
    `;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function appendAssistantPlaceholder() {
    const div = document.createElement("div");
    div.className = "message ai";
    div.innerHTML = `
      <div class="message-avatar"><i class="fa-solid fa-robot"></i></div>
      <div class="message-content"><h4>DocuMind AI</h4><p><span class="cursor-blink"></span></p></div>
    `;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div.querySelector(".message-content");
  }

  function setStreamingUI(isStreaming) {
    state.streaming = isStreaming;
    const readyCount = state.documents.filter((d) => d.status === "ready").length;
    questionInput.disabled = isStreaming || readyCount === 0;
    sendBtn.classList.toggle("hidden", isStreaming);
    stopBtn.classList.toggle("hidden", !isStreaming);
  }

  async function sendQuestion() {
    const question = questionInput.value.trim();
    if (!question || state.streaming) return;
    Voice.stop();
    questionInput.value = "";
    appendUserMessage(question);
    typingIndicator.classList.remove("hidden");
    chatMessages.scrollTop = chatMessages.scrollHeight;
    setStreamingUI(true);

    state.abortController = new AbortController();
    let accumulated = "";
    let assistantContent = null;

    try {
      const res = await Api.askStream(
        {
          question,
          conversation_id: state.activeConversationId,
          document_scope: state.scopeDocumentIds,
        },
        state.abortController.signal
      );

      if (!res.ok || !res.body) throw new Error("The server could not start a response.");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let boundary;
        while ((boundary = buffer.indexOf("\n\n")) !== -1) {
          const rawEvent = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const { event, data } = parseSSEEvent(rawEvent);
          if (!event) continue;

          if (event === "conversation") {
            state.activeConversationId = data.conversation_id;
          } else if (event === "token") {
            if (!assistantContent) {
              typingIndicator.classList.add("hidden");
              assistantContent = appendAssistantPlaceholder();
            }
            accumulated += data.delta;
            renderAssistantContent(assistantContent, accumulated);
          } else if (event === "error") {
            typingIndicator.classList.add("hidden");
            if (!assistantContent) assistantContent = appendAssistantPlaceholder();
            renderAssistantError(assistantContent, data.detail);
          } else if (event === "done") {
            typingIndicator.classList.add("hidden");
            if (!assistantContent) assistantContent = appendAssistantPlaceholder();
            finalizeAssistantMessage(assistantContent, accumulated, data);
          }
        }
      }
    } catch (err) {
      typingIndicator.classList.add("hidden");
      if (!assistantContent) assistantContent = appendAssistantPlaceholder();
      if (err.name !== "AbortError") {
        renderAssistantError(assistantContent, err.message);
      } else {
        finalizeAssistantMessage(assistantContent, accumulated || "(stopped)", { grounded: false, citations: [] });
      }
    } finally {
      setStreamingUI(false);
      state.abortController = null;
      pushActivity("fa-comments", `Asked: ${question.length > 40 ? question.slice(0, 40) + "…" : question}`);
      refreshConversationCount();
    }
  }

  function parseSSEEvent(raw) {
    let event = null;
    let dataLine = "";
    raw.split("\n").forEach((line) => {
      if (line.startsWith("event: ")) event = line.slice(7).trim();
      if (line.startsWith("data: ")) dataLine = line.slice(6);
    });
    let data = {};
    try {
      data = JSON.parse(dataLine);
    } catch (e) {
      /* ignore malformed frame */
    }
    return { event, data };
  }

  function renderAssistantContent(container, text) {
    const isRefusal = text.trim() === REFUSAL_MESSAGE;
    container.classList.toggle("refusal", isRefusal);
    container.innerHTML = `<h4>DocuMind AI</h4><p>${escapeHtml(text)}<span class="cursor-blink"></span></p>`;
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function renderAssistantError(container, detail) {
    container.classList.add("refusal");
    container.innerHTML = `<h4>DocuMind AI</h4><p>Something went wrong: ${escapeHtml(detail)}</p>`;
  }

  function finalizeAssistantMessage(container, text, { grounded, citations }) {
    const isRefusal = !grounded || text.trim() === REFUSAL_MESSAGE;
    container.classList.toggle("refusal", isRefusal);
    let html = `<h4>DocuMind AI</h4><p>${escapeHtml(text)}</p>`;
    if (!isRefusal) {
      html += `<div class="answer-controls">`;
      if (Voice.supported) {
        html += `<button class="voice-btn" type="button" data-state="idle"><span class="voice-icon">🔊</span> Listen</button>`;
      }
      html += `</div>`;
    }
    container.innerHTML = html;
    const voiceBtn = container.querySelector(".voice-btn");
    if (voiceBtn) voiceBtn.addEventListener("click", () => Voice.speak(text, voiceBtn));
    chatMessages.scrollTop = chatMessages.scrollHeight;
    renderSources(citations || []);
  }

  function renderSources(citations) {
    const container = el("sourcesContainer");
    if (!citations.length) {
      container.innerHTML = `<div class="source-empty" id="sourcesEmpty">No citations for this answer.</div>`;
      return;
    }
    container.innerHTML = citations
      .map(
        (c) => `
        <div class="source-card" data-doc-id="${c.document_id}" data-page="${c.page_number}" data-chunk-index="${c.chunk_index}">
          <div class="source-top"><i class="fa-solid fa-file-pdf"></i><span>${escapeHtml(c.filename)}</span></div>
          <p>Page ${c.page_number} · chunk ${String(c.chunk_index).padStart(2, "0")}</p>
          <small>Click to view this passage in context.</small>
        </div>
      `
      )
      .join("");
    container.querySelectorAll(".source-card").forEach((card) => {
      card.addEventListener("click", () => {
        openSourcePreview(card.dataset.docId, card.dataset.page, card.dataset.chunkIndex, card.querySelector("span").textContent);
      });
    });
  }

  // ---------------------------------------------------------------------
  // Preview modal (uses iframe.srcdoc since the backend returns extracted
  // text, not a raw file URL)
  // ---------------------------------------------------------------------
  async function openSourcePreview(docId, page, chunkIndex, label) {
    openModal("previewModal");
    el("previewTitle").textContent = label || "Document Preview";
    el("previewFrame").srcdoc = `<p style="font-family: sans-serif; padding: 1rem; color:#666;">Loading…</p>`;
    try {
      const data = await Api.previewDocument(docId, page, chunkIndex);
      el("previewTitle").textContent = `${data.filename} — page ${data.page_number}${data.page_count ? ` of ${data.page_count}` : ""}`;
      let bodyHtml = escapeHtml(data.page_text || "(No extracted text for this page.)").replace(/\n/g, "<br>");
      if (data.excerpt) {
        bodyHtml = `<div style="background:#fff3cd;border-left:4px solid #F5A524;padding:0.75rem 1rem;margin-bottom:1rem;">${escapeHtml(data.excerpt).replace(/\n/g, "<br>")}</div>${bodyHtml}`;
      }
      el("previewFrame").srcdoc = `
        <html><head><style>
          body { font-family: 'Segoe UI', sans-serif; padding: 1.2rem; line-height: 1.6; color: #161A2E; white-space: pre-wrap; }
        </style></head><body>${bodyHtml}</body></html>
      `;
    } catch (err) {
      el("previewFrame").srcdoc = `<p style="font-family: sans-serif; padding: 1rem; color:#E5484D;">Could not load source: ${escapeHtml(err.message)}</p>`;
    }
  }

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------
  async function bootApp(user) {
    state.user = user;
    el("username").textContent = user.username;
    el("userRole").textContent = user.role;
    showApp();
    hideLoading();
    generateParticles();
    pushActivity("fa-right-to-bracket", `Logged in as ${user.username}`);
    await Promise.all([refreshDocuments(), refreshConversationCount()]);
    startPolling();
  }

  (async function init() {
    generateParticles();
    const token = Api.getToken();
    if (!token) {
      showAuth();
      return;
    }
    showLoading("Loading your workspace…");
    try {
      const data = await Api.me();
      await bootApp(data.user);
    } catch (err) {
      Api.setToken(null);
      hideLoading();
      showAuth();
    }
  })();
})();
function speak(text) {

    // Stop any speech already in progress
    speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);

    utterance.lang = "en-US";
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;

    speechSynthesis.speak(utterance);
}