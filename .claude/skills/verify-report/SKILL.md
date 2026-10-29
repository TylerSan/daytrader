---
name: verify-report
description: Use when you need to verify whether a DayTrader scheduled report (premarket, intraday-4h-1, intraday-4h-2, eod, night, asia, weekly) really succeeded, after a launchd run or a manual re-run; checks state.db, the Obsidian file, the wrapper log and content heuristics, and says what cannot be verified.
---

# verify-report：确认一份 DayTrader 定时报告是否真的成功

launchd 看不出失败（preflight 失败时 wrapper 仍 `exit 0`），Telegram 推送结果被吞掉，
所以"没报错"不等于"成功"。本 skill 给出一套可重复的验收流程，核心工具是
`scripts/verify_report.py`（纯 stdlib，不连 TWS，任何时候都能跑）。

## 1. 什么时候用 / 什么叫"成功"

用在：launchd 定时任务跑完之后、手动补跑之后、用户问"今天的报告出了吗/对不对"时。

一份报告**成功**＝以下三条同时成立：

1. `data/state.db` 的 `reports` 表有 `status='success'` 的行，键为 `(report_type, date)`
   （weekly 例外：走旧系统，不写 state.db）。
2. Obsidian vault 里的目标文件存在且非空（> 500 bytes）。
3. wrapper 日志 `data/logs/launchd/<type>-YYYYMMDD-HHMMSS.log` 里有
   `preflight ok, invoking` 和 `run exit=0`，且没有 `PREFLIGHT FAILED` / `Report FAILED`。

**Telegram 送达今天无法验证**：`TelegramPusher.push` 吞掉异常返回
`PushResult(success=False)`，orchestrator 丢弃返回值，`reports.telegram_msg_ids` 从不写入。
脚本对 premarket / 4h / eod 的 telegram 项永远最多是 WARN（UNVERIFIABLE），
只能让用户在 Telegram 里肉眼确认。日志里的 `[notify_preflight] Telegram OK msg_id=N`
只证明 **preflight 失败告警**发出去了，不是报告送达。

## 2. 流程

所有命令在仓库根目录执行。验证**生产**时必须加
`--project-root "/Users/tylersan/Projects/Day trading/.claude/worktrees/nice-varahamihira-9d6142"`（见 §5）。

**(a) CLI 冒烟**

```bash
uv run daytrader reports dry-run --type <X>
```

老实说：这是 Phase-1 stub，只打印 7 行固定的 `[dry-run] ...` 然后 exit 0，
不读配置、不连 IB、不调 AI、不写文件。它**只证明** CLI 能 import、`<X>` 是合法类型名。
不能当作"管线健康"的证据。

**(b) 跑验收脚本**

```bash
uv run python scripts/verify_report.py --type <X>                      # 默认日期见下
uv run python scripts/verify_report.py --type <X> --date 2026-10-09    # 指定日期键
uv run python scripts/verify_report.py --type <X> --file path/to.md    # 直接验一个文件
uv run python scripts/verify_report.py --type <X> --json               # 机器可读
uv run python scripts/verify_report.py --type <X> --strict             # WARN 也算失败
```

默认日期＝orchestrator 会用的日期键：premarket/4h/eod 取 **ET 今天**，night/asia 取
**PT 今天**，weekly 取最近一个周日（本地）。

8 项检查：`state_db_row`、`output_file`、`latest_run_log`、`telegram`、
`futures_not_etf`（启发式）、`session_sections`（仅 premarket，WARN 不 FAIL）、
`language`（CJK 比例，阈值 0.15）、`required_sections`（复用 output_validator）。
末行 `VERDICT: PASS|WARN|FAIL`。退出码：0＝PASS（或无 `--strict` 的 WARN），
1＝FAIL，2＝报告文件根本找不到。

注意：premarket/4h/eod 因 telegram 永远 WARN，所以这三类正常结果是 `VERDICT: WARN`；
`--strict` 对它们必然失败，只对 night/asia 有意义。

**(c) 失败了就诊断 preflight / 日志**

```bash
uv run python scripts/diagnose_preflight.py --cadence <X> --last-failed
uv run python scripts/diagnose_preflight.py --summary 20          # 最近 20 次运行分类
uv run python scripts/diagnose_preflight.py --cadence <X> --last-failed --json --no-live
```

（`--log-dir` 默认 `<root>/data/logs/launchd`；`--no-live` 跳过实时 TWS 端口 / state.db 探测。）

**(d) 人工抽查（打开文件读，脚本只是启发式）**

- 期货点位不是 ETF 点位：ES/MES ≈ 6000s–7000s（不是 SPY ≈ 600s），
  NQ/MNQ ≈ 20000s–30000s（不是 QQQ ≈ 500s），GC/MGC ≈ 4000s。
- premarket 是否有 亚盘 / 欧盘 段落（当前模板只要求合并的
  "Breaking news (overnight Asia + Europe)"，缺了是模板缺口，不是运行失败）。
- night/asia 必须是中文正文（b38a985 后硬性要求）；premarket/eod 也应为中文。
- 不应出现 `(no bars available)` 之类的占位文本。
- 警惕看起来编造的整数点位（7800.00、31000.00 这种成串出现）——对照 IB / TradingView 抽两个数。

**(e) ET 日期陷阱**

premarket / intraday-4h-1 / intraday-4h-2 / eod 以 **ET 日期**为键。**21:00 PT 之后绝不要手动跑这四类**：
那时 ET 已是次日，会写入"明天"的 success 行，第二天 launchd 的正式运行会被
`already_generated_today` 挡掉（输出 `Report already generated today (skipped).`）。
night/asia 以 PT 日期为键，不受影响。

**(f) TWS 恢复后补跑（按时间顺序）**

```bash
uv run python scripts/preflight_check.py          # 先确认 TWS 端口 + API 握手 OK
uv run daytrader reports run --type premarket --no-pdf
uv run daytrader reports run --type intraday-4h-1 --no-pdf
uv run daytrader reports run --type intraday-4h-2 --no-pdf
uv run daytrader reports run --type eod --no-pdf
uv run daytrader reports run --type night --no-pdf
uv run daytrader reports run --type asia --no-pdf
uv run daytrader weekly run --ai                  # weekly 不需要 TWS（yfinance）
```

只补当天已错过的时段；每跑完一个就用 (b) 验收再跑下一个。直接调 CLI 会绕过 preflight
（preflight 只在 wrapper 里），所以先手动跑一次 preflight。补跑内容反映**运行时刻**的数据
（orchestrator 用 `run_at=now`），不是原定时段的快照。没有 yfinance / databento 备用数据源——
reports 代码里 IB 是唯一来源，TWS 不起来就没有办法。

**(g) 强制重新生成（破坏性，必须先征得用户同意）**

没有 `--force`。唯一办法是删掉 success 行再重跑，**先备份**：

```bash
cp data/state.db "data/state.db.bak-$(date +%Y%m%d-%H%M%S)"
sqlite3 data/state.db "DELETE FROM reports WHERE report_type='asia' AND date='2026-10-09' AND status='success';"
```

⚠️ 这会删除历史记录并覆盖 vault 里的同名文件。执行前向用户确认类型、日期和行 id
（先 `SELECT id, report_type, date, status, obsidian_path FROM reports WHERE ...;`）。
CLI 只能生成"今天"日期键的报告；重生成过去日期需要临时 Python 调
`Orchestrator.run_<cadence>(run_at=<原定 UTC 时刻>)`（仓库里没有现成脚本）。

## 3. Feature map（每类报告）

通用：
- 入口 `uv run daytrader reports run --type <X> --no-pdf`（weekly 除外）。
- 每次运行日志 `data/logs/launchd/<X>-YYYYMMDD-HHMMSS.log`（文件名时间是本机 PT）；
  launchd stdout 汇总 `data/logs/launchd/<X>.<HHMM>pt.out`（.err 一直是 0 字节）。
- 手动补跑日志（人工命名）在 `data/logs/manual/`。
- plist：`~/Library/LaunchAgents/com.daytrader.report.<X>.<HHMM>pt.plist`（只读，勿改）。
- vault：`~/Documents/DayTrader Vault`（`obsidian.vault_path`），写失败回落到 `data/exports/<同名文件>`。
- preflight 失败共有签名：`] PREFLIGHT FAILED` 加以下之一：
  `[preflight] ✗ TWS port unreachable at 127.0.0.1:7496`；
  `[preflight] ✗ TWS API not responsive: API handshake failed: TimeoutError: `
  （前面常有 `positions request timed out` / `open orders request timed out`）；
  少见：`TWS API not responsive: connect() returned but isConnected() is False`、
  `[preflight] ✗ claude CLI not found on PATH`、`[preflight] ✗ config: missing ...`。
- 良性噪声（不是失败）：`Error 321, reqId`、`[futures_section] WARNING: get_open_interest`、
  `[ib_client] WARNING: requested`、`findfont:`、`$ES=F: possibly delisted`。

### premarket

| 项 | 值 |
|---|---|
| 调度 | 周一至周五 06:00 PT |
| 入口 | `uv run daytrader reports run --type premarket --no-pdf` |
| wrapper | `scripts/run_premarket_launchd.sh` |
| 模板 | `src/daytrader/reports/templates/premarket.md` |
| validator key | `premarket` |
| Obsidian | `Daily/{date}-premarket.md` |
| 日期键 | ET |
| Telegram | 有，但不可验证 |
| 语言 | 硬性中文（Chinese (Simplified)） |
| 日志 | `premarket-YYYYMMDD-HHMMSS.log`，`premarket.0600pt.out` |

常见失败签名：preflight 两类（见通用）；AI 失败为 traceback 结尾
`RuntimeError: AI call failed: claude -p exit=1: no stderr`；
运行时 IB 连接超时：`connectAsync` traceback 结尾 `TimeoutError`。

### intraday-4h-1

| 项 | 值 |
|---|---|
| 调度 | 周一至周五 07:00 PT |
| 入口 | `uv run daytrader reports run --type intraday-4h-1 --no-pdf` |
| wrapper | `scripts/run_intraday_4h_1_launchd.sh` |
| 模板 | `src/daytrader/reports/templates/intraday_4h.md` |
| validator key | `intraday-4h` |
| Obsidian | `Daily/{date}-0700PT-4H1.md` |
| 日期键 | ET |
| Telegram | 有，但不可验证 |
| 语言 | 弱要求（"mixed Chinese/English is acceptable"），低于阈值只 WARN |
| 日志 | `intraday-4h-1-YYYYMMDD-HHMMSS.log`，`intraday-4h-1.0700pt.out`；手动日志也可能叫 `4h1-*` |

常见失败签名：preflight 两类；
`Report FAILED: RuntimeError: AI call failed: claude -p exit=1: no stderr`。

### intraday-4h-2

| 项 | 值 |
|---|---|
| 调度 | 周一至周五 11:00 PT |
| 入口 | `uv run daytrader reports run --type intraday-4h-2 --no-pdf` |
| wrapper | `scripts/run_intraday_4h_2_launchd.sh` |
| 模板 | `src/daytrader/reports/templates/intraday_4h.md` |
| validator key | `intraday-4h` |
| Obsidian | `Daily/{date}-1100PT-4H2.md` |
| 日期键 | ET |
| Telegram | 有，但不可验证 |
| 语言 | 弱要求，低于阈值只 WARN |
| 日志 | `intraday-4h-2-YYYYMMDD-HHMMSS.log`，`intraday-4h-2.1100pt.out`；手动日志也可能叫 `4h2-*` |

常见失败签名：同 4h-1。

### eod

| 项 | 值 |
|---|---|
| 调度 | 周一至周五 14:00 PT |
| 入口 | `uv run daytrader reports run --type eod --no-pdf` |
| wrapper | `scripts/run_eod_launchd.sh` |
| 模板 | `src/daytrader/reports/templates/eod.md` |
| validator key | `eod` |
| Obsidian | `Daily/{date}-eod.md` |
| 日期键 | ET |
| Telegram | 有，但不可验证 |
| 语言 | 中文指令（按硬性检查，< 0.15 FAIL） |
| 日志 | `eod-YYYYMMDD-HHMMSS.log`，`eod.1400pt.out` |

常见失败签名：preflight 两类；traceback 结尾 `RuntimeError: AI call failed: claude -p exit=1: no stderr`；
特殊：`Report generated:` 之后 `OSError: [Errno 57] Socket is not connected`（`ib.disconnect()`），
exit=1 但文件已写好——state.db 行和文件都在就算成功。

### night

| 项 | 值 |
|---|---|
| 调度 | 周一至周五 19:00 PT |
| 入口 | `uv run daytrader reports run --type night --no-pdf` |
| wrapper | `scripts/run_night_launchd.sh` |
| 模板 | `src/daytrader/reports/templates/night_asia.md` |
| validator key | `night` |
| Obsidian | `Daily/{date}-1900PT-night.md` |
| 日期键 | PT |
| Telegram | 无（D-only 学习存档，设计如此） |
| 语言 | 硬性中文（"Output MUST be in Chinese"） |
| 日志 | `night-YYYYMMDD-HHMMSS.log`，`night.1900pt.out` |

常见失败签名：preflight 两类；`Report FAILED: RuntimeError: AI call failed: claude -p exit=1: no stderr`；
可能：`AI call failed: claude -p timeout after 300s`。

### asia

| 项 | 值 |
|---|---|
| 调度 | 周一至周五 23:00 PT |
| 入口 | `uv run daytrader reports run --type asia --no-pdf` |
| wrapper | `scripts/run_asia_launchd.sh` |
| 模板 | `src/daytrader/reports/templates/night_asia.md` |
| validator key | `asia` |
| Obsidian | `Daily/{date}-2300PT-asia.md` |
| 日期键 | PT |
| Telegram | 无（设计如此） |
| 语言 | 硬性中文 |
| 日志 | `asia-YYYYMMDD-HHMMSS.log`，`asia.2300pt.out` |

常见失败签名：同 night。

### weekly

| 项 | 值 |
|---|---|
| 调度 | 周日 14:00 PT |
| 入口 | `uv run daytrader weekly run --ai`（旧系统，yfinance，不需要 TWS） |
| wrapper | `scripts/run_weekly_launchd.sh`（仍被 TWS preflight 卡住） |
| 模板 | 内联在 `src/daytrader/premarket/weekly.py` 的 prompt |
| validator key | 无（required_sections SKIP） |
| Obsidian | `Weekly/weekly-{date}.md`，同时 `data/exports/weekly-{date}.md`；`{date}`＝运行当天 |
| 日期键 | 本地日期；不写 state.db |
| Telegram | 无 |
| 语言 | 中文 prompt，低于阈值只 WARN |
| 日志 | `weekly-YYYYMMDD-HHMMSS.log`，`weekly.sun1400pt.out`；结束行 `weekly run exit=` |

常见失败签名：preflight 两类；降级（仍 exit 0）：`Claude AI analysis failed (rc=1): ` +
`Weekly AI analysis unavailable; saving data report only`——脚本记为 WARN。

### 基准失败率（787 次运行，2026-05-02 → 2026-10-29 11:00）

| 类别 | 次数 | 占比 |
|---|---|---|
| TWS port unreachable（preflight） | 639 | 81% |
| TWS API handshake timeout（preflight） | 66 | 8% |
| SUCCESS | 43 | 5% |
| Claude CLI error（`claude -p exit=1: no stderr`） | 36 | 5% |
| weekly 降级成功（AI 失败，exit 0） | 1 | — |
| 运行时 IB connect timeout | 1 | — |
| 报告已写出后 `ib.disconnect()` OSError，exit 1 | 1 | — |

零出现：数据源致命错误、Claude 超时、validation 失败、Telegram 送达失败、幂等跳过、
preflight claude/config 失败。2026-10-12 起每次运行都是 port unreachable；
state.db 最后的 success 行是 2026-10-09（id 95-98）。

## 4. 已知盲区（本 skill 验证不了的）

| 盲区 | 代码位置 | 后果 |
|---|---|---|
| Telegram 推送结果被吞 | `src/daytrader/reports/delivery/telegram_pusher.py:110-111`（`except` → `PushResult(success=False)`）；orchestrator 丢弃返回值；`telegram_msg_ids` 从不写 | 送达只能肉眼确认 |
| `claude -p` stdout 被丢 | `src/daytrader/reports/core/ai_analyst.py:67-99`（非零退出只记 stderr） | 永远是 `claude -p exit=1: no stderr`，无法知道真实原因 |
| dry-run 是 stub | `src/daytrader/cli/reports.py`（`dry_run`，7 行固定 echo） | 不证明管线健康 |
| 没有数据源备用 | `src/daytrader/reports`、`src/daytrader/core` 无 yfinance/databento | TWS 不在就无报告 |
| preflight 失败 exit 0 | `scripts/run_*_launchd.sh`（`PREFLIGHT FAILED` 后 `exit 0`） | `launchctl list` 看不出失败 |
| 告警脚本 stderr 丢弃 | `scripts/run_*_launchd.sh`：`notify_preflight_failure.py ... 2>/dev/null` | 告警失败无痕迹，只能看有没有 `Telegram OK msg_id` |
| weekly 被 TWS 卡住 | `scripts/run_weekly_launchd.sh:51`（跑 TWS preflight，但 weekly 只用 yfinance） | TWS 不在时 weekly 白白失败 |
| validator 只做子串匹配 | `src/daytrader/reports/core/output_validator.py`（`_slot_matches`） | 不查点位量级、中文比例、亚盘/欧盘 |
| preflight 端口写死 | `scripts/preflight_check.py`（`--tws-port` 默认 7496，wrapper 不传；不读 `reports.ib.port`） | 切到 IB Gateway 4002 后 preflight 会误报 |
| futures_not_etf 是启发式 | `scripts/verify_report.py` | 只看 ES/NQ/GC 行及其标题下的 3-6 位数；WARN 时读原文 |

## 5. 路径说明

- 生产运行在 `/Users/tylersan/Projects/Day trading/.claude/worktrees/nice-varahamihira-9d6142/`；
  7 个 plist 都指向那里的 `scripts/run_*_launchd.sh`。
- `data/logs/`、`data/state.db`、`config/user.yaml`、`config/secrets.yaml` **只存在于生产 worktree**
  （gitignored）。在其他 worktree 跑 `verify_report.py` 不加 `--project-root` 会得到
  state_db_row SKIP + latest_run_log WARN。
- 验证生产：

```bash
uv run python scripts/verify_report.py --type asia --date 2026-10-09 \
  --project-root "/Users/tylersan/Projects/Day trading/.claude/worktrees/nice-varahamihira-9d6142"
```

- vault 在 worktree 之外（`~/Documents/DayTrader Vault`），所有 worktree 共用；
  `--vault` 可覆盖，默认读 `config/user.yaml` → `config/default.yaml` 的 `vault_path:`。
- 只读：不要改 `~/Library/LaunchAgents`，不要在生产 worktree 里改文件；补跑命令要在生产
  worktree 里执行（`cd` 到它）才会写对的 state.db。
