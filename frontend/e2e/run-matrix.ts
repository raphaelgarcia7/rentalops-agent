import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import config from '../playwright.config.ts';

// Each viewport gets a fresh managed harness and disposable schema. Sharing one
// loopback peer across the whole growing matrix legitimately exhausts the real
// password-setting budget. Never clear counters or weaken production limits.
const require = createRequire(import.meta.url);
const projects = config.projects?.map((project) => project.name);
if (!projects?.length || projects.some((name) => !name)) {
  throw new Error('Every browser matrix project must have an explicit name');
}
let failed = false;
for (const name of projects) {
  const result = spawnSync(
    process.execPath,
    [
      require.resolve('@playwright/test/cli'),
      'test',
      `--project=${name}`,
      '--workers=1',
      `--output=test-results/runs/${name}`,
    ],
    {
      stdio: 'inherit',
      env: {
        ...process.env,
        PLAYWRIGHT_HTML_OUTPUT_DIR: `playwright-report/${name}`,
      },
    },
  );
  if (result.error) throw result.error;
  failed ||= result.status !== 0;
}
process.exitCode = failed ? 1 : 0;
