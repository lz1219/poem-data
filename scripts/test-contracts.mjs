import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const target = path.join(ROOT, '../jiangshan-xingzhi');
const sources = {};
for (const dir of ['works', 'persons', 'journeys']) {
  sources[dir] = fs.readdirSync(path.join(ROOT, 'data', dir)).filter(f => f.endsWith('.json')).map(f => JSON.parse(fs.readFileSync(path.join(ROOT, 'data', dir, f))));
}
// 真实校验器在内存中接收故障数据；不改仓库文件。
const mutate = `import fs from 'node:fs'; const old=fs.readFileSync; let work=false,journey=false;
fs.readFileSync=function(p,...args){const raw=old.call(this,p,...args);const name=String(p).replaceAll('\\\\','/');
if(name.includes('/data/works/')&&name.endsWith('.json')&&(!work||work===name)){work=name;const w=JSON.parse(raw);delete w.citation;w.text.paragraphsSimplified=[];return JSON.stringify(w)}
if(name.includes('/data/journeys/')&&name.endsWith('.json')&&(!journey||journey===name)){journey=name;const j=JSON.parse(raw);delete j.intro.source;j.stops[0].place.coord=[181,91];return JSON.stringify(j)}return raw};await import('./scripts/validate.mjs');`;
const r = spawnSync(process.execPath, ['--input-type=module', '-e', mutate], { cwd: ROOT, encoding: 'utf8' });
assert.notEqual(r.status, 0, '故障数据必须被拦截');
assert.match(r.stdout + r.stderr, /citation/);assert.match(r.stdout + r.stderr, /坐标/);assert.match(r.stdout + r.stderr, /繁简/);
const ctx = {window: {}};vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(target, 'js/lore_data.js'), 'utf8'), ctx);
const baseline = JSON.parse(JSON.stringify(ctx.window.ATLAS_LORE_DATA));
vm.runInContext(fs.readFileSync(path.join(target, 'js/atlas_overlay.js'), 'utf8'), ctx);
vm.runInContext(fs.readFileSync(path.join(target, 'js/atlas_journeys.js'), 'utf8'), ctx);
const data = ctx.window.ATLAS_LORE_DATA;
for (const original of baseline.PERSON_PROFILES) {
  const current = data.PERSON_PROFILES.find(p => p.key === original.key);
  for (const alias of original.aliases || []) assert.ok(current.aliases.includes(alias), '不得丢失旧别名 ' + alias);
  if (original.courtesyEn) assert.ok(current.courtesyEn);
}
for (const j of sources.journeys) {
  const out = data.HISTORICAL_JOURNEYS.find(x => x.key === j.key);
  for (const s of j.stops) {
    if (s.year === null) {
      assert.ok(ctx.window.ATLAS_JOURNEYS[j.key].undatedStops.some(x => x.seq === s.seq));
      assert.ok(!out.stops.some(x => x.year === null));continue;
    }
    const match = out.stops.find(x => x.year === s.year && x.ancientZh === s.place.ancient);
    assert.equal(match?.descZh, s.descZh, '既有站点修订必须生效');
    assert.equal(match?.source, s.source);
  }
}
console.log('数据故障拦截、站点修订、别名保存、未知年份隔离：通过。');
