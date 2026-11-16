# alphapulse-quantify-mcp-remote

Alphapulse Quantify 的**远程模式**：本机不需要 Python、不需要 aquant 仓库，只把 MCP 的 stdio
通过 SSH 转发到生产机，服务端在那边用生产库跑同一套 16 个只读工具。

工具前缀 `mcp__quantify-remote__*`。

## 前置

1. 本机有 `ssh` 客户端（Windows 10+ 自带 OpenSSH Client）。
2. 到生产机的**免密登录**（密钥，不是密码）：

   ```bash
   ssh-keygen -t ed25519            # 还没有密钥的话
   ssh-copy-id stock-researcher-macmini
   ssh -T stock-researcher-macmini 'echo ok'   # 必须能直接返回 ok
   ```

   插件用 `BatchMode=yes`，不会弹密码提示；登不进去的表现就是 `Connection closed`。

3. 生产机上有服务端脚本 `~/Finance/Quantify/quantify-mcp-server.py`（部署方式见下）。

## 部署服务端脚本

在能 SSH 到生产机的机器上，从本仓库复制一次：

```bash
scp alphapulse-quantify-mcp/server/quant_mcp.py \
    stock-researcher-macmini:~/Finance/Quantify/quantify-mcp-server.py
```

脚本更新后重复执行即可（插件每次启动都会重新读取它）。

## 换主机

改 `cordis.patch.yml` 里的 `stock-researcher-macmini`，以及远程命令中的路径。

## 与本地版的区别

| | 本地版 | 远程版 |
|---|---|---|
| 需要本机 Python + aquant | 是 | 否 |
| 数据来源 | 本机连的 Mongo（可能是研究副本） | 生产库（最新） |
| 工具前缀 | `mcp__quantify__*` | `mcp__quantify-remote__*` |
| 依赖 | Node + Python + aquant | 只要能 SSH |

两个版本可以只装一个；同时装会看到两组同功能工具，不建议。
