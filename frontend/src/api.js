// Клиент API. Только ОТНОСИТЕЛЬНЫЕ пути /api/... — никаких IP и http://localhost:
// запрос идёт на тот же хост, с которого открыта страница, а nginx отправляет его в backend.
// Пути и форматы — строго по frontend/API.md.

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function detailToText(data) {
  if (!data || data.detail == null) return null;
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => `${(d.loc || []).slice(-1)[0] || ''}: ${d.msg}`).join('; ');
  }
  return JSON.stringify(data.detail);
}

// ---------- Токен админки (sessionStorage может быть недоступен — всё в try/catch) ----------
const TOKEN_KEY = 'autello_token';
let memoryToken = null; // запасной вариант, если sessionStorage запрещён

export function getToken() {
  try { return window.sessionStorage.getItem(TOKEN_KEY) || memoryToken; } catch { return memoryToken; }
}

export function setToken(token) {
  memoryToken = token || null;
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
    else window.sessionStorage.removeItem(TOKEN_KEY);
  } catch { /* приватный режим — живём на memoryToken */ }
}

let onUnauthorized = null;
/** Что делать при 401 на запросе с токеном (админка: выйти на экран входа). */
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

/**
 * fetch с таймаутом: если сервер молчит — бросаем ошибку, а не крутим спиннер вечно.
 * auth: true — подставить Bearer-токен; form — тело application/x-www-form-urlencoded (логин).
 */
export async function api(path, { method = 'GET', body, form, auth = false, timeout = 10000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  const headers = {};
  let payload;
  if (form !== undefined) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
    payload = new URLSearchParams(form).toString();
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  const token = auth ? getToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const res = await fetch(`/api${path}`, { method, headers, body: payload, signal: ctrl.signal });
    const data = res.status === 204 ? null : await res.json().catch(() => null);
    if (!res.ok) {
      if (res.status === 401 && auth && onUnauthorized) onUnauthorized();
      throw new ApiError(res.status, detailToText(data) || `Ошибка сервера (HTTP ${res.status})`);
    }
    return data;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err.name === 'AbortError') throw new ApiError(0, 'Сервер не ответил вовремя');
    throw new ApiError(0, 'Нет связи с сервером');
  } finally {
    clearTimeout(timer);
  }
}

export const rub = (n) => `${new Intl.NumberFormat('ru-RU').format(Number(n) || 0)} ₽`;
