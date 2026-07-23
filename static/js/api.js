const Api = (() => {
  const TOKEN_KEY = "documind_token";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }
  function setToken(token) {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  }

  async function request(path, { method = "GET", body, headers = {}, raw = false, signal } = {}) {
    const token = getToken();
    const finalHeaders = { ...headers };
    if (token) finalHeaders["Authorization"] = `Bearer ${token}`;
    let finalBody = body;
    if (body && !(body instanceof FormData)) {
      finalHeaders["Content-Type"] = "application/json";
      finalBody = JSON.stringify(body);
    }
    const res = await fetch(path, { method, headers: finalHeaders, body: finalBody, signal });
    if (raw) return res;
    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      data = null;
    }
    if (!res.ok) {
      const detail = (data && data.detail) || `Request failed (${res.status})`;
      throw new Error(detail);
    }
    return data;
  }

  return {
    getToken,
    setToken,
    register: (payload) => request("/api/auth/register/", { method: "POST", body: payload }),
    login: (payload) => request("/api/auth/login/", { method: "POST", body: payload }),
    logout: () => request("/api/auth/logout/", { method: "POST" }),
    me: () => request("/api/auth/me/"),

    listDocuments: () => request("/api/documents/"),
    deleteDocument: (id) => request(`/api/documents/${id}/delete/`, { method: "DELETE" }),
    retryDocument: (id) => request(`/api/documents/${id}/retry/`, { method: "POST" }),
    renameDocument: (id, filename) =>
      request(`/api/documents/${id}/`, { method: "PATCH", body: { filename } }),
    shareDocument: (id, username) =>
      request(`/api/documents/${id}/share/`, { method: "POST", body: { username } }),
    previewDocument: (id, page, chunkIndex) => {
      const qs = new URLSearchParams({ page: page || 1 });
      if (chunkIndex !== undefined && chunkIndex !== null) qs.set("chunk_index", chunkIndex);
      return request(`/api/documents/${id}/preview/?${qs.toString()}`);
    },

    uploadDocument: (file, onProgress) => {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/documents/upload/");
        const token = getToken();
        if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
        };
        xhr.onload = () => {
          try {
            const data = JSON.parse(xhr.responseText);
            if (xhr.status >= 200 && xhr.status < 300) resolve(data);
            else reject(new Error(data.detail || "Upload failed."));
          } catch (e) {
            reject(new Error("Upload failed."));
          }
        };
        xhr.onerror = () => reject(new Error("Upload failed — network error."));
        const form = new FormData();
        form.append("file", file);
        xhr.send(form);
      });
    },

    listConversations: () => request("/api/chat/conversations/"),
    createConversation: (payload) =>
      request("/api/chat/conversations/new/", { method: "POST", body: payload || {} }),
    conversationMessages: (id) => request(`/api/chat/conversations/${id}/messages/`),

    // Streaming ask: returns the raw fetch Response for manual SSE parsing.
    askStream: (payload, signal) =>
      request("/api/chat/ask/", { method: "POST", body: payload, raw: true, signal }),
  };
})();
