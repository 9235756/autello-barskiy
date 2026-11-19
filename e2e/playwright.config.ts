// Конфиг Playwright. Версия @playwright/test = версии образа mcr.microsoft.com/playwright:v1.49.1
// Порядок файлов — алфавитный: admin_auth (регистрация первого админа) идёт первым.
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.ts$/,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  outputDir: '/reports/e2e-results',
  use: {
    baseURL: process.env.BASE_URL || 'http://nginx',
    viewport: { width: 1366, height: 900 },
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
    deviceScaleFactor: 1,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
