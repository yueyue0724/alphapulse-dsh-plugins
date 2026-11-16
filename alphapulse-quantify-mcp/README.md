# alphapulse-quantify-mcp

把 Alphapulse Quantify 量化研究工作区（aquant）的**只读**查询能力，作为
[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) MCP 插件接入 agent。

安装后得到 16 个工具，前缀 `mcp__quantify__`，全部无副作用：不写库、不下单、不发消息。

## 工具

| 类别 | 工具 |
|---|---|
| 策略 | `strategy_list` `signal_preview` `alpha1_status` |
| 模拟盘 | `paper_status` |
| 数据 | `bars` `adj_factors` `daily_basic` `universe` `trade_calendar` `index_daily` `data_health` |
| 回测/运维 | `backtest_runs` `ops_status` `ops_history` `notify_recent` `notify_incidents` |

## 安装

```bash
# 在本机 DSH profile 里安装（或让 agent 调 plugin_manager install_bundle）
dsh   # 打开 Plugins → Add plugin，选择 npm 包名 alphapulse-quantify-mcp
```

装好后插件页出现「量化研究台」，启用即注册工具。

## 前置条件

1. **aquant 检出 + 虚拟环境**：`QUANTIFY_AQUANT_ROOT` 指向 aquant 仓库，且
   `$QUANTIFY_AQUANT_ROOT/.venv/bin/python` 能 `import aquant`（含 pandas/pymongo）。
2. 本机配置了 aquant 的只读 Mongo 身份（`~/.quantaxis/setting/config.ini`）。
3. `paper_status` 需要 aquant 的 Supabase 只读凭据；没有时只有该工具失败，其余照常。

环境变量（都在 `cordis.patch.yml` 的 `env` 里改）：

| 变量 | 作用 |
|---|---|
| `QUANTIFY_AQUANT_ROOT` | aquant 仓库路径，用于定位 venv 并作为 `aq` 的 cwd |
| `QUANTIFY_PYTHON` | 直接指定 Python 解释器，优先级最高 |
| `QUANTIFY_QUANTDATA_ROOT` | 回测产物目录，默认 `$QUANTIFY_AQUANT_ROOT/../QuantData` |

## 边界

- 只读：没有写入、下单、推送类工具。
- `signal_preview` 依赖各策略的输入产物：`xingmai3` 可直接算；`alpha1`/`alpha2ml` 需要冻结产物；
  `polaris1`/`xingmai2` 需要盘中快照；`alpha3` 仅人工观察。
- 行情来自 `QUANTIFY_AQUANT_ROOT` 所连的 Mongo（可能是研究副本，未必是最新交易日）；
  `paper_status` 读生产账本，两者日期可能不一致，以 `data_health` 为准。
- MCP 客户端没有逐工具审批，因此本包只暴露只读工具。

## 开发

```
server/quant_mcp.py   # 零第三方依赖的 stdio MCP server（JSON-RPC 手写）
server/launch.js      # 定位 python 并转发 stdio
cordis.patch.yml      # 插入 @deepseek-ai/dsh-mcp-client，transport: stdio
```
