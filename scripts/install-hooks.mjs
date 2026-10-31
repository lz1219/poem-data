#!/usr/bin/env node
/**
 * 安装 git 钩子：pre-commit 跑 scripts/check.mjs。
 * 换机器、重新克隆后跑一次即可。卸载：node scripts/install-hooks.mjs --remove
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url)) + '/..';
const HOOK = path.join(ROOT, '.git/hooks/pre-commit');

if (!fs.existsSync(path.join(ROOT, '.git'))) {
  console.error('当前目录不是 git 仓库');
  process.exit(1);
}

if (process.argv.includes('--remove')) {
  if (fs.existsSync(HOOK)) fs.unlinkSync(HOOK);
  console.log('已移除 pre-commit 钩子');
  process.exit(0);
}

fs.mkdirSync(path.dirname(HOOK), { recursive: true });
fs.writeFileSync(
  HOOK,
  `#!/bin/sh
# 由 scripts/install-hooks.mjs 生成，勿手改
node scripts/check.mjs || {
  echo ""
  echo "提交被拦下：数据/索引/数据库往返有一项没通过。"
  echo "确需跳过：git commit --no-verify"
  exit 1
}
`,
  { mode: 0o755 }
);
fs.chmodSync(HOOK, 0o755);
console.log('已安装 pre-commit → scripts/check.mjs');
