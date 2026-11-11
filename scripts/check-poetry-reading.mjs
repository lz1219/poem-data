import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const read = path => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const pilot = read('../data/poetry-reading/pilot-20261105.json');
const fail = message => { throw new Error(message); };
if (pilot.schemaVersion !== 1 || pilot.generation?.reviewStatus !== 'unreviewed' ||
    pilot.generation?.label !== 'AI生成·未经人工审校' || !pilot.generation?.model ||
    !pilot.generation?.generatedAt || !pilot.generation?.promptVersion) fail('生成记录缺失');
for (const [key, entry] of Object.entries(pilot.works)) {
  const work = read(`../data/works/${key}.json`);
  if (entry.sourceEdition !== work.text.sourceEdition ||
      JSON.stringify(entry.sourceOriginal) !== JSON.stringify(work.text.paragraphs) ||
      JSON.stringify(entry.sourceParagraphs) !== JSON.stringify(work.text.paragraphsSimplified)) fail(`${key}: 正文或版本失配`);
  const hash = createHash('sha256').update(entry.sourceParagraphs.join('\n')).digest('hex');
  if (hash !== entry.sourceSha256 || entry.segments.length !== entry.sourceParagraphs.length) fail(`${key}: 哈希或段数失配`);
  if (entry.segments.some((segment, i) => segment.source !== entry.sourceParagraphs[i] || !segment.translation?.trim())) fail(`${key}: 译文或原文缺失`);
  if (!entry.appreciation?.trim() || !entry.sourceStatus?.trim() || entry.notes.some(n => !n.explanation?.trim() || !entry.sourceParagraphs.some(p => p.includes(n.term)))) fail(`${key}: 赏析、来源说明或注释无效`);
}
console.log(`诗词阅读样板：${Object.keys(pilot.works).length} 篇；版本、正文、译文、注释锚点和 AI 标识检查通过（不代表语义审校）。`);
