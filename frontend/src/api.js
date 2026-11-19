// Клиент API. Только ОТНОСИТЕЛЬНЫЕ пути /api/... — никаких IP и http://localhost:
// запрос идёт на тот же хост, с которого открыта страница, а nginx отправляет его в backend.

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

/**
 * fetch с таймаутом: если сервер молчит — бросаем ошибку, а не крутим спиннер вечно.
 */
export async function api(path, { method = 'GET', body, timeout = 10000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const res = await fetch(`/api${path}`, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
    const data = res.status === 204 ? null : await res.json().catch(() => null);
    if (!res.ok) {
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
