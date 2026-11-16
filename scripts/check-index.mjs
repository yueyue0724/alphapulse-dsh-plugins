#!/usr/bin/env node
/**
 * 校验 index.json 与本地两个包一致：格式、包名、当前版本、版本排序、图标。
 * 用官方解析器（@deepseek-ai/dsh-plugin-market-index）保证 schema 不漂移。
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseMarketIndex } from '@deepseek-ai/dsh-plugin-market-index'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const PACKAGES = ['alphapulse-quantify-mcp', 'alphapulse-quantify-mcp-remote']

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

for (const dir of PACKAGES) {
  const pkg = JSON.parse(readFileSync(join(root, dir, 'package.json'), 'utf8'))
  const entry = index.plugins.find((p) => p.name === pkg.name)
  if (!entry) {
    fail(`索引里没有包 ${pkg.name}`)
    continue
  }

  const versions = entry.versions.map((v) => v.version)
  if (!versions.includes(pkg.version)) {
    fail(`${pkg.name} 索引缺少当前版本 ${pkg.version}（已列出 ${versions.join(', ') || '无'}）`)
  } else {
    ok(`${pkg.name}@${pkg.version} 已列入索引`)
  }

  const sorted = [...versions].sort((a, b) => b.localeCompare(a, undefined, { numeric: true }))
  if (versions.join('|') !== sorted.join('|')) fail(`${pkg.name} 的 versions 未按降序排列`)

  const declared = raw.plugins.find((p) => p.name === pkg.name)?.icon
  if (!declared) {
    ok(`${pkg.name} 未声明 icon`)
  } else if (declared.startsWith('http') || declared.startsWith('data:')) {
    ok(`${pkg.name} icon 为绝对地址`)
  } else if (!existsSync(join(root, declared))) {
    fail(`${pkg.name} 的 icon 文件不存在：${declared}`)
  } else {
    ok(`${pkg.name} icon 存在：${declared}`)
  }
}

const localNames = new Set(PACKAGES.map((d) => JSON.parse(readFileSync(join(root, d, 'package.json'), 'utf8')).name))
for (const plugin of index.plugins) {
  if (!localNames.has(plugin.name)) fail(`索引里的 ${plugin.name} 在仓库中没有对应包`)
}

process.exit(failed ? 1 : 0)
