#!/usr/bin/env node
/**
 * 生成 data/index.json：列出所有作品/人物/行迹/评点，供查看器加载。
 * 浏览器无法列目录，所以需要一份索引。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url)) + '/..';
const list = (p) => (fs.existsSync(path.join(ROOT, p)) ? fs.readdirSync(path.join(ROOT, p)).filter((f) => f.endsWith('.json')).sort() : []);

const works = list('data/works').map((f) => JSON.parse(fs.readFileSync(path.join(ROOT, 'data/works', f), 'utf8')));
const persons = list('data/persons').map((f) => JSON.parse(fs.readFileSync(path.join(ROOT, 'data/persons', f), 'utf8')));
const journeys = list('data/journeys').map((f) => JSON.parse(fs.readFileSync(path.join(ROOT, 'data/journeys', f), 'utf8')));

const idx = {
  generatedAt: new Date().toISOString(),
  works: works.map((w) => ({
    key: w.key,
    titleZh: w.titleZh,
    authorKey: w.authorKey,
    genre: w.genre,
    level: w.level,
    year: w.composed?.year ?? null,
    traditionalDerived: !!w.text?.traditionalDerived,
    apparatus: (w.apparatus || []).length,
    hasComments: !!w.commentaryFile,
    file: `data/works/${w.key}.json`,
  })),
  persons: persons.map((p) => ({ key: p.key, zh: p.zh, span: p.span, hasJourney: !!p.journeyKey, file: `data/persons/${p.key}.json` })),
  journeys: journeys.map((j) => ({ key: j.key, titleZh: j.titleZh, stops: (j.stops || []).length, origin: j.origin, file: `data/journeys/${j.key}.json` })),
};

const OUT = path.join(ROOT, 'data/index.json');
const text = JSON.stringify(idx, null, 2) + '\n';

// --check：只比对不写，供提交闸门使用（忽略 generatedAt）
if (process.argv.includes('--check')) {
  const norm = (s) => {
    const d = JSON.parse(s);
    delete d.generatedAt;
    return JSON.stringify(d);
  };
  const old = fs.existsSync(OUT) ? fs.readFileSync(OUT, 'utf8') : '';
  if (norm(old) !== norm(text)) {
    console.error('index.json 与 data/ 不同步，请运行：node scripts/build-index.mjs');
    process.exit(1);
  }
  console.log('index.json 已同步');
  process.exit(0);
}

fs.writeFileSync(OUT, text);
console.log(JSON.stringify({ works: idx.works.length, persons: idx.persons.length, journeys: idx.journeys.length }));
