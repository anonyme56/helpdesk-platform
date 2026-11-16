// Petit client HTTP : le jeton JWT est gardé en mémoire de session (sessionStorage).
const TOKEN_KEY = "helpdesk_token";

export const getToken = () => sessionStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY));

async function request(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api${path}`, { method, headers, body: form ?? (body ? JSON.stringify(body) : undefined) });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      msg = typeof data.detail === "string" ? data.detail : "Requête invalide";
    } catch {
      /* corps vide */
    }
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  register: (email, full_name, password) => request("/auth/register", { method: "POST", body: { email, full_name, password } }),
  login: (email, password) => request("/auth/login", { method: "POST", body: { email, password } }),
  me: () => request("/auth/me"),
  users: () => request("/users"),
  tickets: (status) => request(`/tickets${status ? `?status=${status}` : ""}`),
  ticket: (id) => request(`/tickets/${id}`),
  createTicket: (data) => request("/tickets", { method: "POST", body: data }),
  patchTicket: (id, data) => request(`/tickets/${id}`, { method: "PATCH", body: data }),
  comment: (id, body) => request(`/tickets/${id}/comments`, { method: "POST", body: { body } }),
  upload: (id, file) => {
    const form = new FormData();
    form.append("file", file);
    return request(`/tickets/${id}/attachments`, { method: "POST", form });
  },
  requestExport: () => request("/exports", { method: "POST" }),
  exportStatus: (id) => request(`/exports/${id}`),
};

// Téléchargement authentifié : on récupère le blob puis on déclenche l'enregistrement.
export async function download(path, filename) {
  const res = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new Error("Téléchargement impossible");
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}
