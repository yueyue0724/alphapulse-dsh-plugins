#!/usr/bin/env node
/**
 * 校验 index.json：格式、包名、当前版本、版本排序、图标文件。
 * 用官方解析器（@deepseek-ai/dsh-plugin-market-index）保证 schema 不漂移。
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseMarketIndex } from '@deepseek-ai/dsh-plugin-market-index'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const pkgDir = join(root, 'alphapulse-quantify-mcp')
const pkg = JSON.parse(readFileSync(join(pkgDir, 'package.json'), 'utf8'))
const raw = JSON.parse(readFileSync(join(root, 'index.json'), 'utf8'))

let failed = false
const ok = (m) => console.log(`✓ ${m}`)
const fail = (m) => {
  failed = true
  console.error(`✗ ${m}`)
}

let index
try {
  index = parseMarketIndex(raw, 'https://example.com/index.json')
  ok('index.json 通过 format 1 校验')
} catch (error) {
  fail(`index.json 校验失败：${error.message}`)
  process.exit(1)
}

const entry = index.plugins.find((p) => p.name === pkg.name)
if (!entry) {
  fail(`索引里没有包 ${pkg.name}`)
  process.exit(1)
}
ok(`索引含 ${pkg.name}`)

const versions = entry.versions.map((v) => v.version)
if (!versions.includes(pkg.version)) {
  fail(`索引缺少当前版本 ${pkg.version}（已列出 ${versions.join(', ') || '无'}）`)
} else {
  ok(`索引含当前版本 ${pkg.version}`)
}

const sorted = [...versions].sort((a, b) => b.localeCompare(a, undefined, { numeric: true }))
if (versions.join('|') !== sorted.join('|')) fail('versions 未按版本降序排列')

if (entry.icon) {
  const relative = raw.plugins.find((p) => p.name === pkg.name).icon
  if (relative.startsWith('http') || relative.startsWith('data:')) {
    ok('icon 为绝对地址，跳过文件检查')
  } else if (!existsSync(join(root, relative))) {
    fail(`icon 文件不存在：${relative}`)
  } else {
    ok(`icon 文件存在：${relative}`)
  }
}

if (raw.plugins.some((p) => p.name !== pkg.name)) {
  fail('索引里出现了与当前包无关的插件条目')
}

process.exit(failed ? 1 : 0)
