import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './sol', testMatch: '*.spec.ts', workers: 1, fullyParallel: false, timeout: 45000,
  reporter: [['list'], ['json', { outputFile: '../outputs/visual-review/sol-final/results.json' }]],
  outputDir: '../outputs/visual-review/sol-final/test-results',
  use: { baseURL: 'http://127.0.0.1:5176', viewport: { width: 1440, height: 900 }, locale: 'it-IT', timezoneId: 'Europe/Rome', trace: 'retain-on-failure' },
  webServer: { command: 'npm --prefix . run dev -- --host 127.0.0.1 --port 5176 --strictPort', url: 'http://127.0.0.1:5176', reuseExistingServer: true, timeout: 30000 },
});
