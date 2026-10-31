#!/usr/bin/env node
/**
 * poem-data 校验器（零依赖）
 *
 * 校验的是「学术级数据能不能被信任」，所以重点不在字段齐备，
 * 而在：出处在不在、反推有没有标、评点核没核、系年是否唯一。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url)) + '/..';
const errors = [];
const warns = [];

const readJSON = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8'));
const listDir = (p) => (fs.existsSync(path.join(ROOT, p)) ? fs.readdirSync(path.join(ROOT, p)).filter((f) => f.endsWith('.json')) : []);
const err = (m) => errors.push(m);
const warn = (m) => warns.push(m);

// ── 1. 作品 ──
const workFiles = listDir('data/works');
const works = new Map();
for (const f of workFiles) {
  const w = readJSON(path.join('data/works', f));
  const at = `works/${f}`;

  if (w.schemaVersion !== '1.0') err(`${at}: schemaVersion 非 1.0`);
  if (works.has(w.key)) err(`${at}: key 重复 ${w.key}`);
  works.set(w.key, w);

  if (!w.titleZh) err(`${at}: 缺 titleZh`);
  if (!['shi', 'ci', 'fu', 'wen', 'history', 'qu'].includes(w.genre)) err(`${at}: genre 非法 ${w.genre}`);
  if (!['academic', 'popular'].includes(w.level)) err(`${at}: level 非法 ${w.level}`);
  if (!['confirmed', 'probable', 'disputed', 'unknown'].includes(w.certainty)) err(`${at}: certainty 非法`);

  // 文本：繁简必须一一对应
  const p = w.text?.paragraphs || [];
  const ps = w.text?.paragraphsSimplified || [];
  if (!p.length) err(`${at}: 正文为空`);
  if (ps.length && ps.length !== p.length) err(`${at}: 繁简段数不一致（${p.length} vs ${ps.length}）`);
  if (w.text?.traditionalDerived && !w.text?.simplifiedBy) err(`${at}: 繁体为反推但未标 simplifiedBy`);

  // 赏析：必须自撰 + 许可；推测必须有据
  if (!w.appreciation?.text) err(`${at}: 缺赏析`);
  if (w.appreciation?.by !== '本站自撰') err(`${at}: 赏析 by 必须是「本站自撰」`);
  if (w.appreciation?.license !== 'CC BY-SA 4.0') err(`${at}: 赏析 license 必须是 CC BY-SA 4.0`);
  if (w.appreciation?.inference && !w.appreciation.inference.basis) err(`${at}: 推测缺 basis`);

  // 校记：每条必须有依据
  for (const a of w.apparatus || []) {
    if (!a.basis || a.basis.length < 4) err(`${at}: 校记 ${a.id} 缺依据`);
    if (!['pending', 'base-right', 'var-right', 'both'].includes(a.judgement)) err(`${at}: 校记 ${a.id} judgement 非法`);
    if (a.locator && a.locator.paragraph != null && (a.locator.paragraph < 1 || a.locator.paragraph > p.length)) {
      err(`${at}: 校记 ${a.id} 定位段号越界`);
    }
  }

  // 评点文件
  if (w.commentaryFile) {
    const cp = path.join('data', w.commentaryFile);
    if (!fs.existsSync(path.join(ROOT, cp))) err(`${at}: commentaryFile 不存在 ${w.commentaryFile}`);
    else {
      const cd = readJSON(cp);
      if (cd.workKey !== w.key) err(`${at}: 评点文件 workKey 不匹配`);
      for (const item of cd.items || []) {
        if (!item.critic || !item.source) err(`${at}: 评点 ${item.id} 缺评者或出处`);
        if (item.status !== 'verified') warn(`${at}: 评点 ${item.id} 未核原文（status=${item.status}）`);
      }
    }
  }

  // 系年：adopted 至多一条，且与 composed.year 一致
  const adopted = (w.dating || []).filter((d) => d.stance === 'adopted');
  if (adopted.length > 1) err(`${at}: 系年 adopted 多于一条`);
  if (adopted.length === 1 && w.composed?.year != null && String(w.composed.year) !== adopted[0].claim) {
    err(`${at}: 采信系年 ${adopted[0].claim} 与 composed.year ${w.composed.year} 不一致`);
  }
  if (w.composed?.year != null && !(w.dating || []).length) warn(`${at}: 有作年但无系年依据`);
}

// ── 2. 人物 ──
const personFiles = listDir('data/persons');
const persons = new Set();
for (const f of personFiles) {
  const p = readJSON(path.join('data/persons', f));
  const at = `persons/${f}`;
  if (!p.key || !p.zh) err(`${at}: 缺 key 或 zh`);
  if (persons.has(p.key)) err(`${at}: key 重复`);
  persons.add(p.key);
  if (p.span && p.span.length !== 2) err(`${at}: span 必须是两元组`);
}

// 作品的 authorKey 必须存在
for (const [k, w] of works) {
  if (!persons.has(w.authorKey)) warn(`works/${k}: authorKey ${w.authorKey} 没有对应人物文件`);
}

// ── 3. 行迹 ──
for (const f of listDir('data/journeys')) {
  const j = readJSON(path.join('data/journeys', f));
  const at = `journeys/${f}`;
  if (!persons.has(j.personKey)) err(`${at}: personKey ${j.personKey} 不存在`);
  if (!(j.stops || []).length) err(`${at}: 无站点`);
  (j.stops || []).forEach((s, i) => {
    if (s.seq !== i + 1) err(`${at}: 站序不连续（第 ${i + 1} 个 seq=${s.seq}）`);
    if (!s.source) err(`${at}: 第 ${i + 1} 站缺出处`);
    if (!s.descZh) err(`${at}: 第 ${i + 1} 站缺叙述`);
  });
  for (const [k, v] of Object.entries(j.links || {})) {
    const n = Number(k);
    if (!(n >= 1 && n <= (j.stops || []).length)) err(`${at}: 承接语站号 ${k} 越界`);
    if (!v.source) err(`${at}: 承接语 ${k} 缺出处`);
  }
}

// ── 4. 共享文件 ──
for (const [k, e] of Object.entries(readJSON('shared/editions.json'))) {
  if (!e.name) err(`shared/editions.json: ${k} 缺 name`);
}

// ── 汇总 ──
console.log('\n《poem-data》校验');
console.table({
  作品: works.size,
  人物: persons.size,
  行迹: listDir('data/journeys').length,
  评点文件: listDir('data/comments').length,
  繁体来自底本: [...works.values()].filter((w) => w.text?.traditionalDerived === false).length,
  繁体为反推: [...works.values()].filter((w) => w.text?.traditionalDerived === true).length,
});

if (warns.length) {
  console.log(`\n提示 ${warns.length} 条：`);
  warns.slice(0, 8).forEach((w) => console.log('  · ' + w));
  if (warns.length > 8) console.log(`  … 其余 ${warns.length - 8} 条`);
}
if (errors.length) {
  console.error(`\n错误 ${errors.length} 条：`);
  errors.slice(0, 20).forEach((e) => console.error('  ✕ ' + e));
  if (errors.length > 20) console.error(`  … 其余 ${errors.length - 20} 条`);
  process.exit(1);
}
console.log('\n✓ 数据校验通过\n');
