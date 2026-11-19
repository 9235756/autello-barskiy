// Сбор поведенческих метрик посетителя. Отправляются ОДНИМ пакетом вместе с заявкой
// (поле metrics в POST /api/applications) — отдельных запросов трекер не делает.
//
// Что собираем:
//   time_on_page_sec — сколько секунд страница открыта
//   clicks           — клики по кнопкам и элементам управления [{el, t}]
//   hovers           — наведения курсора дольше 500 мс [{el, ms}]
//   return_count     — сколько раз человек уходил с вкладки и возвращался (visibilitychange)
//   scroll_depth     — максимальная глубина прокрутки, %
//   utm, referrer, user_agent, screen, language

const HOVER_MIN_MS = 500;
const MAX_EVENTS = 200;
const CLICKABLE = 'button, a, select, input[type="radio"], input[type="checkbox"], input[type="range"], [data-track]';

const startedAt = performance.now();
const clicks = [];
const hovers = [];
let returnCount = 0;
let wasHidden = document.visibilityState === 'hidden';
let maxScroll = 0;

const secondsSinceStart = () => Math.round((performance.now() - startedAt) / 100) / 10;

// Понятное имя элемента: data-track → id → name → текст
function elName(el) {
  const name = el.dataset.track || el.id || el.getAttribute('name') || (el.textContent || '').trim().slice(0, 40) || el.tagName.toLowerCase();
  return String(name).slice(0, 100);
}

function push(list, item) {
  if (list.length >= MAX_EVENTS) list.shift();
  list.push(item);
}

// --- Клики ---
document.addEventListener('click', (e) => {
  const el = e.target.closest(CLICKABLE);
  // клик по <label class="chip"> браузер сам пересылает в его <input> —
  // сам label в CLICKABLE не входит, поэтому событие учитывается один раз
  if (!el) return;
  push(clicks, { el: elName(el), t: secondsSinceStart() });
}, { capture: true, passive: true });

// --- Наведения дольше 500 мс (только мышь, на тач-экранах hover не бывает) ---
const hoverStart = new WeakMap();
document.addEventListener('pointerover', (e) => {
  if (e.pointerType !== 'mouse') return;
  const el = e.target.closest('[data-track], button, select, .chip, a');
  if (!el || hoverStart.has(el)) return;
  hoverStart.set(el, performance.now());
}, { passive: true });

document.addEventListener('pointerout', (e) => {
  if (e.pointerType !== 'mouse') return;
  const el = e.target.closest('[data-track], button, select, .chip, a');
  if (!el || (e.relatedTarget && el.contains(e.relatedTarget))) return;
  const t0 = hoverStart.get(el);
  hoverStart.delete(el);
  if (t0 == null) return;
  const ms = Math.round(performance.now() - t0);
  const target = el.matches('.chip') ? el.querySelector('input') || el : el;
  if (ms >= HOVER_MIN_MS) push(hovers, { el: elName(target), ms });
}, { passive: true });

// --- Возвраты на вкладку ---
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    wasHidden = true;
  } else if (wasHidden) {
    returnCount += 1;
    wasHidden = false;
  }
});

// --- Глубина прокрутки ---
function updateScroll() {
  const doc = document.documentElement;
  const scrollable = doc.scrollHeight - window.innerHeight;
  const pct = scrollable <= 0 ? 100 : ((window.scrollY + window.innerHeight) / doc.scrollHeight) * 100;
  maxScroll = Math.max(maxScroll, Math.min(100, Math.round(pct)));
}
let scrollTick = false;
window.addEventListener('scroll', () => {
  if (scrollTick) return;
  scrollTick = true;
  requestAnimationFrame(() => { updateScroll(); scrollTick = false; });
}, { passive: true });
window.addEventListener('load', updateScroll);

// --- UTM-метки из адреса страницы ---
function readUtm() {
  const q = new URLSearchParams(window.location.search);
  const utm = {};
  ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'].forEach((k) => {
    const v = q.get(k);
    if (v) utm[k] = v.slice(0, 200);
  });
  return utm;
}
const utmAtLanding = readUtm();

/** Снимок всех метрик на текущий момент — кладётся в поле metrics пакета заявки. */
export function getMetrics() {
  updateScroll();
  return {
    time_on_page_sec: Math.round((performance.now() - startedAt) / 1000),
    clicks: clicks.slice(),
    hovers: hovers.slice(),
    return_count: returnCount,
    scroll_depth: maxScroll,
    utm: utmAtLanding,
    referrer: document.referrer || null,
    user_agent: navigator.userAgent.slice(0, 1000),
    screen: `${window.screen.width}x${window.screen.height}`,
    language: (navigator.language || '').slice(0, 20) || null,
  };
}
