// Генерация TS-типов протокола из JSON Schema Pydantic-моделей бэкенда.
//   npm run gen:types   (из корня — сначала выгружает схему из бэкенда)
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { compile } from 'json-schema-to-typescript'

const here = dirname(fileURLToPath(import.meta.url))
const dir = resolve(here, '../src/shared/protocol')
const schema = JSON.parse(readFileSync(resolve(dir, 'schema.json'), 'utf8'))

const ts = await compile(schema, 'Protocol', {
  bannerComment:
    '/* Сгенерировано из Pydantic-моделей бэкенда (npm run gen:types). Не редактировать вручную. */',
  additionalProperties: false,
  unreachableDefinitions: true,
  strictIndexSignatures: true,
  ignoreMinAndMaxItems: true,
  style: { semi: false, singleQuote: true, printWidth: 100 },
})
writeFileSync(resolve(dir, 'generated.ts'), ts)
console.log('generated.ts updated')
