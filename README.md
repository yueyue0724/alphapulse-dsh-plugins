# DSH 插件：Quantify 只读研究台

把 `../aquant` 的只读查询能力做成一个 DeepSeek Harness MCP 插件（configuration-only bundle +
stdio MCP server）。安装后 agent 获得 16 个 `mcp__quantify__*` 工具，全部无副作用。

## 目录

```
dsh-plugins/
├── index.json                      # 插件市场索引（format 1），指向 npm 包 alphapulse-quantify-mcp
├── PUBLISH.md                      # npm 发布 + 市场上线清单
└── alphapulse-quantify-mcp/               # 可发布的 npm 包（manifest + patch + locale + icon + server）
    ├── package.json
    ├── cordis.patch.yml            # 插入 @deepseek-ai/dsh-mcp-client，transport: stdio
    ├── server/quant_mcp.py         # MCP stdio 服务（零第三方依赖）
    ├── server/launch.js            # 定位 python 并转发 stdio（包内自足，不依赖 cwd）
    ├── locale/{en,zh}.json         # meta.title / description / detail
    ├── icon.svg
    └── docs/{DETAIL.md,DETAIL.zh.md,preview.svg}
```

## 工作方式

- 命令级工具在 aquant 仓库内跑只读子命令（`aq strategy list`、`aq signal`、`aq paper status`、
  `aq data check`、`aq ops status/history`、`aq notify recent/incidents`、`aq research alpha1 status`），
  解析其 JSON 输出返回。
- 数据级工具直接走 `DataPortal` 的读方法（日线、复权因子、估值截面、资格截面、交易日历、指数日线），
  不经过子进程，行数默认上限 2000。
- `backtest_runs` 只列 `QuantData/runs/` 产物，不运行回测。
- stdout 只写 JSON-RPC 帧，日志写 stderr。
- 进程链路：DSH → `node node_modules/alphapulse-quantify-mcp/server/launch.js`（cwd 是 profile 目录）
  → `$QUANTIFY_AQUANT_ROOT/.venv/bin/python server/quant_mcp.py` → stdio JSON-RPC。

## 安装 / 升级 / 卸载

- 本地开发：`plugin_manager` `install_bundle`，target 为 `alphapulse-quantify-mcp` 目录的绝对路径
  （profile 里记录为 `link:`）；改完文件 toggle 一次 bundle 即可让 MCP 子进程重启。
- npm 分发：发布后 `install_bundle target: alphapulse-quantify-mcp@0.1.0`；版本升级见 `PUBLISH.md`。
- 卸载：`plugin_manager` `remove_bundle`，target 为 `alphapulse-quantify-mcp`。

## 已知边界

- 行情、估值、资格、日历读的是**研究库**：`~/.quantaxis/setting/config.ini` 的只读身份指向
  `127.0.0.1:27018`，而该端口是 `ssh -L 127.0.0.1:27018:127.0.0.1:27017 dgx8001-quant` 隧道，
  背后是 8001 上的 Mongo，不是 Mac mini 生产库；副本不随生产更新（2026-11 时止于 2026-10-23）。
- `signal_preview` 本机只有 `xingmai3` 可直接算：`alpha1`/`alpha2ml` 缺 `QuantData/frozen` 冻结产物，
  `polaris1`/`xingmai2` 需要盘中快照，`alpha3` 只走人工观察。
- `paper_status` 读 Supabase 生产账本（只读），日期通常比本机行情新；不要用它推断行情最新日。
- 生产写入、推送、下单都不在本插件内。
