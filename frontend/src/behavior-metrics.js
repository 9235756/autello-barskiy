// Поведенческие метрики главной (часть 3): анонимно, раз в секунду, POST /api/behavior-metrics.
// Формат — как в уроке (см. frontend/API.md):
//   {application_id, time_on_page, buttons_clicked: "JSON", cursor_positions: "JSON", return_frequency}
//   + session_id, viewport_w/h, doc_w/h, page
//
// Правила:
//   - session_id — один на визит (crypto.randomUUID), строка в БД обновляется (upsert);
//   - время на странице считается только пока вкладка видима;
//   - позиция курсора записывается раз в секунду (не чаще), в долях 0..1 от размеров документа;
//   - отправка — раз в секунду и только при активной вкладке; последний снимок — sendBeacon на pagehide;
//   - ошибки сети молча игнорируются: метрики не должны мешать посетителю.

const ENDPOINT = '/api/behavior-metrics';
const TICK_MS = 1000;
const MAX_POINTS = 3600; // час на странице
const TRACKABLE = 'button, a, select, input, textarea, [data-track]';

function uuid() {
  try {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
  } catch { /* randomUUID есть только в secure context (https или localhost) */ }
  const b = new Uint8Array(16);
  (window.crypto || window.msCrypto).getRandomValues(b);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export const sessionId = uuid();

let seconds = 0;
let returns = 0;
let wasHidden = document.visibilityState === 'hidden';
const buttons = {};
const points = [];
let cursor = null; // последняя позиция мыши в координатах документа (px)
let inFlight = false;
let applicationId = 0;

// Имя элемента: data-track → id → name; у <label class="chip"> — его <input>
function nameOf(el) {
  const target = el.matches('label') ? el.querySelector('input') || el : el;
  return String(target.dataset.track || target.id || target.getAttribute('name') || '').slice(0, 100);
}

document.addEventListener('click', (e) => {
  const el = e.target.closest(TRACKABLE);
  if (!el) return;
  const name = nameOf(el);
  if (name) buttons[name] = (buttons[name] || 0) + 1;
}, { capture: true, passive: true });

// Слушатель только запоминает координаты; в массив они попадают раз в секунду в tick()
document.addEventListener('mousemove', (e) => {
  cursor = { x: e.pageX, y: e.pageY };
}, { passive: true });

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    wasHidden = true;
    send(true); // вкладку свернули — сохранить снимок прямо сейчас
  } else if (wasHidden) {
    returns += 1;
    wasHidden = false;
  }
});

function docSize() {
  const d = document.documentElement;
  return {
    w: Math.max(d.scrollWidth, d.clientWidth, 1),
    h: Math.max(d.scrollHeight, d.clientHeight, 1),
  };
}

function snapshot() {
  const { w, h } = docSize();
  return {
    application_id: applicationId,
    time_on_page: seconds,
    buttons_clicked: JSON.stringify(buttons),
    cursor_positions: JSON.stringify(points),
    return_frequency: returns,
    session_id: sessionId,
    viewport_w: window.innerWidth,
    viewport_h: window.innerHeight,
    doc_w: Math.round(w),
    doc_h: Math.round(h),
    page: window.location.pathname.slice(0, 200),
  };
}

function send(final = false) {
  const body = JSON.stringify(snapshot());
  if (final && navigator.sendBeacon) {
    try {
      // Blob с типом application/json — иначе FastAPI не разберёт тело (text/plain по умолчанию)
      navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'application/json' }));
    } catch { /* молча */ }
    return;
  }
  if (inFlight) return; // предыдущий запрос ещё идёт — следующий снимок всё равно накопительный
  inFlight = true;
  fetch(ENDPOINT, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: body.length < 60000 })
    .catch(() => { /* сеть недоступна — не мешаем посетителю */ })
    .finally(() => { inFlight = false; });
}

function tick() {
  if (document.visibilityState !== 'visible') return;
  seconds += 1;
  if (cursor) {
    const { w, h } = docSize();
    if (points.length >= MAX_POINTS) points.shift();
    points.push({ x: Math.round((cursor.x / w) * 10000) / 10000, y: Math.round((cursor.y / h) * 10000) / 10000 });
  }
  send();
}

setInterval(tick, TICK_MS);
window.addEventListener('pagehide', () => send(true));

/** Номер заявки после отправки формы — попадёт в следующие снимки (бэкенд его не проверяет). */
export function setApplicationId(id) {
  applicationId = Number(id) || 0;
}
