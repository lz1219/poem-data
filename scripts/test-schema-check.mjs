import test from 'node:test';
import assert from 'node:assert/strict';
import {checkSchema} from './schema-check.mjs';

const errors = (v, schema) => { const out=[]; checkSchema(v,schema,'fixture',e=>out.push(e)); return out; };
test('影像页序与修订号必须是正整数', () => {
  const schema={type:'integer',minimum:1};
  for(const bad of [-1,0,0.5,'1',null]) assert.ok(errors(bad,schema).length);
  for(const good of [1,112]) assert.deepEqual(errors(good,schema),[]);
});
test('数值界限包含边界，未实现约束仍阻止通过', () => {
  const schema={type:'number',minimum:-180,maximum:180};
  for(const good of [-180,0,180]) assert.deepEqual(errors(good,schema),[]);
  for(const bad of [-181,181]) assert.ok(errors(bad,schema).length);
  assert.ok(errors({},{$ref:'unknown'}).some(e=>e.includes('尚未实现')));
});
