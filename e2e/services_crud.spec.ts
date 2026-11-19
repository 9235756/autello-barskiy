// CRUD услуг в таблице админки: 5 новых строк → правка одной → удаление одной (своим окном
// подтверждения) → на главной удалённой услуги нет в выпадающем списке.
import { test, expect, type Page } from '@playwright/test';
import { apiToken, loginUI, shot, watchBadResponses } from './helpers';

const NEW_SERVICES = [
  { name: 'Тонировка стёкол', min: '8000', max: '35000' },
  { name: 'Антидождь и защита стёкол', min: '3000', max: '12000' },
  { name: 'Шумоизоляция салона', min: '40000', max: '180000' },
  { name: 'Мойка и консервация двигателя', min: '3000', max: '9000' },
  { name: 'Защита колёсных дисков', min: '10000', max: '45000' },
];
const EDITED = { from: 'Тонировка стёкол', to: 'Тонировка стёкол (плёнка LLumar)', max: '42000' };
const DELETED = 'Мойка и консервация двигателя';

async function addRow(page: Page, s: { name: string; min: string; max: string }) {
  await page.getByRole('button', { name: 'Добавить строку' }).click();
  const row = page.locator('#svcTable tr.is-editing');
  await expect(row).toBeVisible();
  await row.locator('[name=services]').fill(s.name);
  await row.locator('[name=budget_min]').fill(s.min);
  await row.locator('[name=budget_max]').fill(s.max);
  const resp = page.waitForResponse((r) => r.url().endsWith('/api/admin-settings') && r.request().method() === 'POST');
  await row.getByRole('button', { name: 'Сохранить' }).click();
  expect((await resp).status()).toBe(201);
  await expect(page.locator('#svcTable tbody tr', { hasText: s.name })).toHaveCount(1);
}

test('услуги: добавить 5, изменить, удалить, проверить главную', async ({ page, request }) => {
  const bad = watchBadResponses(page);

  // Идемпотентность: убираем следы прошлого прогона (через API с токеном)
  const token = await apiToken(request);
  const existing = await (await request.get('/api/admin-settings')).json();
  expect(Array.isArray(existing), 'GET /api/admin-settings должен вернуть массив').toBe(true);
  const ours = new Set([...NEW_SERVICES.map((s) => s.name), EDITED.to]);
  for (const s of existing.filter((x: { services: string }) => ours.has(x.services))) {
    await request.delete(`/api/admin-settings/${s.id}`, { headers: { Authorization: `Bearer ${token}` } });
  }

  await loginUI(page);
  await page.getByRole('tab', { name: 'Услуги' }).click();
  await expect(page.locator('#svcTable tbody tr').first()).toBeVisible();

  // --- Создание 5 услуг через «Добавить строку» в панели инструментов справа ---
  for (const s of NEW_SERVICES) await addRow(page, s);

  // --- Редактирование в строке: двойной щелчок → поля → Enter ---
  const editRow = page.locator('#svcTable tbody tr', { hasText: EDITED.from }).first();
  await editRow.dblclick();
  const editing = page.locator('#svcTable tr.is-editing');
  await editing.locator('[name=services]').fill(EDITED.to);
  await editing.locator('[name=budget_max]').fill(EDITED.max);
  const put = page.waitForResponse((r) => r.request().method() === 'PUT');
  await editing.locator('[name=budget_max]').press('Enter');
  expect((await put).status()).toBe(200);
  await expect(page.locator('#svcTable tbody tr', { hasText: EDITED.to })).toContainText('42 000');

  // --- Удаление через своё модальное окно (не window.confirm) ---
  let nativeDialog = false;
  page.on('dialog', (d) => { nativeDialog = true; d.dismiss(); });
  await page.locator('#svcTable tbody tr', { hasText: DELETED }).getByRole('button', { name: /Удалить/ }).click();
  const confirm = page.locator('#confirmDialog');
  await expect(confirm).toBeVisible();
  await expect(confirm).toContainText(DELETED);
  const del = page.waitForResponse((r) => r.request().method() === 'DELETE');
  await confirm.getByRole('button', { name: 'Удалить' }).click();
  expect((await del).status()).toBe(204);
  await expect(page.locator('#svcTable tbody tr', { hasText: DELETED })).toHaveCount(0);
  expect(nativeDialog, 'window.confirm использоваться не должен').toBe(false);

  const rows = await page.locator('#svcTable tbody tr').count();
  expect(rows).toBeGreaterThanOrEqual(5);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: shot('services_table'), fullPage: true });

  // --- Главная: удалённой услуги нет, изменённая — с новым названием ---
  await page.goto('/');
  const select = page.locator('#service');
  await expect(select).toBeEnabled();
  await expect(select.locator('option', { hasText: DELETED })).toHaveCount(0);
  await expect(select.locator('option', { hasText: EDITED.to })).toHaveCount(1);
  await expect(select.locator('option', { hasText: 'Оклейка плёнкой PPF' })).toHaveCount(1);
  // Нативный выпадающий список на скриншот не попадает — раскрываем его как listbox
  await select.evaluate((el: HTMLSelectElement) => { el.size = el.options.length; el.style.height = 'auto'; });
  await select.scrollIntoViewIfNeeded();
  await page.evaluate(() => document.fonts.ready);
  await page.locator('.step--service').screenshot({ path: shot('home_service_list') });

  expect(bad, `ошибки загрузки: ${bad.join(', ')}`).toEqual([]);
});
