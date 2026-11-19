// Живая активность на главной: 3 виртуальных посетителя одновременно.
//   «Долгий» — VISIT_SECONDS (по умолчанию 150 с): курсор плавно ходит между элементами формы,
//              клики по полям, ползунку, ролям, кнопкам, уход на другую вкладку и возврат;
//   «Быстрый» — ~25 с, посмотрел услуги и ушёл;
//   «Клиент»  — ~45 с, заполнил форму и отправил заявку.
// Проверяем, что строки behavior_metrics появляются и растут во время визита, затем
// открываем «Статистику пользователей» и снимаем heatmap.
// Итог пишется в reports/visitor_activity.json (его читает scripts/check.sh),
// координаты элементов — в reports/page_geometry.json (для scripts/backfill_metrics.py).
import { test, expect, type Browser, type Page } from '@playwright/test';
import {
  apiToken, glide, glideTo, linger, loginUI, rand, shot, switchTabAndBack, writeReport,
} from './helpers';

const VISIT_SECONDS = Number(process.env.VISIT_SECONDS || 150);
test.setTimeout((VISIT_SECONDS + 150) * 1000);

type Visit = { name: string; seconds: number; session?: string; submitted?: number };

async function openHome(browser: Browser) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: 'ru-RU' });
  const page = await ctx.newPage();
  // session_id виден в первом же снимке метрик (через ~1 с после открытия) — берём его из запроса
  const firstSnapshot = page.waitForRequest((r) => r.url().includes('/api/behavior-metrics') && r.method() === 'POST');
  await page.goto('/?utm_source=e2e&utm_medium=playwright');
  await expect(page.locator('#service')).toBeEnabled();
  const session: string = (await firstSnapshot).postDataJSON().session_id;
  expect(session).toMatch(/^[0-9a-f-]{36}$/);
  return { ctx, page, session };
}

// Набор «целей» для курсора с весами: чаще всего — услуга, бюджет и кнопка «Отправить»
const TARGETS: Array<[string, number]> = [
  ['#service', 5], ['#budget', 5], ['#submitBtn', 3], ['label.chip:has([value="руководитель"])', 2],
  ['label.chip:has([value="собственник"])', 1], ['#last_name', 1], ['#phone', 1], ['#business_niche', 1],
  ['#deadline', 1], ['label.chip:has([value="telegram"])', 1], ['.hero__title', 1], ['#comment', 1],
];
function pickTarget() {
  const total = TARGETS.reduce((s, [, w]) => s + w, 0);
  let r = Math.random() * total;
  for (const [sel, w] of TARGETS) { r -= w; if (r <= 0) return sel; }
  return TARGETS[0][0];
}

async function actOn(page: Page, sel: string) {
  const loc = page.locator(sel).first();
  const at = await glideTo(page, loc);
  if (!at) return;
  if (sel === '#service') {
    await page.mouse.click(at.x, at.y);
    const values = await page.locator('#service option[value]:not([value=""])').evaluateAll((o) => o.map((x) => (x as HTMLOptionElement).value));
    await page.selectOption('#service', values[Math.floor(Math.random() * values.length)]);
  } else if (sel === '#budget') {
    // Тянем ползунок мышью: нажали, повели, отпустили
    await page.mouse.down();
    await glide(page, at.box.x + at.box.width * rand(0.1, 0.9), at.y, rand(300, 700));
    await page.mouse.up();
  } else if (sel === '#submitBtn') {
    // Чаще наводим и думаем, иногда жмём (пустая форма не уйдёт — сработает валидация)
    if (Math.random() < 0.35) await page.mouse.click(at.x, at.y);
  } else if (sel.startsWith('label.chip') || sel.startsWith('#business_niche') || sel === '#deadline') {
    await page.mouse.click(at.x, at.y);
    if (sel === '#business_niche') await page.selectOption(sel, { index: 1 + Math.floor(Math.random() * 5) });
    if (sel === '#deadline') await page.selectOption(sel, { index: 1 + Math.floor(Math.random() * 4) });
  } else if (sel === '#last_name' || sel === '#phone' || sel === '#comment') {
    await page.mouse.click(at.x, at.y);
  }
  await linger(page, rand(400, 2200));
}

async function longVisit(browser: Browser, v: Visit) {
  const { ctx, page, session } = await openHome(browser);
  v.session = session;
  const start = Date.now();
  let switched = 0;
  while ((Date.now() - start) / 1000 < v.seconds) {
    await actOn(page, pickTarget());
    if (Math.random() < 0.12) await page.mouse.wheel(0, rand(-400, 400));
    // Пару раз за визит «уходим на другую вкладку» — растёт return_frequency
    const elapsed = (Date.now() - start) / 1000;
    if ((switched === 0 && elapsed > v.seconds * 0.35) || (switched === 1 && elapsed > v.seconds * 0.7)) {
      await switchTabAndBack(page, 2500);
      switched += 1;
    }
  }
  await ctx.close(); // pagehide → финальный снимок через sendBeacon
}

async function quickVisit(browser: Browser, v: Visit) {
  const { ctx, page, session } = await openHome(browser);
  v.session = session;
  const start = Date.now();
  for (const sel of ['.hero__title', '#service', '#budget', '#service']) await actOn(page, sel);
  const left = v.seconds * 1000 - (Date.now() - start);
  if (left > 0) await linger(page, left);
  await ctx.close();
}

async function customerVisit(browser: Browser, v: Visit) {
  const { ctx, page, session } = await openHome(browser);
  v.session = session;
  const start = Date.now();
  await actOn(page, '#service');
  await page.selectOption('#service', { label: await page.locator('#service option', { hasText: 'Керамическое покрытие' }).innerText() });
  await actOn(page, '#budget');
  const fields: Array<[string, string]> = [['#last_name', 'Посетителев'], ['#first_name', 'Виртуал'], ['#phone', '+7 926 555-01-02'], ['#email', 'visitor@autello.ru']];
  for (const [sel, text] of fields) {
    await glideTo(page, page.locator(sel));
    await page.locator(sel).click();
    await page.keyboard.type(text, { delay: rand(40, 110) });
  }
  await actOn(page, 'label.chip:has([value="руководитель"])');
  await page.selectOption('#deadline', 'В течение недели');
  await page.selectOption('#business_niche', 'Детейлинг-центр');
  const left = v.seconds * 1000 - (Date.now() - start) - 3000;
  if (left > 0) await linger(page, left);
  await glideTo(page, page.locator('#submitBtn'));
  const resp = page.waitForResponse((r) => r.url().endsWith('/api/applications') && r.request().method() === 'POST');
  await page.locator('#submitBtn').click();
  const r = await resp;
  expect(r.status()).toBe(201);
  v.submitted = (await r.json()).id;
  expect(r.request().postDataJSON().session_id).toBe(session);
  await expect(page.getByText('Заявка отправлена!')).toBeVisible();
  await linger(page, 2500);
  await ctx.close();
}

test('3 виртуальных посетителя: метрики растут, heatmap в «Статистике пользователей»', async ({ browser, request, page }) => {
  const token = await apiToken(request);
  const auth = { headers: { Authorization: `Bearer ${token}` } };
  const total = async () => (await (await request.get('/api/behavior-metrics/stats', auth)).json()).total_sessions as number;

  // Геометрия главной: где поле услуги, ползунок, кнопка (доли документа) — для backfill и силуэта
  await page.goto('/');
  await expect(page.locator('#service')).toBeEnabled();
  const geometry = await page.evaluate(() => {
    const d = document.documentElement;
    const W = d.scrollWidth; const H = d.scrollHeight;
    const pick = (sel: string) => {
      const el = document.querySelector(sel); if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: +((r.left + scrollX) / W).toFixed(4), y: +((r.top + scrollY) / H).toFixed(4), w: +(r.width / W).toFixed(4), h: +(r.height / H).toFixed(4) };
    };
    return {
      doc: { w: W, h: H },
      hero: pick('.hero'), title: pick('.hero__title'), facts: pick('.hero__facts'), panel: pick('#panel'),
      service: pick('#service'), budget: pick('#budget'), submit: pick('#submitBtn'),
      steps: [...document.querySelectorAll('fieldset.step')].map((f) => {
        const r = f.getBoundingClientRect(); return { y: +((r.top + scrollY) / H).toFixed(4), h: +(r.height / H).toFixed(4) };
      }),
    };
  });
  writeReport('page_geometry.json', geometry);

  const before = await total();
  const visits: Visit[] = [
    { name: 'Долгий визит', seconds: VISIT_SECONDS },
    { name: 'Быстрый взгляд', seconds: 25 },
    { name: 'Клиент с заявкой', seconds: 45 },
  ];

  // Пока посетители ходят по странице — замеряем рост числа строк
  let during = before;
  const sampler = (async () => {
    await new Promise((r) => setTimeout(r, 12_000));
    during = await total();
  })();
  await Promise.all([longVisit(browser, visits[0]), quickVisit(browser, visits[1]), customerVisit(browser, visits[2]), sampler]);
  await page.waitForTimeout(2000); // последние снимки (sendBeacon) долетают до БД
  const after = await total();

  // Строки визитов в behavior_metrics
  const list = await (await request.get('/api/behavior-metrics?limit=50', auth)).json();
  const rows = visits.map((v) => list.find((m: { session_id: string }) => m.session_id === v.session));
  rows.forEach((row, i) => expect(row, `нет строки визита «${visits[i].name}»`).toBeTruthy());
  const long = rows[0];
  expect(long.time_on_page).toBeGreaterThanOrEqual(VISIT_SECONDS - 10);
  expect(long.return_frequency).toBeGreaterThanOrEqual(1);
  expect(long.cursor_positions.length).toBeGreaterThan(VISIT_SECONDS * 0.6);
  expect(Object.keys(long.buttons_clicked).length).toBeGreaterThan(2);
  expect(rows[2].application_id).toBe(visits[2].submitted);
  expect(during).toBeGreaterThan(before);
  expect(after).toBeGreaterThanOrEqual(before + 3);

  writeReport('visitor_activity.json', {
    finished_at: new Date().toISOString(),
    visit_seconds: VISIT_SECONDS,
    metrics_rows: { before, during_12s: during, after },
    visits: visits.map((v, i) => ({
      name: v.name, session_id: v.session, time_on_page: rows[i].time_on_page, return_frequency: rows[i].return_frequency,
      cursor_points: rows[i].cursor_positions.length, buttons_clicked: rows[i].buttons_clicked, application_id: rows[i].application_id,
    })),
  });

  // --- Статистика пользователей в админке ---
  await loginUI(page);
  await page.getByRole('button', { name: 'Статистика пользователей' }).click();
  const dlg = page.locator('#statsDialog');
  await expect(dlg).toBeVisible();
  await expect(dlg.locator('.period')).toHaveCount(3);
  await expect(dlg.locator('.period[data-period="day"]')).toContainText('Сессий');
  await expect(dlg.locator('#topButtons li').first()).toBeVisible();
  // Canvas нарисован (не пустой)
  await expect.poll(async () => dlg.locator('#heatCanvas').evaluate((c: HTMLCanvasElement) => c.width)).toBeGreaterThan(100);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  await page.screenshot({ path: shot('stats_modal_heatmap') });
});
