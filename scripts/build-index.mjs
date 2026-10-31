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
  journeys: journeys.map((j) => ({ key: j.key, titleZh: j.titleZh, stops: (j.stops || []).length, file: `data/journeys/${j.key}.json` })),
};

fs.writeFileSync(path.join(ROOT, 'data/index.json'), JSON.stringify(idx, null, 2) + '\n');
console.log(JSON.stringify({ works: idx.works.length, persons: idx.persons.length, journeys: idx.journeys.length }));
