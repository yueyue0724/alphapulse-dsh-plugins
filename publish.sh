#!/usr/bin/env bash
# 发布 dsh-quantify-mcp 到 npmjs。
#
# npm 要求「发布者启用 2FA」或「使用可绕过 2FA 的 granular access token」，二选一：
#
#   NPM_TOKEN=npm_xxxxxxxx ./publish.sh     # 推荐：npmjs → Access Tokens → Granular Token
#                                            #       Packages: Read and write；勾选 Bypass two-factor authentication
#   NPM_OTP=123456 ./publish.sh             # 已开 2FA：用 login token，附一次性口令
#
# 提示：token 只放环境变量，不要粘进对话或写进仓库文件。
set -euo pipefail
cd "$(dirname "$0")/dsh-quantify-mcp"

args=(publish --access public)
if [[ -n "${NPM_OTP:-}" ]]; then
  args+=(--otp "$NPM_OTP")
fi

if [[ -n "${NPM_TOKEN:-}" ]]; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  printf '//registry.npmjs.org/:_authToken=%s\n' "$NPM_TOKEN" > "$tmp/.npmrc"
  chmod 600 "$tmp/.npmrc"
  npm "${args[@]}" --userconfig "$tmp/.npmrc"
else
  npm "${args[@]}"
fi

echo "--- registry 回读 ---"
npm view dsh-quantify-mcp version
