// 项目实际使用的 JSON Schema 子集；遇到未实现约束报错，避免静默放过。
export function checkSchema(value, schema, at, fail) {
  const types = { null: x => x === null, array: Array.isArray,
    object: x => x !== null && typeof x === 'object' && !Array.isArray(x),
    string: x => typeof x === 'string', boolean: x => typeof x === 'boolean',
    integer: Number.isInteger, number: x => typeof x === 'number' && Number.isFinite(x) };
  if (schema.type && ![schema.type].flat().some(t => types[t]?.(value))) {
    fail(`${at}: 类型应为 ${schema.type}`); return;
  }
  if ('const' in schema && value !== schema.const) fail(`${at}: const 不匹配`);
  if (schema.enum && !schema.enum.includes(value)) fail(`${at}: 枚举非法 ${value}`);
  if (typeof value === 'string' && schema.minLength != null && value.trim().length < schema.minLength) fail(`${at}: 字符串过短`);
  if (typeof value === 'number') {
    if (schema.minimum != null && value < schema.minimum) fail(`${at}: 小于 minimum ${schema.minimum}`);
    if (schema.maximum != null && value > schema.maximum) fail(`${at}: 大于 maximum ${schema.maximum}`);
  }
  if (Array.isArray(value)) {
    if (schema.minItems != null && value.length < schema.minItems) fail(`${at}: 数组过短`);
    if (schema.maxItems != null && value.length > schema.maxItems) fail(`${at}: 数组过长`);
    if (schema.items) value.forEach((x, i) => checkSchema(x, schema.items, `${at}[${i}]`, fail));
  }
  if (types.object(value)) {
    for (const key of schema.required || []) if (!(key in value)) fail(`${at}: 缺 ${key}`);
    for (const [key, val] of Object.entries(value)) {
      const prop = schema.properties?.[key];
      if (prop) checkSchema(val, prop, `${at}.${key}`, fail);
      else if (schema.additionalProperties === false) fail(`${at}: 未登记字段 ${key}`);
      else if (typeof schema.additionalProperties === 'object') checkSchema(val, schema.additionalProperties, `${at}.${key}`, fail);
    }
  }
  for (const key of ['$ref', 'oneOf', 'anyOf', 'allOf', 'pattern']) {
    if (key in schema) fail(`${at}: 校验器尚未实现 ${key}`);
  }
}
