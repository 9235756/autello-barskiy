// Админка: CRUD услуг через /api/admin-settings и просмотр последних заявок.
// TODO (следующий урок): авторизация по ADMIN_TOKEN — заголовок Authorization: Bearer ...
import './styles/base.css';
import './styles/main.css';
import './styles/admin.css';
import { api, rub } from './api';

const $ = (sel) => document.querySelector(sel);
const svcBody = $('#svcTable tbody');
const appBody = $('#appTable tbody');
const svcMsg = $('#svcMsg');

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const dt = (iso) => new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

function message(text, isError = false) {
  svcMsg.textContent = text;
  svcMsg.classList.toggle('is-error', isError);
}

// ---------- Услуги ----------
let services = [];
let editingId = null;

function rowView(s) {
  return `<tr data-id="${s.id}">
    <td>${s.id}</td>
    <td><strong>${esc(s.services)}</strong></td>
    <td>${esc(s.budget_range)}</td>
    <td class="num">${rub(s.budget_min)}</td>
    <td class="num">${rub(s.budget_max)}</td>
    <td><span class="pill ${s.is_active ? 'pill--on' : 'pill--off'}">${s.is_active ? 'да' : 'нет'}</span></td>
    <td>${dt(s.updated_at)}</td>
    <td><div class="actions">
      <button class="btn btn--ghost btn--small" data-act="edit">Изменить</button>
      <button class="btn btn--danger btn--small" data-act="delete">Удалить</button>
    </div></td>
  </tr>`;
}

function rowEdit(s) {
  return `<tr data-id="${s.id}" class="is-editing">
    <td>${s.id}</td>
    <td><input name="services" value="${esc(s.services)}" aria-label="Название"></td>
    <td><input name="budget_range" value="${esc(s.budget_range)}" aria-label="Подпись"></td>
    <td class="num"><input name="budget_min" type="number" min="0" step="1000" value="${s.budget_min}" aria-label="Бюджет от"></td>
    <td class="num"><input name="budget_max" type="number" min="0" step="1000" value="${s.budget_max}" aria-label="Бюджет до"></td>
    <td><input name="is_active" type="checkbox" ${s.is_active ? 'checked' : ''} aria-label="Активна"></td>
    <td>${dt(s.updated_at)}</td>
    <td><div class="actions">
      <button class="btn btn--small" data-act="save">Сохранить</button>
      <button class="btn btn--ghost btn--small" data-act="cancel">Отмена</button>
    </div></td>
  </tr>`;
}

function renderServices() {
  if (!services.length) {
    svcBody.innerHTML = '<tr><td colspan="8" class="muted">Услуг пока нет — добавьте первую формой выше или через Swagger (/docs).</td></tr>';
    return;
  }
  svcBody.innerHTML = services.map((s) => (s.id === editingId ? rowEdit(s) : rowView(s))).join('');
}

async function loadServices() {
  try {
    services = await api('/admin-settings');
    renderServices();
  } catch (err) {
    svcBody.innerHTML = `<tr><td colspan="8" class="msg is-error">Не удалось загрузить услуги: ${esc(err.message)}</td></tr>`;
  }
}

svcBody.addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-act]');
  if (!btn) return;
  const tr = btn.closest('tr');
  const id = Number(tr.dataset.id);
  const s = services.find((x) => x.id === id);
  const act = btn.dataset.act;

  if (act === 'edit') { editingId = id; renderServices(); svcBody.querySelector('tr.is-editing input')?.focus(); return; }
  if (act === 'cancel') { editingId = null; renderServices(); return; }
  if (act === 'delete') {
    if (!window.confirm(`Удалить услугу «${s.services}»? Заявки останутся, но без привязки к услуге.`)) return;
    try {
      await api(`/admin-settings/${id}`, { method: 'DELETE' });
      message(`Услуга «${s.services}» удалена`);
      await loadServices();
    } catch (err) { message(err.message, true); }
    return;
  }
  if (act === 'save') {
    const body = {
      services: tr.querySelector('[name=services]').value.trim(),
      budget_range: tr.querySelector('[name=budget_range]').value.trim(),
      budget_min: Number(tr.querySelector('[name=budget_min]').value),
      budget_max: Number(tr.querySelector('[name=budget_max]').value),
      is_active: tr.querySelector('[name=is_active]').checked,
    };
    if (body.budget_min > body.budget_max) { message('«От» не может быть больше «до»', true); return; }
    try {
      await api(`/admin-settings/${id}`, { method: 'PUT', body });
      editingId = null;
      message('Изменения сохранены');
      await loadServices();
    } catch (err) { message(err.message, true); }
  }
});

$('#svcForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.currentTarget;
  const body = {
    services: f.services.value.trim(),
    budget_min: Number(f.budget_min.value),
    budget_max: Number(f.budget_max.value),
  };
  if (f.budget_range.value.trim()) body.budget_range = f.budget_range.value.trim();
  if (body.services.length < 2 || !f.budget_min.value || !f.budget_max.value) {
    message('Заполните название и обе границы бюджета', true);
    return;
  }
  if (body.budget_min > body.budget_max) { message('«От» не может быть больше «до»', true); return; }
  try {
    const created = await api('/admin-settings', { method: 'POST', body });
    message(`Добавлена услуга «${created.services}» (id ${created.id})`);
    f.reset();
    await loadServices();
  } catch (err) { message(err.message, true); }
});

$('#reloadServices').addEventListener('click', loadServices);

// ---------- Заявки ----------
const contactName = { phone: 'звонок', telegram: 'Telegram', whatsapp: 'WhatsApp', email: 'email' };

async function loadApps() {
  try {
    const apps = await api('/applications?limit=20');
    if (!apps.length) {
      appBody.innerHTML = '<tr><td colspan="11" class="muted">Заявок пока нет.</td></tr>';
      return;
    }
    appBody.innerHTML = apps.map((a) => {
      const m = a.metrics || {};
      const utm = m.utm && m.utm.utm_source ? `${m.utm.utm_source}${m.utm.utm_medium ? ' / ' + m.utm.utm_medium : ''}` : '—';
      return `<tr>
        <td>${a.id}</td>
        <td>${dt(a.created_at)}</td>
        <td>${esc([a.last_name, a.first_name, a.middle_name].filter(Boolean).join(' '))}</td>
        <td>${esc(a.phone)}</td>
        <td>${esc(a.service_name || '—')}</td>
        <td class="num">${a.budget ? rub(a.budget) : '—'}</td>
        <td>${esc(a.role)}</td>
        <td>${esc(contactName[a.contact_method] || a.contact_method || '—')}</td>
        <td class="num">${m.time_on_page_sec != null ? `${m.time_on_page_sec} с` : '—'}</td>
        <td class="num">${m.clicks ? m.clicks.length : '—'}</td>
        <td>${esc(utm)}</td>
      </tr>`;
    }).join('');
  } catch (err) {
    appBody.innerHTML = `<tr><td colspan="11" class="msg is-error">Не удалось загрузить заявки: ${esc(err.message)}</td></tr>`;
  }
}

$('#reloadApps').addEventListener('click', loadApps);

loadServices();
loadApps();
