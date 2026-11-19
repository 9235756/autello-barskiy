// Браузерный тест: главная → выбор услуги → ползунок → форма → «Заявка отправлена!».
// Плюс скриншоты /admin и /docs для сдачи. Всё складывается в reports/screens/.
import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs';

const SHOTS = process.env.SCREENS_DIR || '/reports/screens';
const DOCS_ENABLED = (process.env.DOCS_ENABLED || 'false').toLowerCase() === 'true';
fs.mkdirSync(SHOTS, { recursive: true });

// Ловим 4xx/5xx по статике и API — CSS 404 из урока не должен проскочить незамеченным
function watchBadResponses(page: Page) {
  const bad: string[] = [];
  const ourHost = new URL(process.env.BASE_URL || 'http://nginx').hostname;
  page.on('response', (r) => {
    const url = new URL(r.url());
    if (url.hostname === ourHost && r.status() >= 400) {
      bad.push(`${r.status()} ${url.pathname}`);
    }
  });
  return bad;
}

test.describe.configure({ mode: 'serial' });

test('главная: выбор услуги, заполнение формы, «Заявка отправлена!»', async ({ page }) => {
  const bad = watchBadResponses(page);
  await page.goto('/?utm_source=yandex&utm_medium=cpc&utm_campaign=e2e_playwright');

  // CSS реально применился: фон body белый, шрифт округлый
  const bodyFont = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
  expect(bodyFont).toContain('Nunito');

  // Дожидаемся загрузки услуг (без бесконечного «Загружаем…»)
  const service = page.locator('#service');
  await expect(service).toBeEnabled();
  await expect(service.locator('option', { hasText: 'Керамическое покрытие' })).toHaveCount(1);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${SHOTS}/01_home.png` });

  // Немного «живого» поведения для трекера: наведение > 500 мс
  await page.hover('#service');
  await page.waitForTimeout(650);
  await page.mouse.move(5, 5);

  await service.selectOption({ label: await service.locator('option', { hasText: 'Керамическое покрытие' }).innerText() });

  // Ползунок получил границы услуги «Керамическое покрытие» (50 000 – 250 000)
  const budget = page.locator('#budget');
  await expect(budget).toBeEnabled();
  await expect(budget).toHaveAttribute('min', '50000');
  await expect(budget).toHaveAttribute('max', '250000');
  await budget.fill('180000');
  await expect(page.locator('#budgetOut')).toContainText('180');

  await page.fill('#last_name', 'Тестов');
  await page.fill('#first_name', 'Playwright');
  await page.fill('#middle_name', 'Автотестович');
  await page.fill('#phone', '+7 916 000-11-22');
  await page.fill('#email', 'e2e@autello.ru');
  await page.locator('label.chip', { hasText: 'Руководитель' }).click();
  await page.selectOption('#business_niche', 'Детейлинг-центр');
  await page.selectOption('#company_size', '11–50 человек');
  await page.selectOption('#task_type', 'Защита нового автомобиля');
  await page.selectOption('#need_volume', '2–5 автомобилей');
  await page.selectOption('#task_volume', 'Несколько раз в год');
  await page.selectOption('#deadline', 'В течение недели');
  await page.selectOption('#product_interest', 'Комплекс услуг');
  await page.locator('label.chip', { hasText: 'Telegram' }).click();
  await page.selectOption('#contact_time', 'Вечер, 17:00–21:00');
  await page.fill('#comment', 'Porsche Cayenne 2024, нужна керамика в 2 слоя. Заявка создана e2e-тестом.');
  await page.screenshot({ path: `${SHOTS}/02_filled.png`, fullPage: true });

  const responsePromise = page.waitForResponse(
    (r) => r.url().endsWith('/api/applications') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Отправить' }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(201);
  const body = await response.json();
  expect(body.message).toBe('Заявка отправлена!');
  expect(typeof body.id).toBe('number');

  // Метрики ушли тем же пакетом
  const sent = response.request().postDataJSON();
  expect(sent.metrics.utm.utm_source).toBe('yandex');
  expect(sent.metrics.clicks.length).toBeGreaterThan(0);

  await expect(page.getByText('Заявка отправлена!')).toBeVisible();
  await expect(page.getByText('Мы свяжемся с вами в ближайшее время.')).toBeVisible();
  await page.waitForTimeout(1200); // даём доиграть анимации галочки
  await page.screenshot({ path: `${SHOTS}/03_success.png` });

  expect(bad, `ошибки загрузки: ${bad.join(', ')}`).toEqual([]);
});

test('админка: услуги и последние заявки', async ({ page }) => {
  const bad = watchBadResponses(page);
  await page.goto('/admin');
  await expect(page.locator('#svcTable tbody tr', { hasText: 'Керамическое покрытие' })).toHaveCount(1);
  await expect(page.locator('#appTable tbody tr', { hasText: 'Тестов' }).first()).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${SHOTS}/04_admin.png`, fullPage: true });
  expect(bad, `ошибки загрузки: ${bad.join(', ')}`).toEqual([]);
});

test('Swagger: /docs и GET /api/admin-settings через Try it out', async ({ page }) => {
  test.skip(!DOCS_ENABLED, 'DOCS_ENABLED=false — Swagger закрыт, как и должно быть в продакшене');
  await page.goto('/docs');
  const op = page.locator('.opblock-get', { hasText: '/api/admin-settings' }).first();
  await expect(op).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/05_docs.png`, fullPage: true });

  await op.locator('.opblock-summary').click();
  await op.getByRole('button', { name: 'Try it out' }).click();
  await op.getByRole('button', { name: 'Execute' }).click();
  const resp = op.locator('.responses-wrapper .live-responses-table');
  await expect(resp).toContainText('200');
  await expect(resp).toContainText('Керамическое покрытие');
  await op.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${SHOTS}/06_docs_get_list.png`, fullPage: true });
});
