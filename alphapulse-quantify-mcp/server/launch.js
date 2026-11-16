#!/usr/bin/env node
/**
 * MCP stdio 启动器：定位包内的 quant_mcp.py，选一个能 import aquant 的 Python，然后把
 * stdio 原样交给它（DSH 直接和 Python 进程说 JSON-RPC）。
 *
 * Python 解析顺序：
 *   1. QUANTIFY_PYTHON            显式指定解释器
 *   2. $QUANTIFY_AQUANT_ROOT/.venv/bin/python   项目自带虚拟环境（推荐）
 *   3. python3
 *
 * 之所以要这层：mcp-client 用固定 command 拉起子进程，而 npm 包的安装路径因 profile 而异；
 * 用 __dirname 定位包内文件后，路径问题就和 cwd 无关了。
 */
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const server = join(here, 'quant_mcp.py')
const aquantRoot = process.env.QUANTIFY_AQUANT_ROOT || ''

const candidates = [
  process.env.QUANTIFY_PYTHON,
  aquantRoot ? join(aquantRoot, '.venv', 'bin', 'python') : undefined,
  'python3',
].filter(Boolean)

const python = candidates.find((p) => p === 'python3' || existsSync(p))

if (!existsSync(server)) {
  console.error(`[quantify-mcp] 找不到服务端脚本：${server}`)
  process.exit(1)
}

const child = spawn(python, [server, ...process.argv.slice(2)], {
  stdio: 'inherit',
  cwd: aquantRoot && existsSync(aquantRoot) ? aquantRoot : process.cwd(),
  env: process.env,
})

child.on('error', (error) => {
  console.error(`[quantify-mcp] 启动 ${python} 失败：${error.message}`)
  process.exit(1)
})
child.on('exit', (code, signal) => process.exit(signal ? 1 : code ?? 0))

for (const signal of ['SIGTERM', 'SIGINT', 'SIGHUP']) {
  process.on(signal, () => child.kill(signal))
}
