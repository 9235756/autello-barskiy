// Приоритизация: после sql/test_applications.sql (make test-sql) первые 4 строки — 🔥,
// «Просмотр» открывает подробности с причинами оценки и ссылками tel:/mailto:.
import { test, expect } from '@playwright/test';
import { apiToken, loginUI, shot, watchBadResponses } from './helpers';

test('заявки по температуре: 4 горячих сверху, просмотр деталей', async ({ page, request }) => {
  const bad = watchBadResponses(page);

  // Тестовые заявки на месте и дают 4/3/3 — проверяем через API
  const token = await apiToken(request);
  const ranked = await (await request.get('/api/applications/ranked', { headers: { Authorization: `Bearer ${token}` } })).json();
  const test10 = ranked.filter((a: { comment: string | null }) => (a.comment || '').startsWith('[тест-SQL]'));
  expect(test10.length, 'нет тестовых заявок — выполните make test-sql').toBe(10);
  const count = (t: string) => test10.filter((a: { scoring: { temperature: string } }) => a.scoring.temperature === t).length;
  expect([count('hot'), count('warm'), count('cold')]).toEqual([4, 3, 3]);

  await loginUI(page);
  await expect(page.getByRole('tab', { name: 'Заявки' })).toHaveAttribute('aria-selected', 'true');
  const rows = page.locator('#appTable tbody tr[data-id]');
  await expect(rows.first()).toBeVisible();

  // Первые 4 строки — горячие (выше всех по score)
  for (let i = 0; i < 4; i += 1) {
    await expect(rows.nth(i).locator('.temp')).toHaveClass(/temp--hot/);
    await expect(rows.nth(i)).toContainText('🔥');
  }
  // Сортировка по score — по убыванию
  const scores = await rows.locator('.score__num').allInnerTexts();
  const nums = scores.map(Number);
  expect(nums).toEqual([...nums].sort((a, b) => b - a));

  // Сводка сверху
  await expect(page.locator('#summary .kpi').first()).toContainText('Всего заявок');
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: shot('applications_ranked'), fullPage: false });

  // Фильтр «Горячие» — только 🔥
  await page.getByRole('button', { name: '🔥 Горячие' }).click();
  await expect(page.locator('#appTable tbody .temp--warm')).toHaveCount(0);
  await page.getByRole('button', { name: 'Все' }).click();

  // --- Просмотр самой горячей тестовой заявки (Кравцова, 81) ---
  const target = page.locator('#appTable tbody tr', { hasText: 'Кравцова' }).first();
  await target.getByRole('button', { name: 'Просмотр' }).click();
  const dlg = page.locator('#appDialog');
  await expect(dlg).toBeVisible();
  await expect(dlg.locator('#appTitle')).toContainText('Кравцова');
  await expect(dlg).toContainText('Причины');
  await expect(dlg).toContainText('Срок «Как можно скорее»: +25');
  await expect(dlg.locator('a[href^="tel:+7"]')).toBeVisible();
  await expect(dlg.locator('a[href^="mailto:"]')).toBeVisible();
  await expect(dlg.locator('.scorecard__num')).toHaveText('81');
  await page.waitForTimeout(300); // анимация появления окна
  await page.screenshot({ path: shot('application_details') });

  await dlg.getByRole('button', { name: 'Закрыть' }).click();
  await expect(dlg).toBeHidden();
  expect(bad, `ошибки загрузки: ${bad.join(', ')}`).toEqual([]);
});
