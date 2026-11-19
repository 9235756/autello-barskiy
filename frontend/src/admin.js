// Админка (часть 3): вход по JWT, заявки по приоритету, CRUD услуг в таблице,
// статистика пользователей с heatmap. Пути и форматы — строго по frontend/API.md.
import './styles/base.css';
import './styles/admin.css';
import { api, getToken, rub, setToken, setUnauthorizedHandler } from './api';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const dt = (iso) => (iso ? new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—');
const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const TEMP = {
  hot: { icon: '🔥', label: 'горячий' },
  warm: { icon: '🌤', label: 'тёплый' },
  cold: { icon: '❄️', label: 'холодный' },
};

// =====================================================================
//  Авторизация
// =====================================================================
const authView = $('#authView');
const appView = $('#appView');
const authForm = $('#authForm');
const authMsg = $('#authMsg');
let authMode = 'login'; // login | register

function setAuthMode(mode) {
  authMode = mode;
  const reg = mode === 'register';
  $('#authTitle').textContent = reg ? 'Регистрация администратора' : 'Вход в админку';
  $('#authLead').textContent = reg ? 'Создайте логин и пароль первого администратора.' : 'Заявки, услуги и статистика посетителей.';
  $('#authSubmit').textContent = reg ? 'Создать администратора' : 'Войти';
  $('#authPass').autocomplete = reg ? 'new-password' : 'current-password';
  $('#authPassHint').hidden = !reg;
  $('#backToLogin').hidden = !reg;
  $('#registerBox').classList.toggle('is-collapsed', reg);
  authMsg.textContent = '';
}

async function showAuth(message = '') {
  appView.hidden = true;
  authView.hidden = false;
  setAuthMode('login');
  authMsg.textContent = message;
  // Кнопка «Зарегистрироваться» — только если в БД нет ни одного админа
  try {
    const { has_admins: hasAdmins } = await api('/auth/check');
    $('#registerBox').hidden = Boolean(hasAdmins);
  } catch (err) {
    $('#registerBox').hidden = true;
    authMsg.textContent = `Не удалось связаться с сервером: ${err.message}`;
  }
  $('#authUser').focus();
}

function logout(message = '') {
  setToken(null);
  closeAllDialogs();
  showAuth(message);
}

setUnauthorizedHandler(() => logout('Сессия истекла — войдите снова.'));

$('#registerBtn').addEventListener('click', () => { setAuthMode('register'); $('#authUser').focus(); });
$('#backToLogin').addEventListener('click', () => { setAuthMode('login'); $('#authUser').focus(); });
$('#logoutBtn').addEventListener('click', () => logout());

authForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = authForm.username.value.trim();
  const password = authForm.password.value;
  if (username.length < 3) { authMsg.textContent = 'Логин — не короче 3 символов'; authForm.username.focus(); return; }
  if (password.length < (authMode === 'register' ? 8 : 1)) {
    authMsg.textContent = authMode === 'register' ? 'Пароль — не короче 8 символов' : 'Введите пароль';
    authForm.password.focus();
    return;
  }
  const btn = $('#authSubmit');
  btn.disabled = true;
  authMsg.textContent = '';
  try {
    if (authMode === 'register') {
      await api('/auth/register', { method: 'POST', body: { username, password } });
    }
    // Логин — form-urlencoded (OAuth2PasswordRequestForm), не JSON
    const tok = await api('/auth/login', { method: 'POST', form: { username, password } });
    setToken(tok.access_token);
    authForm.reset();
    await enterApp();
  } catch (err) {
    if (err.status === 403) $('#registerBox').hidden = true; // админ уже есть — регистрация закрыта
    if (err.status === 403) setAuthMode('login');
    authMsg.textContent = err.status === 401 ? 'Неверный логин или пароль' : err.message;
  } finally {
    btn.disabled = false;
  }
});

async function enterApp() {
  const me = await api('/auth/me', { auth: true });
  $('#whoami').textContent = me.username;
  authView.hidden = true;
  appView.hidden = false;
  selectTab(currentTab());
}

// =====================================================================
//  Вкладки
// =====================================================================
const TABS = ['apps', 'services'];
function currentTab() {
  const h = window.location.hash.replace('#', '');
  return TABS.includes(h) ? h : 'apps';
}

function selectTab(name) {
  TABS.forEach((t) => {
    const on = t === name;
    const tab = $(`#tab-${t}`);
    tab.setAttribute('aria-selected', String(on));
    tab.tabIndex = on ? 0 : -1;
    $(`#panel-${t}`).hidden = !on;
  });
  if (window.location.hash !== `#${name}`) window.history.replaceState(null, '', `#${name}`);
  if (name === 'apps') loadApps();
  else loadServices();
}

TABS.forEach((t) => $(`#tab-${t}`).addEventListener('click', () => selectTab(t)));
$('.tabs').addEventListener('keydown', (e) => {
  if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
  const i = TABS.indexOf(currentTab());
  const next = TABS[(i + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length];
  selectTab(next);
  $(`#tab-${next}`).focus();
});

// =====================================================================
//  Модальные окна (<dialog>: фокус внутри, Esc закрывает)
// =====================================================================
function openDialog(dlg) {
  if (!dlg.open) dlg.showModal();
}
function closeDialog(dlg) {
  if (!dlg.open) return;
  if (reduceMotion()) { dlg.close(); return; }
  dlg.classList.add('is-closing');
  setTimeout(() => { dlg.classList.remove('is-closing'); dlg.close(); }, 140);
}
function closeAllDialogs() { $$('dialog[open]').forEach((d) => d.close()); }

// Клик по подложке закрывает окно
$$('dialog').forEach((dlg) => {
  dlg.addEventListener('click', (e) => { if (e.target === dlg) closeDialog(dlg); });
  dlg.addEventListener('cancel', (e) => { e.preventDefault(); closeDialog(dlg); });
});

function confirmDialog(title, text, okLabel = 'Удалить') {
  const dlg = $('#confirmDialog');
  $('#confirmTitle').textContent = title;
  $('#confirmText').textContent = text;
  $('#confirmOk').textContent = okLabel;
  dlg.returnValue = '';
  openDialog(dlg);
  return new Promise((resolve) => {
    dlg.addEventListener('close', () => resolve(dlg.returnValue === 'ok'), { once: true });
  });
}

// =====================================================================
//  Заявки
// =====================================================================
const appBody = $('#appTable tbody');
let tempFilter = '';
let ranked = [];

function badge(t) {
  const x = TEMP[t] || { icon: '', label: t };
  return `<span class="temp temp--${esc(t)}"><span aria-hidden="true">${x.icon}</span> ${x.label}</span>`;
}

function scoreBar(score, t) {
  return `<span class="score"><span class="score__num">${score}</span><span class="score__track" aria-hidden="true"><i class="score__fill score__fill--${esc(t)}" style="width:${Math.max(3, score)}%"></i></span></span>`;
}

function renderSummary(s) {
  const t = s.by_temperature || {};
  const svc = (s.by_service || []).slice(0, 4)
    .map((x) => `<li><span>${esc(x.service)}</span><b>${x.count}</b></li>`).join('');
  $('#summary').innerHTML = `
    <div class="kpi"><span class="kpi__label">Всего заявок</span><span class="kpi__value">${s.total}</span>
      <span class="kpi__sub">за 7 дней — ${s.last_7_days} · за 30 дней — ${s.last_30_days}</span></div>
    <div class="kpi kpi--temps"><span class="kpi__label">По температуре</span>
      <span class="kpi__temps">
        <span title="горячие">🔥 <b>${t.hot || 0}</b></span><span title="тёплые">🌤 <b>${t.warm || 0}</b></span><span title="холодные">❄️ <b>${t.cold || 0}</b></span>
      </span>
      <span class="kpi__sub">средний score ${s.avg_score}</span></div>
    <div class="kpi"><span class="kpi__label">Средний бюджет</span><span class="kpi__value">${s.avg_budget ? rub(s.avg_budget) : '—'}</span>
      <span class="kpi__sub">нужен персональный менеджер: ${s.needs_personal_manager}</span></div>
    <div class="kpi"><span class="kpi__label">Популярные услуги</span><ul class="kpi__list">${svc || '<li class="muted">нет данных</li>'}</ul></div>`;
}

function renderApps() {
  const items = tempFilter ? ranked.filter((a) => a.scoring.temperature === tempFilter) : ranked;
  if (!items.length) {
    appBody.innerHTML = `<tr><td colspan="10" class="muted">${ranked.length ? 'Нет заявок с такой температурой.' : 'Заявок пока нет. Выполните make test-sql или отправьте форму на главной.'}</td></tr>`;
    return;
  }
  appBody.innerHTML = items.map((a) => {
    const sc = a.scoring;
    const fio = [a.last_name, a.first_name].filter(Boolean).join(' ');
    return `<tr data-id="${a.id}" class="row--${esc(sc.temperature)}">
      <td>${badge(sc.temperature)}</td>
      <td class="num">${scoreBar(sc.score, sc.temperature)}</td>
      <td><strong>${esc(fio)}</strong><span class="sub">${esc(a.business_niche || '—')}</span></td>
      <td>${esc(a.service_name || '—')}</td>
      <td class="num">${a.budget ? rub(a.budget) : '—'}</td>
      <td>${esc(a.deadline || '—')}</td>
      <td>${esc(sc.department)}</td>
      <td>${sc.needs_personal_manager ? '<span class="pill pill--pm">нужен</span>' : '<span class="muted">—</span>'}</td>
      <td class="nowrap">${dt(a.created_at)}</td>
      <td><button type="button" class="btn btn--ghost btn--small" data-act="view">Просмотр</button></td>
    </tr>`;
  }).join('');
}

async function loadApps() {
  try {
    const [summary, list] = await Promise.all([
      api('/applications/summary', { auth: true }),
      api('/applications/ranked', { auth: true }),
    ]);
    ranked = Array.isArray(list) ? list : [];
    renderSummary(summary);
    renderApps();
  } catch (err) {
    if (err.status === 401) return;
    appBody.innerHTML = `<tr><td colspan="10" class="form-msg is-error">Не удалось загрузить заявки: ${esc(err.message)}</td></tr>`;
  }
}

$('.filters').addEventListener('click', (e) => {
  const b = e.target.closest('.filter');
  if (!b) return;
  tempFilter = b.dataset.temp;
  $$('.filter').forEach((x) => x.classList.toggle('is-on', x === b));
  renderApps();
});
$('#reloadApps').addEventListener('click', loadApps);

appBody.addEventListener('click', (e) => {
  const b = e.target.closest('button[data-act="view"]');
  if (b) openApplication(Number(b.closest('tr').dataset.id));
});

// ---------- Просмотр заявки ----------
const CONTACT = { phone: 'Звонок', telegram: 'Telegram', whatsapp: 'WhatsApp', email: 'Email' };
const BREAKDOWN = { budget: ['Бюджет', 30], deadline: ['Срок', 25], company: ['Компания', 15], role: ['Роль', 10], volume: ['Объём', 10], niche: ['Ниша', 10] };

function telHref(phone) { return `tel:${String(phone || '').replace(/[^\d+]/g, '')}`; }

async function openApplication(id) {
  const dlg = $('#appDialog');
  $('#appNo').textContent = `Заявка №${id}`;
  $('#appTitle').textContent = 'Загрузка…';
  $('#appBody').innerHTML = '<p class="muted">Загрузка…</p>';
  openDialog(dlg);
  try {
    const a = await api(`/applications/${id}`, { auth: true });
    const sc = a.scoring;
    const fio = [a.last_name, a.first_name, a.middle_name].filter(Boolean).join(' ');
    $('#appTitle').innerHTML = `${esc(fio)} ${badge(sc.temperature)}`;
    const field = (label, value) => `<div class="kv"><dt>${label}</dt><dd>${value || '<span class="muted">—</span>'}</dd></div>`;
    const m = a.metrics;
    $('#appBody').innerHTML = `
      <div class="detail__grid">
        <section class="detail__main">
          <h3>Контакты</h3>
          <div class="contact-links">
            <a class="btn btn--small" href="${esc(telHref(a.phone))}">📞 ${esc(a.phone)}</a>
            ${a.email ? `<a class="btn btn--ghost btn--small" href="mailto:${esc(a.email)}">✉️ ${esc(a.email)}</a>` : ''}
          </div>
          <dl class="kvs">
            ${field('Способ связи', esc(CONTACT[a.contact_method] || a.contact_method))}
            ${field('Удобное время', esc(a.contact_time))}
            ${field('Роль', esc(a.role))}
          </dl>
          <h3>Задача</h3>
          <dl class="kvs">
            ${field('Услуга', esc(a.service_name))}
            ${field('Бюджет', a.budget ? rub(a.budget) : '')}
            ${field('Срок', esc(a.deadline))}
            ${field('Сфера', esc(a.business_niche))}
            ${field('Размер компании', esc(a.company_size))}
            ${field('Автомобилей', esc(a.need_volume))}
            ${field('Формат работы', esc(a.task_volume))}
            ${field('Что сделать', esc(a.task_type))}
            ${field('Интерес', esc(a.product_interest))}
            ${field('Создана', dt(a.created_at))}
          </dl>
          ${a.comment ? `<h3>Комментарий</h3><p class="comment">${esc(a.comment)}</p>` : ''}
          ${m ? `<h3>Поведение на сайте</h3><dl class="kvs">
            ${field('Время на странице', `${m.time_on_page} с`)}
            ${field('Кликов', String(Object.values(m.buttons_clicked || {}).reduce((x, y) => x + (Number(y) || 0), 0)))}
            ${field('Возвратов на вкладку', String(m.return_frequency))}
          </dl>` : ''}
        </section>
        <aside class="detail__side">
          <div class="scorecard scorecard--${esc(sc.temperature)}">
            <span class="scorecard__num">${sc.score}</span><span class="scorecard__of">/ 100</span>
            <p>${badge(sc.temperature)}</p>
          </div>
          <dl class="kvs kvs--tight">
            ${field('Срочность', esc(sc.urgency))}
            ${field('Отдел', esc(sc.department))}
            ${field('Перс. менеджер', sc.needs_personal_manager ? '<span class="pill pill--pm">нужен</span>' : 'не нужен')}
          </dl>
          <p class="action"><b>Что сделать:</b> ${esc(sc.recommended_action)}</p>
          ${sc.ai_summary ? `<p class="ai"><b>ИИ-резюме (эмуляция):</b> ${esc(sc.ai_summary)}</p>` : ''}
          <h3>Из чего сложился score</h3>
          <ul class="breakdown">${Object.entries(BREAKDOWN).map(([k, [label, max]]) => {
            const v = sc.breakdown[k] || 0;
            return `<li><span>${label}</span><span class="breakdown__track"><i style="width:${(v / max) * 100}%"></i></span><b>${v}/${max}</b></li>`;
          }).join('')}</ul>
          <h3>Причины</h3>
          <ul class="reasons">${sc.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>
        </aside>
      </div>`;
  } catch (err) {
    if (err.status === 401) return;
    $('#appTitle').textContent = 'Ошибка';
    $('#appBody').innerHTML = `<p class="form-msg is-error">Не удалось загрузить заявку: ${esc(err.message)}</p>`;
  }
}
$('#appClose').addEventListener('click', () => closeDialog($('#appDialog')));

// =====================================================================
//  Услуги: таблица с добавлением строки, редактированием в строке, удалением
// =====================================================================
const svcBody = $('#svcTable tbody');
const svcMsg = $('#svcMsg');
let services = [];
let editingId = null; // id редактируемой строки или 'new'

function message(text, isError = false) {
  svcMsg.textContent = text;
  svcMsg.classList.toggle('is-error', isError);
}

function rowView(s) {
  return `<tr data-id="${s.id}">
    <td class="num muted">${s.id}</td>
    <td><strong>${esc(s.services)}</strong></td>
    <td>${esc(s.budget_range)}</td>
    <td class="num">${rub(s.budget_min)}</td>
    <td class="num">${rub(s.budget_max)}</td>
    <td><span class="pill ${s.is_active ? 'pill--on' : 'pill--off'}">${s.is_active ? 'да' : 'нет'}</span></td>
    <td class="nowrap muted">${dt(s.updated_at)}</td>
    <td><div class="actions">
      <button type="button" class="btn btn--ghost btn--small" data-act="edit">Изменить</button>
      <button type="button" class="btn btn--danger btn--small" data-act="delete" aria-label="Удалить «${esc(s.services)}»">Удалить</button>
    </div></td>
  </tr>`;
}

function rowEdit(s) {
  const isNew = s.id === 'new';
  return `<tr data-id="${s.id}" class="is-editing">
    <td class="num muted">${isNew ? 'нов.' : s.id}</td>
    <td><input name="services" value="${esc(s.services)}" aria-label="Название услуги" placeholder="Название" maxlength="200"></td>
    <td><input name="budget_range" value="${esc(s.budget_range)}" aria-label="Подпись диапазона" placeholder="авто: 50к–250к" maxlength="50"></td>
    <td class="num"><input name="budget_min" type="number" min="0" step="1000" value="${s.budget_min ?? ''}" aria-label="Бюджет от" placeholder="от"></td>
    <td class="num"><input name="budget_max" type="number" min="0" step="1000" value="${s.budget_max ?? ''}" aria-label="Бюджет до" placeholder="до"></td>
    <td><label class="switch"><input name="is_active" type="checkbox" ${s.is_active ? 'checked' : ''}><span class="sr-only">Активна</span></label></td>
    <td class="muted">${isNew ? '—' : dt(s.updated_at)}</td>
    <td><div class="actions">
      <button type="button" class="btn btn--small" data-act="save">Сохранить</button>
      <button type="button" class="btn btn--quiet btn--small" data-act="cancel">Отмена</button>
    </div></td>
  </tr>`;
}

function renderServices() {
  const rows = [];
  if (editingId === 'new') rows.push(rowEdit({ id: 'new', services: '', budget_range: '', budget_min: '', budget_max: '', is_active: true }));
  services.forEach((s) => rows.push(s.id === editingId ? rowEdit(s) : rowView(s)));
  svcBody.innerHTML = rows.length ? rows.join('')
    : '<tr><td colspan="8" class="muted">Услуг пока нет — нажмите «Добавить строку» в панели справа.</td></tr>';
  const active = services.filter((s) => s.is_active).length;
  $('#svcCount').textContent = `Всего: ${services.length} · активных: ${active}`;
  // После редактирования (широкие поля) таблица могла уехать вбок — возвращаем к началу
  if (editingId === null) svcBody.closest('.table-wrap').scrollLeft = 0;
}

async function loadServices() {
  try {
    const data = await api('/admin-settings');
    // Ответ обязан быть массивом — иначе таблица не строится (ошибка урока)
    if (!Array.isArray(data)) throw new Error('сервер вернул не список услуг');
    services = data;
    renderServices();
  } catch (err) {
    svcBody.innerHTML = `<tr><td colspan="8" class="form-msg is-error">Не удалось загрузить услуги: ${esc(err.message)}</td></tr>`;
  }
}

function startEdit(id) {
  editingId = id;
  renderServices();
  const input = svcBody.querySelector('tr.is-editing input[name="services"]');
  if (input) { input.focus(); input.select(); }
}

async function saveRow(tr) {
  const id = tr.dataset.id;
  const val = (n) => tr.querySelector(`[name=${n}]`);
  const body = {
    services: val('services').value.trim(),
    budget_min: Number(val('budget_min').value),
    budget_max: Number(val('budget_max').value),
    is_active: val('is_active').checked,
  };
  const range = val('budget_range').value.trim();
  if (range) body.budget_range = range;
  if (body.services.length < 2) { message('Название — не короче 2 символов', true); val('services').focus(); return; }
  if (val('budget_min').value === '' || val('budget_max').value === '') { message('Заполните обе границы бюджета', true); return; }
  if (body.budget_min > body.budget_max) { message('«От» не может быть больше «до»', true); val('budget_min').focus(); return; }
  tr.querySelectorAll('button, input').forEach((x) => { x.disabled = true; });
  try {
    if (id === 'new') {
      const created = await api('/admin-settings', { method: 'POST', body, auth: true });
      message(`Добавлена услуга «${created.services}»`);
    } else {
      await api(`/admin-settings/${id}`, { method: 'PUT', body, auth: true });
      message('Изменения сохранены');
    }
    editingId = null;
    await loadServices();
  } catch (err) {
    message(err.status === 409 ? 'Услуга с таким названием уже есть' : err.message, true);
    tr.querySelectorAll('button, input').forEach((x) => { x.disabled = false; });
  }
}

svcBody.addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-act]');
  if (!btn) return;
  const tr = btn.closest('tr');
  const id = tr.dataset.id === 'new' ? 'new' : Number(tr.dataset.id);
  const act = btn.dataset.act;
  if (act === 'edit') { startEdit(id); return; }
  if (act === 'cancel') { editingId = null; message(''); renderServices(); return; }
  if (act === 'save') { saveRow(tr); return; }
  if (act === 'delete') {
    const s = services.find((x) => x.id === id);
    const ok = await confirmDialog('Удалить услугу?', `«${s.services}» пропадёт из списка на главной. Заявки останутся, но без привязки к услуге.`);
    if (!ok) return;
    try {
      await api(`/admin-settings/${id}`, { method: 'DELETE', auth: true });
      message(`Услуга «${s.services}» удалена`);
      if (editingId === id) editingId = null;
      await loadServices();
    } catch (err) { message(err.message, true); }
  }
});

svcBody.addEventListener('dblclick', (e) => {
  const tr = e.target.closest('tr[data-id]');
  if (tr && !tr.classList.contains('is-editing') && editingId === null) startEdit(Number(tr.dataset.id));
});

svcBody.addEventListener('keydown', (e) => {
  const tr = e.target.closest('tr.is-editing');
  if (!tr) return;
  if (e.key === 'Enter') { e.preventDefault(); saveRow(tr); }
  if (e.key === 'Escape') { e.preventDefault(); editingId = null; message(''); renderServices(); }
});

$('#addRow').addEventListener('click', () => {
  if (editingId === 'new') { svcBody.querySelector('tr.is-editing input')?.focus(); return; }
  message('');
  startEdit('new');
});
$('#reloadServices').addEventListener('click', () => { editingId = null; message(''); loadServices(); });

// =====================================================================
//  Статистика пользователей: периоды, heatmap, топ кнопок
// =====================================================================
const BUTTON_NAMES = {
  service: 'Выбор услуги', budget: 'Ползунок бюджета', submit: 'Кнопка «Отправить»',
  role_owner: 'Роль: собственник', role_head: 'Роль: руководитель', role_staff: 'Роль: сотрудник',
  cm_phone: 'Связь: звонок', cm_telegram: 'Связь: Telegram', cm_whatsapp: 'Связь: WhatsApp', cm_email: 'Связь: email',
  last_name: 'Поле «Фамилия»', first_name: 'Поле «Имя»', middle_name: 'Поле «Отчество»', phone: 'Поле «Телефон»',
  email: 'Поле «Email»', business_niche: 'Сфера', company_size: 'Размер компании', task_type: 'Что сделать',
  need_volume: 'Сколько автомобилей', task_volume: 'Формат работы', deadline: 'Когда нужно',
  product_interest: 'Что ещё интересно', contact_time: 'Удобное время', comment: 'Комментарий',
  again: 'Отправить ещё одну', service_retry: 'Повторить загрузку услуг',
};

// Схема главной в долях документа (замер Playwright на 1366×900: reports/page_geometry.json): [x, y, w, h, тип]
const SILHOUETTE = [
  [0.1047, 0.016, 0.16, 0.008, 'brand'],
  [0.1047, 0.0444, 0.6589, 0.0503, 'title'],
  [0.1047, 0.104, 0.56, 0.036, 'text'],
  [0.1047, 0.1506, 0.7906, 0.0326, 'facts'],
  [0.1047, 0.2011, 0.6003, 0.7521, 'panel'],
  [0.1376, 0.2624, 0.5345, 0.1399, 'step-service'],
  [0.1376, 0.4158, 0.5345, 0.1288, 'step'],
  [0.1376, 0.5581, 0.5345, 0.1667, 'step'],
  [0.1376, 0.7382, 0.5345, 0.1466, 'step'],
  [0.1567, 0.3058, 0.4963, 0.0227, 'field'],
  [0.1567, 0.3614, 0.4963, 0.0127, 'field'],
  [0.1376, 0.9062, 0.1175, 0.0202, 'button'],
];

function fmtSec(s) {
  const n = Math.round(Number(s) || 0);
  if (n < 60) return `${n} с`;
  return `${Math.floor(n / 60)} мин ${String(n % 60).padStart(2, '0')} с`;
}

function renderPeriods(periods) {
  const names = { day: 'За день', week: 'За неделю', month: 'За месяц' };
  $('#periods').innerHTML = ['day', 'week', 'month'].map((k) => {
    const p = periods[k] || { avg_sec: 0, max_sec: 0, sessions: 0 };
    return `<article class="period" data-period="${k}">
      <h3>${names[k]}</h3>
      <dl>
        <div><dt>Среднее время</dt><dd>${fmtSec(p.avg_sec)}</dd></div>
        <div><dt>Максимум</dt><dd>${fmtSec(p.max_sec)}</dd></div>
        <div><dt>Сессий</dt><dd>${p.sessions}</dd></div>
      </dl>
    </article>`;
  }).join('');
}

function renderTopButtons(list) {
  if (!list.length) { $('#topButtons').innerHTML = '<li class="muted">Кликов пока нет.</li>'; return; }
  const max = list[0].count || 1;
  $('#topButtons').innerHTML = list.map((b) => `<li>
    <span class="bars__name">${esc(BUTTON_NAMES[b.name] || b.name)}</span>
    <span class="bars__track"><i style="width:${(b.count / max) * 100}%"></i></span>
    <b>${b.count}</b></li>`).join('');
}

// Цвет по интенсивности: прохладный сине-зелёный → янтарный → красный
function heatColor(t, alpha) {
  const stops = [[56, 145, 166], [233, 179, 59], [214, 69, 47]];
  const seg = t < 0.5 ? 0 : 1;
  const k = t < 0.5 ? t / 0.5 : (t - 0.5) / 0.5;
  const [a, b] = [stops[seg], stops[seg + 1]];
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * k));
  return `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${alpha})`;
}

let lastStats = null;

function drawHeatmap(stats) {
  const frame = $('#heatFrame');
  const canvas = $('#heatCanvas');
  const aspect = stats.page_aspect || 2.2;
  // Вписываем страницу целиком по высоте рамки
  const availH = Math.max(320, frame.clientHeight - 2);
  const availW = Math.max(160, frame.clientWidth - 2);
  let h = availH;
  let w = h / aspect;
  if (w > availW) { w = availW; h = w * aspect; }
  const dpr = window.devicePixelRatio || 1;
  canvas.style.width = `${Math.round(w)}px`;
  canvas.style.height = `${Math.round(h)}px`;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  // Фон страницы и схематичный силуэт
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, w, h);
  SILHOUETTE.forEach(([x, y, bw, bh, kind]) => {
    const r = kind === 'button' ? 999 : 6;
    ctx.beginPath();
    ctx.roundRect(x * w, y * h, bw * w, bh * h, Math.min(r, (bh * h) / 2));
    if (kind === 'panel') { ctx.fillStyle = '#fbf8f2'; ctx.fill(); ctx.strokeStyle = '#e8dfcf'; ctx.stroke(); }
    else if (kind === 'button') { ctx.fillStyle = '#e6cd8d'; ctx.fill(); }
    else if (kind.startsWith('step')) { ctx.strokeStyle = '#e8dfcf'; ctx.setLineDash([4, 3]); ctx.stroke(); ctx.setLineDash([]); }
    else if (kind === 'field') { ctx.fillStyle = '#ffffff'; ctx.fill(); ctx.strokeStyle = '#dccfb5'; ctx.stroke(); }
    else { ctx.fillStyle = kind === 'title' ? '#e9e3d7' : '#f1ece3'; ctx.fill(); }
  });

  // Круги heatmap
  const cells = stats.heatmap || [];
  const max = cells.reduce((m, c) => Math.max(m, c.count), 1);
  const cell = w / (stats.grid || 40);
  cells.slice().sort((a, b) => a.count - b.count).forEach((c) => {
    const t = Math.sqrt(c.count / max);
    // Ячейка 40×40 на высокой странице вытянута по вертикали — круги крупнее шага сетки,
    // чтобы соседние сливались в пятна, а не выстраивались в ряды точек
    const radius = Math.max(cell * (0.7 + 2.4 * t), (h / (stats.grid || 40)) * (0.45 + 1.2 * t));
    ctx.beginPath();
    ctx.arc(c.x * w, c.y * h, radius, 0, Math.PI * 2);
    ctx.fillStyle = heatColor(t, 0.12 + 0.45 * t);
    ctx.fill();
  });
  if (!cells.length) {
    ctx.fillStyle = '#6e6353';
    ctx.font = '600 13px Nunito, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Данных о курсоре пока нет', w / 2, h / 2);
  }
}

async function loadStats() {
  $('#statsMeta').textContent = 'Загрузка…';
  try {
    const s = await api('/behavior-metrics/stats', { auth: true });
    lastStats = s;
    renderPeriods(s.periods);
    renderTopButtons(s.top_buttons || []);
    $('#statsMeta').textContent = `Таблица behavior_metrics: ${s.total_sessions} сессий · обновлено ${dt(s.generated_at)}`;
    requestAnimationFrame(() => drawHeatmap(s));
  } catch (err) {
    if (err.status === 401) return;
    $('#statsMeta').textContent = `Не удалось загрузить статистику: ${err.message}`;
  }
}

$('#statsBtn').addEventListener('click', () => { openDialog($('#statsDialog')); loadStats(); });
$('#statsReload').addEventListener('click', loadStats);
$('#statsClose').addEventListener('click', () => closeDialog($('#statsDialog')));
window.addEventListener('resize', () => { if ($('#statsDialog').open && lastStats) drawHeatmap(lastStats); });

// =====================================================================
//  Старт: есть токен — проверяем его через /auth/me, нет — экран входа
// =====================================================================
(async function start() {
  if (!getToken()) { showAuth(); return; }
  try {
    await enterApp();
  } catch {
    // 401 уже обработан setUnauthorizedHandler; здесь — прочие сбои (нет связи и т.п.)
    if (authView.hidden) logout();
  }
}());
