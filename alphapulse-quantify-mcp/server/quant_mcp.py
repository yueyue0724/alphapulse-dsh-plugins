#!/usr/bin/env python3
"""Quantify 只读 MCP server（stdio，零第三方 MCP SDK 依赖）。

把本项目 aquant 的只读能力暴露为 MCP 工具，供 DeepSeek Harness 的
`@deepseek-ai/dsh-mcp-client` 以 `transport: stdio` 接入。

设计约束：
- 只读：命令级工具只调用 `aq` 的查询类子命令；数据级工具只走 DataPortal 的读方法。
- 不写 stdout 除 JSON-RPC 帧以外的任何内容；诊断信息一律写 stderr。
- 超时与行数上限是硬约束，避免一次调用把全市场数据塞进上下文。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

AQUANT_ROOT = Path(
    os.environ.get("QUANTIFY_AQUANT_ROOT") or (Path.home() / "Finance/Quantify/aquant")
).expanduser()
QUANTDATA_ROOT = Path(
    os.environ.get("QUANTIFY_QUANTDATA_ROOT") or str(AQUANT_ROOT.parent / "QuantData")
).expanduser()
SERVER_NAME = "quantify"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL = "2025-06-18"
MAX_CHARS = 180_000
MAX_ROWS = 2_000


def log(message: str) -> None:
    print(f"[quant-mcp] {message}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- 通用


def _truncate(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    return text[:MAX_CHARS] + f"\n…（已截断，原长度 {len(text)} 字符；请缩小查询范围或降低 limit）"


def _json(obj: Any) -> str:
    return _truncate(json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":")))


def run_aq(args: list[str], timeout: float = 300) -> Any:
    """在 aquant 仓库内运行只读 `aq` 子命令，返回解析后的 JSON。"""
    proc = subprocess.run(
        [sys.executable, "-m", "aquant.cli", *args],
        cwd=str(AQUANT_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "").strip()
    try:
        data = json.loads(out) if out else None
    except json.JSONDecodeError:
        data = None
    if proc.returncode != 0:
        # 部分子命令用非零退出码表达业务结论（如 data check 的“数据陈旧”），JSON 仍有效
        if data is not None:
            if isinstance(data, dict):
                data.setdefault("_exit_code", proc.returncode)
            return data
        detail = (proc.stderr or out or "").strip().splitlines()
        tail = detail[-1] if detail else "无错误输出"
        raise RuntimeError(f"aq {' '.join(args)} 失败（退出码 {proc.returncode}）：{tail[:500]}")
    if data is None:
        return {"raw": _truncate(out)} if out else {"ok": True}
    return data


def _frame(df, limit: int = MAX_ROWS) -> dict:
    """DataFrame → 可序列化记录，带截断标记。"""
    total = int(len(df))
    head = df.head(limit)
    records = head.astype(object).where(head.notna(), None).to_dict("records")
    result: dict[str, Any] = {"rows": records, "returned": len(records), "total": total}
    if total > len(records):
        result["truncated"] = True
    return result


def portal():
    from aquant.data import DataPortal

    return DataPortal()


# --------------------------------------------------------------------------- 工具实现


def strategy_list(_: dict) -> Any:
    return run_aq(["strategy", "list"], timeout=120)


def signal_preview(args: dict) -> Any:
    cmd = ["signal", args["strategy"]]
    if args.get("date"):
        cmd += ["--date", args["date"]]
    return run_aq(cmd, timeout=900)


def paper_status(args: dict) -> Any:
    return run_aq(["paper", "status", args["strategy"]], timeout=180)


def data_health(_: dict) -> Any:
    return run_aq(["data", "check"], timeout=180)


def ops_status(_: dict) -> Any:
    return run_aq(["ops", "status"], timeout=120)


def ops_history(args: dict) -> Any:
    cmd = ["ops", "history", "--limit", str(int(args.get("limit", 20)))]
    if args.get("job"):
        cmd.append(args["job"])
    return run_aq(cmd, timeout=120)


def notify_recent(args: dict) -> Any:
    return run_aq(["notify", "recent", "--limit", str(int(args.get("limit", 20)))], timeout=120)


def notify_incidents(args: dict) -> Any:
    return run_aq(["notify", "incidents", "--limit", str(int(args.get("limit", 20)))], timeout=120)


def alpha1_status(_: dict) -> Any:
    return run_aq(["research", "alpha1", "status"], timeout=120)


def backtest_runs(args: dict) -> Any:
    root = QUANTDATA_ROOT / "runs"
    limit = max(1, min(int(args.get("limit", 20)), 200))
    strategy = args.get("strategy")
    runs = []
    if root.exists():
        bases = [root / strategy] if strategy else [p for p in root.iterdir() if p.is_dir()]
        for base in bases:
            if not base.is_dir():
                continue
            for run in base.iterdir():
                if not run.is_dir():
                    continue
                summary = run / "summary.json"
                metrics = run / "metrics.json"
                item: dict[str, Any] = {
                    "strategy": base.name,
                    "run": run.name,
                    "path": str(run),
                    "modified": run.stat().st_mtime,
                }
                for name, path in (("summary", summary), ("metrics", metrics)):
                    if path.exists():
                        text = path.read_text()
                        try:
                            parsed = json.loads(text)
                            item[name] = (
                                parsed
                                if len(json.dumps(parsed, ensure_ascii=False)) <= 4_000
                                else _truncate(text[:4_000])
                            )
                        except Exception:
                            item[name] = _truncate(text[:4_000])
                        break
                runs.append(item)
    runs.sort(key=lambda r: r["modified"], reverse=True)
    return {"runs": runs[:limit], "total": len(runs)}


def bars(args: dict) -> Any:
    p = portal()
    df = p.daily_bars(args["ts_codes"], args["start"], args["end"])
    return _frame(df, int(args.get("limit", MAX_ROWS)))


def adj_factors(args: dict) -> Any:
    p = portal()
    df = p.adj_factors(args["ts_codes"], args["start"], args["end"])
    return _frame(df, int(args.get("limit", MAX_ROWS)))


def daily_basic(args: dict) -> Any:
    p = portal()
    fields = args.get("fields") or ["pe_ttm", "pb", "total_mv", "circ_mv", "turnover_rate"]
    df = p.daily_basic(args["day"], fields)
    return _frame(df, int(args.get("limit", MAX_ROWS)))


def universe(args: dict) -> Any:
    p = portal()
    fields = tuple(args.get("fields") or ["tradable", "is_st", "is_suspended"])
    df = p.universe(args["day"], fields)
    return _frame(df, int(args.get("limit", MAX_ROWS)))


def trade_calendar(args: dict) -> Any:
    cal = portal().calendar
    out: dict[str, Any] = {"first": cal.first, "last": cal.last, "count": len(cal.sessions)}
    day = args.get("day")
    if day:
        item: dict[str, Any] = {"day": day, "is_session": cal.is_session(day)}
        try:
            item["previous"] = cal.previous(day)
        except Exception:
            item["previous"] = None
        try:
            item["next"] = cal.next(day)
        except Exception:
            item["next"] = None
        out["day"] = item
        if item.get("next") is None:
            out["note"] = f"日历仅覆盖到 {cal.last}，其后交易日未知（本机 calendar-sync 未运行到最后）"
    if args.get("start") and args.get("end"):
        sessions = cal.between(args["start"], args["end"])
        limit = max(1, min(int(args.get("limit", 60)), 500))
        out["sessions"] = sessions[:limit]
        out["session_count"] = len(sessions)
    return out


def index_daily(args: dict) -> Any:
    p = portal()
    df = p.index_daily(args["ts_code"], args["start"], args["end"])
    return _frame(df, int(args.get("limit", MAX_ROWS)))


# --------------------------------------------------------------------------- 工具注册表


def _date(desc: str) -> dict:
    return {"type": "string", "description": desc, "pattern": r"^\d{4}-\d{2}-\d{2}$"}


def _codes() -> dict:
    return {
        "type": "array",
        "items": {"type": "string"},
        "description": "证券代码，支持 000001.SZ / 600000.SH / 830799.BJ 或 6 位代码",
        "minItems": 1,
        "maxItems": 200,
    }


STRATEGY_HINT = "策略 id，例如 alpha1、alpha2ml、alpha3、polaris1、xingmai2、xingmai3"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "strategy_list",
        "description": "列出 aquant 已注册策略：id、显示名、版本、模拟盘账户与通知通道。只读。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": strategy_list,
    },
    {
        "name": "signal_preview",
        "description": (
            "只计算某策略在某信号日的目标股池（不发布、不下单、不推送）。"
            "返回 signal_date、execution_date 与 targets（ts_code/name/weight）。计算可能需要数十秒。"
            "本机可用性：xingmai3 可直接预览；alpha1/alpha2ml 需要 QuantData/frozen 冻结产物；"
            "polaris1/xingmai2 需要盘中快照；alpha3 只走人工观察流程。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "description": STRATEGY_HINT},
                "date": _date("信号日 YYYY-MM-DD；缺省为最近一个已收盘交易日"),
            },
            "required": ["strategy"],
            "additionalProperties": False,
        },
        "handler": signal_preview,
    },
    {
        "name": "paper_status",
        "description": (
            "读取某策略模拟盘账户状态：资金/净值、持仓、最新目标批次、运行态。只读，不改账户。"
            "账本经 Supabase 只读连接读取，是生产账本，通常比本机 Mongo 行情更新；"
            "不要用它的日期推断本机行情最新交易日（那看 data_health）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"strategy": {"type": "string", "description": STRATEGY_HINT}},
            "required": ["strategy"],
            "additionalProperties": False,
        },
        "handler": paper_status,
    },
    {
        "name": "data_health",
        "description": "数据新鲜度巡检：各集合最新交易日、stale 明细、日历是否覆盖、待核验退市证券。只读，不发告警。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": data_health,
    },
    {
        "name": "ops_status",
        "description": "定时任务状态（本机 launchd 视图）：每个 job 的加载状态、计划时刻、最近运行与退出码。只读。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": ops_status,
    },
    {
        "name": "ops_history",
        "description": "定时任务运行历史（最近 N 条，可按任务名过滤）。只读。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job": {"type": "string", "description": "任务名，如 data-update、paper-execute"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
            },
            "additionalProperties": False,
        },
        "handler": ops_history,
    },
    {
        "name": "notify_recent",
        "description": "最近推送记录（outbox）。只读，不发送、不重试。",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
            "additionalProperties": False,
        },
        "handler": notify_recent,
    },
    {
        "name": "notify_incidents",
        "description": "待诊断告警队列（只读查看，不运行诊断、不外发）。",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
            "additionalProperties": False,
        },
        "handler": notify_incidents,
    },
    {
        "name": "alpha1_status",
        "description": "Alpha1 研究自动化状态：当前窗口、期次、任务进度与阻塞。只读。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": alpha1_status,
    },
    {
        "name": "backtest_runs",
        "description": (
            "列出 QuantData/runs 下的回测产物（策略、run 目录、修改时间，附 summary/metrics 摘要）。"
            "只列出，不运行回测、不发布。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "description": "只列该策略的 run；缺省为全部"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
            },
            "additionalProperties": False,
        },
        "handler": backtest_runs,
    },
    {
        "name": "bars",
        "description": (
            "读取日线（stock_day 为主，缺日由补充集合补齐；已剔除隔离行）。"
            "字段含 ts_code/code/date/open/high/low/close/vol/amount 等，vol 单位为手。"
            "数据来自研究库（经本机配置的只读 Mongo 身份读取，当前为 dgx8001-quant 的 SSH 隧道），"
            "不是 Mac mini 生产库；最新可用交易日以 data_health 为准。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ts_codes": _codes(),
                "start": _date("起始交易日（含）"),
                "end": _date("结束交易日（含）"),
                "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 2000},
            },
            "required": ["ts_codes", "start", "end"],
            "additionalProperties": False,
        },
        "handler": bars,
    },
    {
        "name": "adj_factors",
        "description": "读取复权因子（已剔除隔离行）。用于把原始价换算为后复权序列。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ts_codes": _codes(),
                "start": _date("起始交易日（含）"),
                "end": _date("结束交易日（含）"),
                "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 2000},
            },
            "required": ["ts_codes", "start", "end"],
            "additionalProperties": False,
        },
        "handler": adj_factors,
    },
    {
        "name": "daily_basic",
        "description": "读取单日估值截面（已剔除隔离行、去重）。常用字段 pe_ttm、pb、total_mv、circ_mv、turnover_rate。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "day": _date("交易日 YYYY-MM-DD"),
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要的字段；缺省 pe_ttm/pb/total_mv/circ_mv/turnover_rate",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 2000},
            },
            "required": ["day"],
            "additionalProperties": False,
        },
        "handler": daily_basic,
    },
    {
        "name": "universe",
        "description": "读取单日证券资格截面：tradable、is_st、is_suspended 等（已叠加隔离状态）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "day": _date("交易日 YYYY-MM-DD"),
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要的字段；缺省 tradable/is_st/is_suspended",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 2000},
            },
            "required": ["day"],
            "additionalProperties": False,
        },
        "handler": universe,
    },
    {
        "name": "trade_calendar",
        "description": "交易日历：覆盖范围；给 day 返回是否交易日与前后交易日；给 start/end 返回区间内的交易日列表。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "day": _date("要判断的日期"),
                "start": _date("区间起始日"),
                "end": _date("区间结束日"),
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 60},
            },
            "additionalProperties": False,
        },
        "handler": trade_calendar,
    },
    {
        "name": "index_daily",
        "description": "读取指数日线（trade_date/open/close）。例如 000300.SH、899050.BJ。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ts_code": {"type": "string", "description": "指数代码，如 000300.SH"},
                "start": _date("起始交易日（含）"),
                "end": _date("结束交易日（含）"),
                "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 2000},
            },
            "required": ["ts_code", "start", "end"],
            "additionalProperties": False,
        },
        "handler": index_daily,
    },
]

BY_NAME: dict[str, dict[str, Any]] = {t["name"]: t for t in TOOLS}


# --------------------------------------------------------------------------- JSON-RPC


def _reply(msg_id: Any, result: Any) -> None:
    frame = {"jsonrpc": "2.0", "id": msg_id, "result": result}
    sys.stdout.write(json.dumps(frame, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _error(msg_id: Any, code: int, message: str) -> None:
    frame = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
    sys.stdout.write(json.dumps(frame, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _call_tool(params: dict) -> dict:
    name = params.get("name")
    tool = BY_NAME.get(name)
    if tool is None:
        return {"content": [{"type": "text", "text": f"未知工具：{name}"}], "isError": True}
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        return {"content": [{"type": "text", "text": "arguments 必须是对象"}], "isError": True}
    try:
        value = tool["handler"](args)
        return {"content": [{"type": "text", "text": _json(value)}], "isError": False}
    except subprocess.TimeoutExpired:
        return {"content": [{"type": "text", "text": f"{name} 超时：命令未在限制时间内完成"}], "isError": True}
    except Exception as exc:  # 业务异常回填给模型，不中断会话
        log(traceback.format_exc())
        return {"content": [{"type": "text", "text": f"{name} 失败：{type(exc).__name__}: {exc}"}], "isError": True}


def handle(message: dict) -> None:
    method = message.get("method")
    msg_id = message.get("id")
    is_notification = "id" not in message
    params = message.get("params") or {}

    if method == "initialize":
        requested = params.get("protocolVersion") or DEFAULT_PROTOCOL
        _reply(
            msg_id,
            {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Quantify 量化研究工作区的只读工具集：策略与模拟盘查询、数据健康、"
                    "定时任务与推送记录、日线/复权/估值/资格/日历/指数查询。"
                    "全部工具无副作用；生产系统的写入与推送不在本服务内。"
                ),
            },
        )
        return

    if is_notification:
        return  # notifications/initialized、notifications/cancelled 等无需响应

    if method == "ping":
        _reply(msg_id, {})
    elif method == "tools/list":
        _reply(
            msg_id,
            {
                "tools": [
                    {
                        "name": t["name"],
                        "description": t["description"],
                        "inputSchema": t["inputSchema"],
                        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
                    }
                    for t in TOOLS
                ]
            },
        )
    elif method == "tools/call":
        _reply(msg_id, _call_tool(params))
    elif method == "resources/list":
        _reply(msg_id, {"resources": []})
    elif method == "prompts/list":
        _reply(msg_id, {"prompts": []})
    else:
        _error(msg_id, -32601, f"method not found: {method}")


def main() -> int:
    log(f"starting {SERVER_NAME} {SERVER_VERSION} (python {sys.version.split()[0]})")
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            log(f"bad frame: {exc}")
            _error(None, -32700, "parse error")
            continue
        try:
            handle(message)
        except Exception as exc:  # 任何未捕获异常都要回帧，否则客户端会挂起
            log(traceback.format_exc())
            _error(message.get("id"), -32603, f"{type(exc).__name__}: {exc}")
    log("stdin closed, exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
