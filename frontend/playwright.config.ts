import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests', timeout: 90000, workers: 1,
  reporter: 'list', outputDir: '../artifacts/browser-tests',
  use: { baseURL: 'http://localhost:5174', viewport: { width: 1440, height: 1000 },
    launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] } },
  webServer: [
    { command: '../.venv/bin/uvicorn app.main:app --app-dir ../backend --port 8001',
      url: 'http://localhost:8001/health', env: { GENESIS_DB: '../artifacts/browser-world.sqlite' }, reuseExistingServer: false },
    { command: 'npm run dev -- --port 5174', url: 'http://localhost:5174',
      env: { BACKEND_URL: 'http://127.0.0.1:8001' }, reuseExistingServer: false },
  ],
})
