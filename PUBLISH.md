# 发布到 npm 与插件市场

包已经按 npm 分发形态整理好（`server/` 在包内、`cordis.patch.yml` 用 profile 相对路径拉起）。
本文件是发布清单，按顺序执行即可。

## 0. 前置

- Node/npm 已有；包名 `alphapulse-quantify-mcp` 已在 2026-11-16 发布（0.1.0）。
- npm 账号 `alphapulse_billy`，2FA 方式为**通行密钥（passkey）**——没有 6 位 TOTP，发布时走浏览器授权。

## 1. 发布前自检

```bash
cd /Users/yueyue/Finance/Quantify/dsh-plugins/alphapulse-quantify-mcp
npm pack --dry-run          # 应看到 11 个文件，含 server/launch.js 与 server/quant_mcp.py
```

## 2. 发布（passkey 账号的实际流程）

```bash
npm login        # 网页授权一次
npm publish --access public
```

`npm publish` 会打印 `Authenticate your account at: https://www.npmjs.com/auth/cli/<id>` 并等回车。
在终端里直接回车会用默认浏览器打开授权页，点一下 Touch ID 即可。**在非交互环境**（脚本/后台）里
npm 会把该链接打码成 `***` 并立即退出，此时用伪终端拿到真链接：

```bash
printf '\n' | script -q /dev/null npm publish --access public   # 或直接 script -q /dev/null npm publish
open "https://www.npmjs.com/auth/cli/<id>"                       # 浏览器里点授权
```

成功后注意两件事：

- npm 11 是**暂存发布**：会先出现 `0.0.0-stage` 占位版本，真正的 `0.1.0` 要等 1–2 分钟处理完才可见。
  期间 `npm view` 报 404 属正常，别重复发布。
- 确认：`npm view alphapulse-quantify-mcp version` → `0.1.0`；`npm view alphapulse-quantify-mcp versions` 会同时列出
  `0.0.0-stage` 与 `0.1.0`。


## 3. 本机从 tarball 切到 registry

当前 profile 里装的是 tarball 版本（`file:/tmp/alphapulse-quantify-mcp-0.1.0.tgz`）。切换：

```
plugin_manager remove_bundle   target: alphapulse-quantify-mcp
plugin_manager install_bundle  target: alphapulse-quantify-mcp@0.1.0
```

装完调用 `mcp__quantify__strategy_list` 确认。

## 4. 上线插件市场（可选）

1. 装市场 bundle：`plugin_manager install_bundle target: @deepseek-ai/dsh-experimental-plugin-market-bundle@0.2.2-rc.3`
   （官方 optional，装完插件页出现 Discover）。
2. 托管 `../index.json`：放到任意 HTTPS 静态地址，例如
   `https://raw.githubusercontent.com/<you>/<repo>/main/dsh-plugins/index.json`。
   要求：`http(s)`、无凭据、**不能重定向**（GitHub raw 可以，Gist 重定向不行）。
3. Discover 里添加该 URL；条目出现后点安装，等价于
   `install_bundle target: alphapulse-quantify-mcp@0.1.0`。
4. 索引里的相对 `icon` 按索引 URL 解析，所以 `index.json` 要和 `alphapulse-quantify-mcp/` 目录同级托管。

## 5. 发新版

1. 改 `package.json` 的 `version`（SemVer）。
2. `npm publish`。
3. 在 `index.json` 的 `versions` **数组最前面**加新版本条目（`publishTimestamp` 用真实发布时间的 Unix 秒），
   旧版本保留，`defaultVersion` 自动取最高兼容版本。
4. 重新托管 `index.json`。

## 6. 别人装之前要知道

- `cordis.patch.yml` 里的 `QUANTIFY_AQUANT_ROOT` 目前是本机路径，别人要么改这一行，
  要么在 profile patch 里覆盖 `config.env`（row id `quantify-mcp`）。
- 需要能 `import aquant` 的 Python：默认用 `$QUANTIFY_AQUANT_ROOT/.venv/bin/python`，
  也可用 `QUANTIFY_PYTHON` 指定。
- 只读：无写入/下单/推送工具，MCP 客户端也没有逐工具审批。

## 7. 走 CI 发版（可信发布 / OIDC）

仓库里 `\.github/workflows/publish.yml` 在推 `v*` tag 时发布，不需要任何长期 token：

```bash
# 1. 改 alphapulse-quantify-mcp/package.json 的 version
# 2. 在 index.json 的 versions 数组最前面加同版本条目
git add -A && git commit -m "release: X.Y.Z"
git tag vX.Y.Z && git push origin main && git push origin vX.Y.Z
```

一次性配置（只做一次）：npmjs.com → 包 → Settings → Trusted Publisher → GitHub Actions，四个字段
`yueyue0724` / `alphapulse-dsh-plugins` / `publish.yml` / environment 留空，并在 **Allowed actions**
里勾上 `npm publish`。漏勾这一项的表现是：provenance 签名成功，但 registry 回
`403 OIDC permission denied for this action`。

两个已知的安装侧延迟（不是发布失败）：

- 新版刚发布时，`registry.npmjs.org` 的 packument 里已经有版本，但 tarball 可能还 404 几分钟；
  等 CDN 同步后再装。
- 安装时若回退到 `registry.npmmirror.com`，镜像可能还没同步新版本；`install_bundle` 显式传
  `registry: https://registry.npmjs.org/` 可绕过。
