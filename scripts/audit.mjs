#!/usr/bin/env node
/** 数据体检：找出"缺什么"，而不是"有什么"。 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url)) + '/..';
const list = (d) => fs.readdirSync(path.join(ROOT, d)).filter((f) => f.endsWith('.json')).map((f) => JSON.parse(fs.readFileSync(path.join(ROOT, d, f), 'utf8')));

const works = list('data/works');
const persons = list('data/persons');
const journeys = list('data/journeys');

const pct = (n, d) => (d ? Math.round((n / d) * 100) : 0) + '%';
const row = (label, n, total, note = '') => console.log(`  ${label.padEnd(22)} ${String(n).padStart(4)} / ${String(total).padEnd(4)} ${pct(n, total).padStart(5)}  ${note}`);

console.log('\n《作品》' + ` 共 ${works.length} 条`);
row('正文（≥1 句）', works.filter((w) => (w.text?.paragraphs || []).length > 0).length, works.length);
row('繁简双份', works.filter((w) => (w.text?.paragraphsSimplified || []).length).length, works.length);
row('繁体取自底本', works.filter((w) => w.text?.traditionalDerived === false).length, works.length, '其余为反推');
row('大意', works.filter((w) => w.meaning).length, works.length);
row('注释', works.filter((w) => (w.notes || []).length).length, works.length);
row('写作背景', works.filter((w) => w.background).length, works.length);
row('赏析', works.filter((w) => w.appreciation?.text).length, works.length);
row('推测带依据', works.filter((w) => w.appreciation?.inference?.basis).length, works.length);
row('系年依据', works.filter((w) => (w.dating || []).length).length, works.length);
row('校记', works.filter((w) => (w.apparatus || []).length).length, works.length, `共 ${works.reduce((n, w) => n + (w.apparatus || []).length, 0)} 条`);
row('评点', works.filter((w) => w.commentaryFile).length, works.length, '0 条（未找到可核原文）');
row('学术级', works.filter((w) => w.level === 'academic').length, works.length);

console.log('\n《人物》' + ` 共 ${persons.length} 位`);
row('生卒齐全', persons.filter((p) => p.span?.[0] && p.span?.[1]).length, persons.length);
row('CBDB 映射', persons.filter((p) => p.externalIds?.cbdb).length, persons.length);
row('有行迹', persons.filter((p) => p.journeyKey).length, persons.length);
row('别名', persons.filter((p) => (p.aliases || []).length > 1).length, persons.length);

console.log('\n《行迹》' + ` 共 ${journeys.length} 条`);
const stops = journeys.flatMap((j) => j.stops || []);
const links = journeys.flatMap((j) => Object.values(j.links || {}));
row('站点（总）', stops.length, stops.length);
row('站点有出处', stops.filter((s) => s.source).length, stops.length);
row('站点有坐标', stops.filter((s) => s.place?.coord).length, stops.length);
row('站点有引文', stops.filter((s) => s.quote).length, stops.length);
row('站点有今地名', stops.filter((s) => s.place?.modern).length, stops.length);
row('承接语有出处', links.filter((l) => l.source).length, links.length);
row('导语', journeys.filter((j) => j.intro).length, journeys.length);

console.log('\n《缺口清单》');
const noAuthor = works.filter((w) => w.authorKey === 'anonymous' || !w.authorKey).length;
if (noAuthor) console.log(`  · ${noAuthor} 条作品作者为「佚名」`);
const derived = works.filter((w) => w.text?.traditionalDerived).length;
if (derived) console.log(`  · ${derived} 条繁体是反推的（底本不可得），引用时须注明`);
const noCbdb = persons.filter((p) => !p.externalIds?.cbdb && p.key !== 'anonymous');
if (noCbdb.length) console.log(`  · ${noCbdb.length} 位人物未映射 CBDB：${noCbdb.map((p) => p.zh).join('、')}`);
const noCoord = stops.filter((s) => !s.place?.coord).length;
if (noCoord) console.log(`  · ${noCoord} 个站点缺坐标`);
const single = works.filter((w) => (w.text?.paragraphs || []).length <= 2).length;
if (single) console.log(`  · ${single} 条作品仅 1–2 句（可能是摘录而非全篇）`);
