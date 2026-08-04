const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/+$/, "");

export function apiUrl(path) {
  return `${API_BASE}${path}`;
}

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function authHeader(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function conciseError(message, status) {
  const raw = String(message || "").trim();
  if (/<(?:!doctype|html|head|body)\b/i.test(raw)) return `请求失败（HTTP ${status}）`;
  return raw || `HTTP ${status}`;
}

export async function request(path, { method = "GET", token, body, signal } = {}) {
  const headers = {
    ...authHeader(token),
  };
  const init = { method, headers, signal };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  const res = await fetch(apiUrl(path), init);
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    if (data && typeof data === "object") {
      if (typeof data.detail === "string") msg = conciseError(data.detail, res.status);
      else if (data.detail?.message) msg = data.detail.message;
      else if (data.detail) msg = JSON.stringify(data.detail);
      else msg = JSON.stringify(data);
    } else if (typeof data === "string" && data) {
      msg = conciseError(data, res.status);
    }
    throw new ApiError(msg, res.status, data);
  }
  return data;
}
