#!/usr/bin/env node
/**
 * 构建 GitHub Pages 用的静态版。
 *
 * 静态版只含策展内容（作品 / 人物 / 行迹）；语料库功能（作者 / 典籍 / 仕历 / 全文检索）
 * 依赖服务器上的数据库，在静态版里隐藏，并给出完整版入口。
 *
 * 用法：node scripts/build-static.mjs [--full-site URL]
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url)) + '/..';
const OUT = path.join(ROOT, 'dist');
const args = process.argv.slice(2);
const fullSite = args.includes('--full-site')
  ? args[args.indexOf('--full-site') + 1]
  : 'http://47.94.110.181:8081/';

const rmrf = (p) => fs.rmSync(p, { recursive: true, force: true });
const copy = (from, to) => {
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.copyFileSync(from, to);
};

rmrf(OUT);
fs.mkdirSync(OUT, { recursive: true });

/* 1. 前端：注入静态标记 */
let html = fs.readFileSync(path.join(ROOT, 'web/index.html'), 'utf8');
const flag =
  `<script>window.STATIC_ONLY = true; window.FULL_SITE = ${JSON.stringify(fullSite)};</script>\n`;
// 插在第一个 <script> 之前（即主逻辑之前）
const i = html.indexOf('<script>');
if (i < 0) {
  console.error('✗ 未找到脚本入口');
  process.exit(1);
}
html = html.slice(0, i) + flag + html.slice(i);
fs.writeFileSync(path.join(OUT, 'index.html'), html);

/* 2. 数据：只带策展内容 */
const files = [];
const walk = (dir) => {
  for (const e of fs.readdirSync(path.join(ROOT, dir), { withFileTypes: true })) {
    const rel = path.posix.join(dir, e.name);
    if (e.isDirectory()) walk(rel);
    else files.push(rel);
  }
};
walk('data');

for (const rel of files) {
  // 静态版不需要 schema / comments（评点当前为空，有则一并带上）
  copy(path.join(ROOT, rel), path.join(OUT, rel));
}

/* 3. 杂项 */
fs.writeFileSync(path.join(OUT, '.nojekyll'), '');
fs.writeFileSync(
  path.join(OUT, 'robots.txt'),
  'User-agent: *\nAllow: /\n' + (fullSite ? `\n# 完整版（含语料库）：${fullSite}\n` : '')
);

const size = (p) => fs.statSync(p).size;
let total = 0;
const count = (d) =>
  fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
    const f = path.join(d, e.name);
    if (e.isDirectory()) count(f);
    else total += size(f);
  });
count(OUT);

console.log(`静态版已生成 → ${OUT}`);
console.log(`  文件 ${files.length + 3} 个，共 ${(total / 1024).toFixed(0)} KB`);
console.log(`  完整版入口：${fullSite || '（未设置）'}`);
