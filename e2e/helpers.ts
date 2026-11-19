// Общие функции e2e: адреса, демо-админ, вход через интерфейс и через API, «живое» движение мыши.
import { expect, type APIRequestContext, type Locator, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

export const SHOTS = process.env.SCREENS_DIR || '/reports/screens';
export const REPORTS = process.env.REPORTS_DIR || '/reports';
export const BACKEND_URL = process.env.BACKEND_URL || 'http://backend:8000';
export const ADMIN = {
  username: process.env.DEMO_ADMIN_USER || 'admin',
  password: process.env.DEMO_ADMIN_PASSWORD || 'change_me_demo',
};
fs.mkdirSync(SHOTS, { recursive: true });

export const shot = (name: string) => path.join(SHOTS, `${name}.png`);

export function writeReport(name: string, data: unknown) {
  fs.writeFileSync(path.join(REPORTS, name), JSON.stringify(data, null, 2));
}

/** JWT демо-админа через API (для подготовки данных и проверок). */
export async function apiToken(request: APIRequestContext): Promise<string> {
  const res = await request.post('/api/auth/login', { form: { username: ADMIN.username, password: ADMIN.password } });
  expect(res.status(), 'логин демо-админа (DEMO_ADMIN_USER / DEMO_ADMIN_PASSWORD)').toBe(200);
  return (await res.json()).access_token;
}

/** Вход через экран /admin — как это делает человек. */
export async function loginUI(page: Page) {
  await page.goto('/admin');
  await expect(page.locator('#authView')).toBeVisible();
  await page.fill('#authUser', ADMIN.username);
  await page.fill('#authPass', ADMIN.password);
  await page.click('#authSubmit');
  await expect(page.locator('#appView')).toBeVisible();
  await expect(page.locator('#whoami')).toHaveText(ADMIN.username);
}

/** Ловим 4xx/5xx по статике и API нашего хоста (CSS 404 из урока не должен проскочить). */
export function watchBadResponses(page: Page, allow: number[] = []) {
  const bad: string[] = [];
  const ourHost = new URL(process.env.BASE_URL || 'http://nginx').hostname;
  page.on('response', (r) => {
    const url = new URL(r.url());
    if (url.hostname === ourHost && r.status() >= 400 && !allow.includes(r.status())) bad.push(`${r.status()} ${url.pathname}`);
  });
  return bad;
}

// ---------- «Живая» мышь: плавные кривые Безье между элементами ----------
const mouse = new WeakMap<Page, { x: number; y: number }>();

export function rand(min: number, max: number) {
  return min + Math.random() * (max - min);
}

/** Плавно ведёт курсор по кубической кривой Безье в точку (x, y) за ~ms миллисекунд. */
export async function glide(page: Page, x: number, y: number, ms = rand(350, 900)) {
  const from = mouse.get(page) || { x: rand(200, 900), y: rand(100, 500) };
  const steps = Math.max(8, Math.round(ms / 25));
  const c1 = { x: from.x + (x - from.x) * rand(0.1, 0.4) + rand(-120, 120), y: from.y + (y - from.y) * rand(0.1, 0.4) + rand(-80, 80) };
  const c2 = { x: from.x + (x - from.x) * rand(0.6, 0.9) + rand(-60, 60), y: from.y + (y - from.y) * rand(0.6, 0.9) + rand(-40, 40) };
  for (let i = 1; i <= steps; i += 1) {
    const t = i / steps;
    const e = t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2; // ease-in-out: разгон и торможение
    const bx = (1 - e) ** 3 * from.x + 3 * (1 - e) ** 2 * e * c1.x + 3 * (1 - e) * e ** 2 * c2.x + e ** 3 * x;
    const by = (1 - e) ** 3 * from.y + 3 * (1 - e) ** 2 * e * c1.y + 3 * (1 - e) * e ** 2 * c2.y + e ** 3 * y;
    await page.mouse.move(bx, by);
    await page.waitForTimeout(ms / steps);
  }
  mouse.set(page, { x, y });
}

/** Подвести курсор к элементу (с прокруткой) в случайную точку внутри него. */
export async function glideTo(page: Page, loc: Locator, ms?: number) {
  await loc.scrollIntoViewIfNeeded();
  const box = await loc.boundingBox();
  if (!box) return null;
  const x = box.x + box.width * rand(0.2, 0.8);
  const y = box.y + box.height * rand(0.3, 0.7);
  await glide(page, x, y, ms);
  return { x, y, box };
}

/** Небольшое «дрожание» курсора на месте — человек читает или думает. */
export async function linger(page: Page, ms: number) {
  const p = mouse.get(page);
  const until = Date.now() + ms;
  while (Date.now() < until) {
    if (p) await page.mouse.move(p.x + rand(-6, 6), p.y + rand(-4, 4));
    await page.waitForTimeout(rand(180, 420));
  }
}

/**
 * Ушёл на другую вкладку и вернулся. В headless-браузере вкладок «на экране» нет,
 * поэтому подменяем document.visibilityState и шлём настоящее событие visibilitychange —
 * трекер (behavior-metrics.js) реагирует на него так же, как на переключение вкладки.
 */
export async function switchTabAndBack(page: Page, awayMs = 2500) {
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.waitForTimeout(awayMs);
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
}
