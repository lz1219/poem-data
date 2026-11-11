import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, copyFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const root = resolve(import.meta.dirname, '..');
const lore = resolve(root, '../jiangshan-xingzhi/js/lore_data.js');

test('指定数据目录生成与默认输入一致，并拒绝缺失目录', (t) => {
  const target = mkdtempSync(join(tmpdir(), 'atlas-input-test-'));
  t.after(() => rmSync(target, { recursive: true, force: true }));
  mkdirSync(join(target, 'js'));
  copyFileSync(lore, join(target, 'js/lore_data.js'));
  const run = (...args) => spawnSync(process.execPath, [join(root, 'scripts/emit-atlas.mjs'), '--target', target, ...args], { cwd: root, encoding: 'utf8' });
  assert.equal(run().status, 0);
  const compare = run('--data-dir', join(root, 'data'), '--check');
  assert.equal(compare.status, 0, compare.stderr);
  assert.notEqual(run('--data-dir', join(target, 'missing')).status, 0);
});
