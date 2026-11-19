// Конфиг Playwright. Версия @playwright/test = версии образа mcr.microsoft.com/playwright:v1.49.1
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  workers: 1,
  retries: 0,
  reporter: [['list']],
  outputDir: '/reports/e2e-results',
  use: {
    baseURL: process.env.BASE_URL || 'http://nginx',
    viewport: { width: 1366, height: 900 },
    locale: 'ru-RU',
    deviceScaleFactor: 1,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
