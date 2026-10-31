#!/usr/bin/env node
/**
 * 生成器：poem-data（唯一真相） → 江山行止（站点）
 *
 * 产出三个文件（均为生成物，勿手改）：
 *   js/atlas_works.js      作品（69 条）
 *   js/atlas_overlay.js    人物档案 + 行迹（含「只补缺站」的差量逻辑）
 *   js/atlas_journeys.js   行迹读本（导语 + 站间承接语）
 *
 * 用法：
 *   node scripts/emit-atlas.mjs --target ../jiangshan-xingzhi
 *   node scripts/emit-atlas.mjs --target ../jiangshan-xingzhi --check   # 只比对
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url)) + '/..';
const args = process.argv.slice(2);
const arg = (name, def) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : def;
};
const TARGET = path.resolve(ROOT, arg('--target', '../jiangshan-xingzhi'));
const CHECK = args.includes('--check');

const readJSON = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const list = (dir) => (fs.existsSync(path.join(ROOT, dir)) ? fs.readdirSync(path.join(ROOT, dir)).filter((f) => f.endsWith('.json')).sort() : []);

/* ── 读取 poem-data ── */
const works = list('data/works').map((f) => readJSON(path.join(ROOT, 'data/works', f)));
const persons = list('data/persons').map((f) => readJSON(path.join(ROOT, 'data/persons', f)));
const journeys = list('data/journeys').map((f) => readJSON(path.join(ROOT, 'data/journeys', f)));
const personByKey = new Map(persons.map((p) => [p.key, p]));

/* ── 读取江山行止的上游数据（用于差量） ── */
global.window = {};
const lorePath = path.join(TARGET, 'js/lore_data.js');
if (!fs.existsSync(lorePath)) {
  console.error('找不到上游数据：' + lorePath);
  process.exit(1);
}
await import('file://' + lorePath.replace(/\\/g, '/'));
const LORE = global.window.ATLAS_LORE_DATA || {};
const upJourneys = new Map((LORE.HISTORICAL_JOURNEYS || []).map((j) => [j.key, j]));
const upPersons = new Map((LORE.PERSON_PROFILES || []).map((p) => [p.key, p]));

/* ══════════ 1. 作品 ══════════ */
const worksOut = {};
for (const w of works) {
  const author = personByKey.get(w.authorKey) || { zh: '', en: '' };
  worksOut[w.key] = {
    alias: w.aliases && w.aliases.length ? w.aliases : [w.titleZh],
    titleZh: w.titleZh,
    titleEn: w.titleEn || '',
    authorZh: author.zh || '佚名',
    authorEn: author.en || '',
    year: w.composed?.year ?? null,
    placeZh: w.composed?.placeZh || '',
    placeEn: '',
    genre: w.genre,
    certainty: w.certainty,
    // 站点显示简体；繁体仍留在 poem-data
    text: w.text?.paragraphsSimplified?.length ? w.text.paragraphsSimplified : w.text?.paragraphs || [],
    meaning: w.meaning || '',
    notes: (w.notes || []).map((n) => ({ term: n.term, explain: n.explain })),
    background: w.background || '',
    appreciation: {
      text: w.appreciation?.text || '',
      inference: w.appreciation?.inference || null,
      by: w.appreciation?.by || '本站自撰',
      license: w.appreciation?.license || 'CC BY-SA 4.0',
    },
    source: w.citation || '',
    // 以下为站点可选使用的考据字段
    level: w.level,
    apparatus: w.apparatus || [],
    dating: w.dating || [],
  };
}

/* ══════════ 2. 人物 + 行迹（差量） ══════════ */
const personOut = [];
const journeyOut = [];
const extraStops = []; // 上游已有、我们只补缺站的情况

for (const j of journeys) {
  const p = personByKey.get(j.personKey) || {};
  const upJ = upJourneys.get(j.key);

  if (!upJ) {
    // 上游没有 → 整条新建
    journeyOut.push({
      key: j.key,
      dynastyKey: p.dynastyKey || '',
      color: '#7a5c3e',
      shortZh: j.titleZh,
      shortEn: '',
      titleZh: j.titleZh,
      titleEn: j.titleEn || '',
      spanZh: j.spanZh || '',
      spanEn: '',
      stops: (j.stops || []).map((s) => ({
        year: s.year,
        eraZh: s.eraZh || '',
        coord: s.place?.coord || null,
        labelPos: 'top',
        ancientZh: s.place?.ancient || '',
        modernZh: s.place?.modern || '',
        ancientEn: '',
        modernEn: '',
        titleZh: s.titleZh,
        titleEn: '',
        descZh: s.descZh,
        descEn: '',
        quoteZh: s.quote || '',
        quoteEn: '',
        persons: [j.personKey],
        source: s.source,
      })),
    });
  } else {
    // 上游已有 → 只补上游没有的站（按「年 + 古地名」判定）
    const seen = new Set((upJ.stops || []).map((s) => s.year + '|' + s.ancientZh));
    const add = (j.stops || [])
      .filter((s) => !seen.has(s.year + '|' + (s.place?.ancient || '')))
      .map((s) => ({
        year: s.year,
        eraZh: s.eraZh || '',
        coord: s.place?.coord || null,
        labelPos: 'top',
        ancientZh: s.place?.ancient || '',
        modernZh: s.place?.modern || '',
        ancientEn: '',
        modernEn: '',
        titleZh: s.titleZh,
        titleEn: '',
        descZh: s.descZh,
        descEn: '',
        quoteZh: s.quote || '',
        quoteEn: '',
        persons: [j.personKey],
        source: s.source,
      }));
    if (add.length) extraStops.push({ key: j.key, stops: add });
  }
}

// 人物档案：上游没有的新建；已有的补 journeyKey
for (const j of journeys) {
  const p = personByKey.get(j.personKey);
  if (!p) continue;
  const up = upPersons.get(p.key);
  const rec = {
    key: p.key,
    zh: p.zh,
    en: p.en || '',
    courtesyZh: p.courtesyZh || '',
    courtesyEn: '',
    dynastyKey: p.dynastyKey || '',
    span: [p.span?.[0] ?? null, p.span?.[1] ?? null],
    journeyKey: j.key,
    aliases: p.aliases || [],
    tokens: [p.zh, ...(p.aliases || [])].filter(Boolean),
  };
  if (!up) personOut.push(rec);
  else personOut.push({ ...rec, __mergeInto: p.key });
}

/* ══════════ 3. 行迹读本（导语 + 承接语） ══════════ */
const readOut = {};
for (const j of journeys) {
  if (!j.intro && !(j.links && Object.keys(j.links).length)) continue;
  readOut[j.key] = {
    intro: j.intro ? { text: j.intro.text, source: j.intro.source } : undefined,
    links: j.links || {},
  };
}

/* ══════════ 输出 ══════════ */
const HEADER = (name, extra = '') =>
  `/**\n * ${name}\n * ⚠ 本文件由 poem-data/scripts/emit-atlas.mjs 生成，请勿手动编辑。\n *   内容源头：poem-data/data/*.json\n${extra} */\n\n`;

const files = {};

files['js/atlas_works.js'] =
  HEADER('作品数据（生成物）', ` * 共 ${Object.keys(worksOut).length} 条`) +
  `window.ATLAS_WORKS = ${JSON.stringify(worksOut, null, 2)};\n`;

const personLines = personOut
  .map((p) => {
    const { __mergeInto, ...rest } = p;
    return __mergeInto
      ? `  mergePerson(${JSON.stringify(rest, null, 2).replace(/\n/g, '\n  ')});`
      : `  pushPerson(${JSON.stringify(rest, null, 2).replace(/\n/g, '\n  ')});`;
  })
  .join('\n\n');

const journeyLines = journeyOut
  .map((j) => `  pushJourney(${JSON.stringify(j, null, 2).replace(/\n/g, '\n  ')});`)
  .join('\n\n');

const extraLines = extraStops
  .map((e) => `  addStops(${JSON.stringify(e.key)}, ${JSON.stringify(e.stops, null, 2).replace(/\n/g, '\n  ')});`)
  .join('\n\n');

files['js/atlas_overlay.js'] =
  HEADER('人物与行迹（生成物）', ` * 人物 ${personOut.length} 位；新建行迹 ${journeyOut.length} 条；补站 ${extraStops.length} 组`) +
  `(function () {
  'use strict';
  var D = window.ATLAS_LORE_DATA;
  if (!D) return;
  if (!D.PERSON_PROFILES) D.PERSON_PROFILES = [];
  if (!D.HISTORICAL_JOURNEYS) D.HISTORICAL_JOURNEYS = [];

  // 上游已有同名人物时合并，而不是跳过——否则 journeyKey 挂不上，行迹不显示
  function mergePerson(p) {
    var idx = D.PERSON_PROFILES.findIndex(function (x) { return x.key === p.key; });
    if (idx >= 0) {
      var cur = D.PERSON_PROFILES[idx];
      for (var k in p) { if (p[k] !== undefined) cur[k] = p[k]; }
    } else {
      D.PERSON_PROFILES.push(p);
    }
  }

  function pushPerson(p) {
    if (!D.PERSON_PROFILES.some(function (x) { return x.key === p.key; })) D.PERSON_PROFILES.push(p);
  }

  function pushJourney(j) {
    var i = D.HISTORICAL_JOURNEYS.findIndex(function (x) { return x.key === j.key; });
    if (i >= 0) D.HISTORICAL_JOURNEYS[i] = j;
    else D.HISTORICAL_JOURNEYS.push(j);
  }

  // 上游已有该行迹：只补它缺的站，不覆盖上游
  function addStops(key, stops) {
    var j = D.HISTORICAL_JOURNEYS.find(function (x) { return x.key === key; });
    if (!j) return;
    var seen = {};
    (j.stops || []).forEach(function (s) { seen[s.year + '|' + s.ancientZh] = 1; });
    var merged = (j.stops || []).slice();
    stops.forEach(function (s) {
      if (!seen[s.year + '|' + s.ancientZh]) { merged.push(s); seen[s.year + '|' + s.ancientZh] = 1; }
    });
    merged.sort(function (a, b) { return (a.year || 0) - (b.year || 0); });
    j.stops = merged;
  }

${personLines}

${journeyLines}

${extraLines}
})();
`;

files['js/atlas_journeys.js'] =
  HEADER('行迹读本（生成物）', ` * 导语 ${Object.keys(readOut).length} 条`) +
  `window.ATLAS_JOURNEYS = ${JSON.stringify(readOut, null, 2)};\n`;

let changed = 0;
let same = 0;
const diffs = [];
for (const [rel, content] of Object.entries(files)) {
  const abs = path.join(TARGET, rel);
  const old = fs.existsSync(abs) ? fs.readFileSync(abs, 'utf8').replace(/\r\n/g, '\n') : '';
  if (old === content) {
    same++;
    continue;
  }
  changed++;
  diffs.push(rel);
  if (!CHECK) {
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, content);
  }
}

if (CHECK) {
  if (changed) {
    console.log('以下文件与生成结果不同：');
    diffs.forEach((d) => console.log('  · ' + d));
    process.exit(1);
  }
  console.log('全部一致（' + same + ' 个文件）');
} else {
  console.log(
    `生成完成：作品 ${Object.keys(worksOut).length} / 人物 ${personOut.length} / ` +
      `新建行迹 ${journeyOut.length} / 补站 ${extraStops.length} 组 / 读本 ${Object.keys(readOut).length}`
  );
  console.log(`写入 ${changed} 个文件，${same} 个未变 → ${TARGET}`);
}
