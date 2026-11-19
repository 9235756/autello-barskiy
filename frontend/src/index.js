// Клиентская страница: загрузка услуг, ползунок бюджета, валидация и отправка заявки.
import './styles/base.css';
import './styles/main.css';
import { api, rub } from './api';
import { getMetrics } from './tracker';

const $ = (sel) => document.querySelector(sel);

const form = $('#leadForm');
const serviceSel = $('#service');
const serviceWrap = $('#serviceWrap');
const serviceStatus = $('#serviceStatus');
const serviceRetry = $('#serviceRetry');
const budget = $('#budget');
const budgetOut = $('#budgetOut');
const budgetMin = $('#budgetMin');
const budgetMax = $('#budgetMax');
const submitBtn = $('#submitBtn');
const formError = $('#formError');
const success = $('#success');

let services = [];

// ---------- Услуги ----------
function setServiceState(state, message) {
  serviceWrap.dataset.state = state;
  serviceStatus.textContent = message || '';
  serviceStatus.classList.toggle('is-error', state === 'error');
  serviceRetry.hidden = state !== 'error';
}

async function loadServices() {
  setServiceState('loading', 'Загружаем список услуг…');
  serviceSel.disabled = true;
  serviceSel.innerHTML = '<option value="">Загружаем услуги…</option>';
  try {
    // ВЕСЬ список (getAll), а не «последняя запись» — иначе в списке одна услуга или вечная загрузка
    const all = await api('/admin-settings?only_active=true', { timeout: 8000 });
    services = Array.isArray(all) ? all : [];
    if (!services.length) {
      serviceSel.innerHTML = '<option value="">Услуги пока не добавлены</option>';
      setServiceState('empty', 'Администратор ещё не добавил услуги. Загляните позже или позвоните нам.');
      return;
    }
    serviceSel.innerHTML = '<option value="">Выберите услугу…</option>' + services
      .map((s) => `<option value="${s.id}">${escapeHtml(s.services)} · ${escapeHtml(s.budget_range)}</option>`)
      .join('');
    serviceSel.disabled = false;
    setServiceState('ready', `Доступно услуг: ${services.length}`);
  } catch (err) {
    serviceSel.innerHTML = '<option value="">Не удалось загрузить</option>';
    setServiceState('error', `Не удалось загрузить услуги: ${err.message}.`);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ---------- Ползунок бюджета ----------
function niceStep(min, max) {
  const span = max - min;
  if (span <= 20000) return 500;
  if (span <= 200000) return 1000;
  return 5000;
}

function paintBudget() {
  const min = Number(budget.min);
  const max = Number(budget.max);
  const val = Number(budget.value);
  const pct = max > min ? ((val - min) / (max - min)) * 100 : 0;
  budget.style.setProperty('--pct', `${pct}%`);
  budgetOut.textContent = budget.disabled ? '—' : rub(val);
}

function applyService() {
  const s = services.find((x) => String(x.id) === serviceSel.value);
  clearError('service_id');
  if (!s) {
    budget.disabled = true;
    budget.min = 0; budget.max = 0; budget.value = 0;
    budgetMin.textContent = 'Выберите услугу';
    budgetMax.textContent = '';
    paintBudget();
    return;
  }
  budget.disabled = false;
  budget.min = s.budget_min;
  budget.max = s.budget_max;
  budget.step = niceStep(s.budget_min, s.budget_max);
  // стартуем с середины диапазона, округлённой до шага
  const mid = s.budget_min + Math.round((s.budget_max - s.budget_min) / 2 / budget.step) * budget.step;
  budget.value = Math.min(s.budget_max, mid);
  budgetMin.textContent = rub(s.budget_min);
  budgetMax.textContent = rub(s.budget_max);
  paintBudget();
}

serviceSel.addEventListener('change', applyService);
budget.addEventListener('input', paintBudget);
serviceRetry.addEventListener('click', loadServices);

// ---------- Валидация ----------
const PHONE_RE = /^\+?[0-9 ()-]{10,20}$/;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function fieldTarget(name) {
  if (name === 'role') return form.querySelector('[data-field="role"] .chips');
  return form.elements[name];
}

function setError(name, msg) {
  const el = $(`#err-${name}`);
  if (el) el.textContent = msg;
  const target = fieldTarget(name);
  if (target && target.setAttribute) target.setAttribute('aria-invalid', 'true');
}

function clearError(name) {
  const el = $(`#err-${name}`);
  if (el) el.textContent = '';
  const target = fieldTarget(name);
  if (target && target.removeAttribute) target.removeAttribute('aria-invalid');
}

function validate(data) {
  const errors = {};
  if (!data.service_id) errors.service_id = 'Выберите услугу из списка';
  if (!data.last_name) errors.last_name = 'Укажите фамилию';
  if (!data.first_name) errors.first_name = 'Укажите имя';
  if (!data.phone) errors.phone = 'Укажите телефон';
  else if (!PHONE_RE.test(data.phone) || data.phone.replace(/\D/g, '').length < 10) errors.phone = 'Например: +7 916 123-45-67';
  if (data.email && !EMAIL_RE.test(data.email)) errors.email = 'Проверьте адрес почты';
  if (!data.role) errors.role = 'Выберите роль';
  return errors;
}

form.addEventListener('input', (e) => { if (e.target.name) clearError(e.target.name); });
form.addEventListener('change', (e) => { if (e.target.name) clearError(e.target.name); });

function collect() {
  const fd = new FormData(form);
  const get = (k) => {
    const v = fd.get(k);
    return v == null ? null : String(v).trim() || null;
  };
  return {
    last_name: get('last_name'),
    first_name: get('first_name'),
    middle_name: get('middle_name'),
    phone: get('phone'),
    email: get('email'),
    service_id: serviceSel.value ? Number(serviceSel.value) : null,
    business_niche: get('business_niche'),
    company_size: get('company_size'),
    task_volume: get('task_volume'),
    role: get('role'),
    need_volume: get('need_volume'),
    deadline: get('deadline'),
    task_type: get('task_type'),
    product_interest: get('product_interest'),
    budget: budget.disabled ? null : String(budget.value),
    contact_method: get('contact_method'),
    contact_time: get('contact_time'),
    comment: get('comment'),
  };
}

// ---------- Отправка ----------
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  formError.textContent = '';
  const application = collect();
  const errors = validate(application);
  Object.keys(application).forEach(clearError);
  if (Object.keys(errors).length) {
    Object.entries(errors).forEach(([k, v]) => setError(k, v));
    const first = fieldTarget(Object.keys(errors)[0]);
    const focusEl = first && (first.focus ? first : first.querySelector && first.querySelector('input'));
    if (focusEl && focusEl.focus) focusEl.focus();
    formError.textContent = 'Проверьте отмеченные поля.';
    return;
  }

  submitBtn.disabled = true;
  submitBtn.classList.add('is-loading');
  try {
    // Заявка и метрики — ОДНИМ пакетом, backend сохраняет их в одной транзакции
    const res = await api('/applications', { method: 'POST', body: { application, metrics: getMetrics() } });
    showSuccess(res);
  } catch (err) {
    formError.textContent = `Не удалось отправить заявку: ${err.message}. Попробуйте ещё раз.`;
  } finally {
    submitBtn.disabled = false;
    submitBtn.classList.remove('is-loading');
  }
});

function showSuccess(res) {
  form.hidden = true;
  $('#successMeta').textContent = res && res.id ? `Номер заявки: ${res.id}` : '';
  success.hidden = false;
  success.focus({ preventScroll: true });
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  $('#panel').scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
}

$('#again').addEventListener('click', () => {
  form.reset();
  applyService();
  success.hidden = true;
  form.hidden = false;
  serviceSel.focus();
});

loadServices();
