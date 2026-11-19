// 1) Вход в админку: на чистой БД есть «Зарегистрироваться» → регистрация → выход → кнопки больше нет.
// 2) Swagger UI: кнопка Authorize → логин → защищённый GET /api/auth/me отвечает 200.
// make e2e в режиме эмуляции перед запуском очищает таблицу admins, чтобы БД была «чистой».
import { test, expect } from '@playwright/test';
import { ADMIN, BACKEND_URL, shot, watchBadResponses } from './helpers';

test.describe.configure({ mode: 'serial' });

test('регистрация первого админа, выход, кнопка «Зарегистрироваться» исчезла', async ({ page, request }) => {
  const bad = watchBadResponses(page, [401]);
  const check = await (await request.get('/api/auth/check')).json();

  await page.goto('/admin');
  await expect(page.locator('#authView')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);

  if (check.has_admins) {
    // БД не чистая (запуск отдельного spec или MOCK_MODE=false) — регистрацию проверить нельзя
    test.info().annotations.push({ type: 'warning', description: 'Админ уже есть: регистрация пропущена, скриншот login_with_register не обновлён' });
    await expect(page.getByRole('button', { name: 'Зарегистрироваться' })).toBeHidden();
  } else {
    // --- Чистая БД: кнопка есть ---
    const registerBtn = page.getByRole('button', { name: 'Зарегистрироваться' });
    await expect(registerBtn).toBeVisible();
    await page.screenshot({ path: shot('login_with_register') });

    // --- Регистрация ---
    await registerBtn.click();
    await expect(page.locator('#authTitle')).toHaveText('Регистрация администратора');
    await page.fill('#authUser', ADMIN.username);
    await page.fill('#authPass', ADMIN.password);
    const reg = page.waitForResponse((r) => r.url().includes('/api/auth/register'));
    await page.click('#authSubmit');
    expect((await reg).status()).toBe(201);
    await expect(page.locator('#appView')).toBeVisible();
    await expect(page.locator('#whoami')).toHaveText(ADMIN.username);

    // Повторная регистрация через API — 403
    const again = await request.post('/api/auth/register', { data: { username: 'second_admin', password: 'another_pass_123' } });
    expect(again.status()).toBe(403);

    // --- Выход ---
    await page.getByRole('button', { name: 'Выйти' }).click();
    await expect(page.locator('#authView')).toBeVisible();
  }

  // --- Кнопки «Зарегистрироваться» больше нет ---
  await expect(page.locator('#registerBox')).toBeHidden();
  await expect(page.getByRole('button', { name: 'Зарегистрироваться' })).toBeHidden();
  await page.screenshot({ path: shot('login_without_register') });

  // Неверный пароль — сообщение, а не вход
  await page.fill('#authUser', ADMIN.username);
  await page.fill('#authPass', 'wrong_password');
  await page.click('#authSubmit');
  await expect(page.locator('#authMsg')).toHaveText('Неверный логин или пароль');

  // Верный — вход; после перезагрузки токен из sessionStorage сохраняет сессию
  await page.fill('#authPass', ADMIN.password);
  await page.click('#authSubmit');
  await expect(page.locator('#appView')).toBeVisible();
  await page.reload();
  await expect(page.locator('#appView')).toBeVisible();

  // Протухший/поддельный токен → 401 → экран входа
  await page.evaluate(() => sessionStorage.setItem('autello_token', 'broken.token.value'));
  await page.reload();
  await expect(page.locator('#authView')).toBeVisible();

  expect(bad, `ошибки загрузки: ${bad.join(', ')}`).toEqual([]);
});

test('Swagger: Authorize → GET /api/auth/me = 200', async ({ page }) => {
  test.skip((process.env.DOCS_ENABLED || 'true') !== 'true', 'DOCS_ENABLED=false — Swagger закрыт');
  await page.goto(`${BACKEND_URL}/docs`);
  await expect(page.locator('.swagger-ui .info .title')).toContainText('Autello');

  await page.locator('.swagger-ui .auth-wrapper .btn.authorize').click();
  const modal = page.locator('.swagger-ui .modal-ux');
  await expect(modal).toBeVisible();
  await modal.locator('#oauth_username').fill(ADMIN.username);
  await modal.locator('#oauth_password').fill(ADMIN.password);
  await modal.locator('.auth-btn-wrapper .btn.modal-btn.auth.authorize').click();
  await expect(modal.getByText('Logout')).toBeVisible();
  await modal.locator('.btn-done').click();
  await expect(modal).toBeHidden();
  // Замок у кнопки Authorize закрылся
  await expect(page.locator('.swagger-ui .auth-wrapper .btn.authorize.locked')).toBeVisible();

  const op = page.locator('.opblock-get', { has: page.locator('[data-path="/api/auth/me"]') }).first();
  await op.locator('.opblock-summary').click();
  await op.getByRole('button', { name: 'Try it out' }).click();
  await op.getByRole('button', { name: 'Execute' }).click();
  const live = op.locator('.responses-wrapper .live-responses-table');
  await expect(live).toContainText('200');
  await expect(live).toContainText(ADMIN.username);
  await op.scrollIntoViewIfNeeded();
  await page.screenshot({ path: shot('swagger_authorized'), fullPage: false });
});
