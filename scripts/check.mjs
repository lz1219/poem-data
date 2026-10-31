#!/usr/bin/env node
/**
 * 提交闸门：数据 + 索引 + 数据库往返，三道一起过。
 *
 * 单独跑：node scripts/check.mjs
 * 装钩子：node scripts/install-hooks.mjs
 *
 * 任何一道失败 → 退出码 1 → pre-commit 拦下本次提交。
 */
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url)) + '/..';
const isWin = process.platform === 'win32';

const steps = [];
const run = (name, cmd, args, opts = {}) => {
  const r = spawnSync(cmd, args, { cwd: opts.cwd || ROOT, encoding: 'utf8', shell: isWin });
  const ok = r.status === 0;
  steps.push({ name, ok, out: ((r.stdout || '') + (r.stderr || '')).trim() });
  return ok;
};

// ① 数据契约
run('data', 'node', ['scripts/validate.mjs']);

// ② 索引同步
run('index', 'node', ['scripts/build-index.mjs', '--check']);

// ④ 站点生成物是否与数据一致（兄弟仓库存在时才跑）
const atlasDir = path.join(ROOT, '..', 'jiangshan-xingzhi');
if (existsSync(atlasDir)) {
  run('atlas', 'node', ['scripts/emit-atlas.mjs', '--target', atlasDir, '--check']);
} else {
  steps.push({ name: 'atlas', ok: true, skipped: true, out: '未找到 ../jiangshan-xingzhi，跳过生成物检查' });
}

// ③ 数据库往返（有 venv 才跑；没有则跳过）
const py = isWin
  ? path.join(ROOT, 'server/.venv/Scripts/python.exe')
  : path.join(ROOT, 'server/.venv/bin/python');
const django = path.join(ROOT, 'server');
if (existsSync(py) && existsSync(path.join(django, 'db.sqlite3'))) {
  run('db', py, ['manage.py', 'export_json', '--check'], {
    cwd: django,
    env: {
      ...process.env,
      DATA_DIR: path.join(ROOT, 'data'),
      PUBLIC_DIR: ROOT,
      DJANGO_DEBUG: '0',
    },
  });
} else {
  steps.push({ name: 'db', ok: true, skipped: true, out: '未装 server 环境，跳过往返检查' });
}

// ── 汇总 ──
let failed = 0;
for (const s of steps) {
  const mark = s.skipped ? '–' : s.ok ? '✓' : '✕';
  console.log(`${mark} ${s.name.padEnd(6)} ${s.ok ? '' : s.out.split('\n').slice(-4).join('\n         ')}`);
  if (!s.ok) failed++;
}
if (failed) {
  console.error(`\n${failed} 项未通过，提交已拦下。`);
  process.exit(1);
}
console.log('\n全部通过。');
