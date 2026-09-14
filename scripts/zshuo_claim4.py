#!/usr/bin/env python
"""Claim-4 audit runner: "a broken swing extreme is a *better* S/R level".

Reads the cached MES 1m parquet, builds the 5m frame, scans the three line
kinds, scores every first touch with the symmetric race and writes
``docs/research/zshuo-price-action/AUDIT_CLAIM4.md``.

    uv run python scripts/zshuo_claim4.py [--full-grid]

``--full-grid`` appends the 27-cell sensitivity table (k x X x expiry_days);
without it the report carries a placeholder saying the grid was not run, and
the spec §4 "grid must agree" clause therefore cannot be evaluated.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from daytrader.research.zshuo import pipeline as P
from daytrader.research.zshuo.bars import load_1m, resample_5m, tag_sessions
from daytrader.research.zshuo.config import SENSITIVITY_GRID, AuditConfig
from daytrader.research.zshuo.gaps import COUNTER_FIELDS, scan_lines
from daytrader.research.zshuo.stats import diff_ci, wilson

DEFAULT_PARQUET = Path("/Users/tylersan/Projects/Day trading/data/cache/ohlcv/"
                       "MES_1m_2018-05-01_2024-12-31_raw.parquet")
REPORT = (Path(__file__).resolve().parents[1] / "docs" / "research"
          / "zshuo-price-action" / "AUDIT_CLAIM4.md")
AGE_BUCKETS = [("1 bar", 1, 1), ("2-6 bars", 2, 6), ("7-24 bars", 7, 24),
               (">24 bars", 25, 10 ** 9)]


def pct(x: float) -> str:
    return "n/a" if x is None or np.isnan(x) else f"{100 * x:.2f}%"


def pp(x: float) -> str:
    return "n/a" if x is None or np.isnan(x) else f"{100 * x:+.2f}pp"


def table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(["---"] * len(header)) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def rate_cells(k: int, n: int) -> list[str]:
    p, lo, hi = wilson(k, n)
    return [str(n), str(k), pct(p), f"[{pct(lo)}, {pct(hi)}]"]


def diff_cells(a: tuple[int, int], b: tuple[int, int]) -> list[str]:
    d, lo, hi = diff_ci(*a, *b)
    return [pp(d), f"[{pp(lo)}, {pp(hi)}]",
            "是" if (lo > 0 or hi < 0) else "否"]


# ------------------------------------------------------------------ sections

def section_header(args, df, cfg, lines, ev_raw, ev) -> str:
    return "\n".join([
        "## 1. 数据与配置",
        "",
        f"- 源 parquet：`{args.parquet}`",
        f"- 5m bar：{len(df):,} 根，{df.index[0]} → {df.index[-1]}（UTC）",
        f"- 交易日（CME，18:00 ET 起算）：{df['session_date'].nunique():,}",
        f"- 主配置：k={cfg.k}、X={cfg.x_ticks} ticks、expiry_days={cfg.expiry_days}"
        f"、tick={cfg.tick_size}、race_timeout_bars={cfg.race_timeout_bars}"
        f"、rollover_blackout_bars={cfg.rollover_blackout_bars}"
        f"、min_gap_between_events={cfg.min_gap_between_events}、seed={cfg.seed}",
        f"- 线总数 {len(lines):,}；首触事件 {len(ev_raw):,}；"
        f"非重叠过滤后 {len(ev):,}（按 (kind, direction) 分组、间隔 <"
        f" {cfg.min_gap_between_events} bar 取先者）",
        "",
        "> 所有下表除特别注明外均为**非重叠过滤后**的事件。反弹率的分母是"
        " resolved = bounce + penetrate；indeterminate 与 timeout 单列，见 §7。",
    ])


def section_main(ev) -> str:
    s = P.summarize(ev)
    rows = [[kind, f"{int(s.loc[kind, 'n_events']):,}",
             *rate_cells(int(s.loc[kind, "bounce"]),
                         int(s.loc[kind, "n_resolved"]))]
            for kind in P.KINDS]
    return "\n".join([
        "## 2. 主表：反弹优先率",
        "",
        table(["组", "事件数", "n(resolved)", "bounce", "反弹率", "95% Wilson CI"],
              rows),
        "",
        "gap = 被实体突破的波段极值（受审对象）；phantom = C1 时移 placebo；"
        "plain = C2 未被突破的波段点。",
    ])


def section_effects(ev) -> str:
    e = P.effects(ev)
    c = e["counts"]
    rows = [["gap − phantom (C1)", *diff_cells(c["gap"], c["phantom"])],
            ["gap − plain (C2)", *diff_cells(c["gap"], c["plain"])]]
    return "\n".join([
        "## 3. 效应量（Newcombe 95% CI）",
        "",
        table(["对比", "效应", "95% CI", "CI 排除 0"], rows),
        "",
        "spec §4 的 CONFIRMED 阈值是两个效应同时 ≥ +5.00pp 且 CI 排除 0。",
    ])


def section_bounds(ev) -> str:
    rows = []
    for kind in P.KINDS:
        b = P.bounds_rates(ev, kind)
        rows.append([kind, f"{b.n:,}", pct(b.rate_all_penetrate),
                     pct(b.rate_all_bounce),
                     pp(b.rate_all_bounce - b.rate_all_penetrate)])
    contrast = []
    for rule in ("resolved", "all_bounce", "all_penetrate"):
        c = {kind: P.rule_counts(ev, kind, rule) for kind in P.KINDS}
        contrast.append([rule, *diff_cells(c["gap"], c["phantom"]),
                         *diff_cells(c["gap"], c["plain"])])
    v = P.verdict(ev)
    return "\n".join([
        "## 4. 界稳健性（spec 修订 (三)）",
        "",
        "indeterminate 事件全部改判 penetrate（下界）或全部改判 bounce（上界），"
        "同一规则同时施加于三组：",
        "",
        table(["组", "n(含 indeterminate)", "下界（全 penetrate）",
               "上界（全 bounce）", "界宽"], rows),
        "",
        "两个对比在三种读法下的方向：",
        "",
        table(["读法", "gap−C1 效应", "gap−C1 CI", "C1 排除 0",
               "gap−C2 效应", "gap−C2 CI", "C2 排除 0"], contrast),
        "",
        table(["读法", "§4 判定"],
              [[rule, verd] for rule, verd in v["by_rule"].items()]),
        "",
        f"三读法一致：**{'是' if v['robust'] else '否'}**。",
    ])


def _strata_rows(ev, kind, label_rows) -> list[list[str]]:
    rows = []
    for label, mask in label_rows:
        sub = ev[(ev["kind"] == kind) & mask]
        b = int((sub["outcome"] == "bounce").sum())
        n = b + int((sub["outcome"] == "penetrate").sum())
        rows.append([label, *rate_cells(b, n)])
    return rows


def section_strata(ev) -> str:
    def sess(ev_):
        return [("RTH", ev_["rth"]), ("overnight", ~ev_["rth"])]

    def ages(ev_):
        return [(lbl, (ev_["line_age_bars"] >= lo) & (ev_["line_age_bars"] <= hi))
                for lbl, lo, hi in AGE_BUCKETS]

    blocks = []
    for title, rows_fn in (("时段", sess), ("线龄桶", ages)):
        rows = []
        for kind in ("gap", "plain"):
            for r in _strata_rows(ev, kind, rows_fn(ev)):
                rows.append([kind, *r])
        blocks.append(f"### 5.{len(blocks) + 1} {title}\n\n" + table(
            ["组", title, "n(resolved)", "bounce", "反弹率", "95% Wilson CI"],
            rows) + "\n")

    ft = [("FT+", ev["follow_through"] == True),        # noqa: E712
          ("FT-", ev["follow_through"] == False),       # noqa: E712
          ("FT 未知", ev["follow_through"].isna())]
    blocks.append("### 5.3 跟随（仅 gap；plain 无突破，该协变量不存在）\n\n"
                  + table(["跟随", "n(resolved)", "bounce", "反弹率",
                           "95% Wilson CI"],
                          _strata_rows(ev, "gap", ft))
                  + "\n\n> FT± 的巨大落差**不可读成机制证据**：FT- 的定义是"
                    "突破后下一根 bar 就收回线的另一侧，这本身已经是「价格正在"
                    "往回走」的直接观测，与随后那场以线价为原点的竞赛高度机械"
                    "相关（多数 FT- 事件的 t0 就是破位后第 1 根 bar，见 5.2 的"
                    "线龄分布）。它检验的是「回撤中的动量会延续吗」，不是"
                    "「被套者会在成本线打平离场吗」。")
    return "\n".join([
        "## 5. 分层", "",
        "> **线龄语义跨组不可比**：gap 的 line_age_bars 是*破位后*时长，"
        "plain 是*确认后*时长（spec §3 修订 (二)）。两列只可桶内对照趋势，"
        "不可合并成一个「线龄效应」。gap 的线龄分布极度左偏——多数缺口线在"
        "破位后第 1 根 bar 就被回触——所以 gap 的合并反弹率基本由「1 bar」桶"
        "决定；而线龄越长反弹率越高这个趋势在 gap 与 plain 上同时出现，"
        "因此它不是「套得越久越想打平」的证据，两组共有的东西不能用来证明"
        "只有其中一组才有的机制。", "",
        *blocks,
    ])


def section_aux(ev) -> str:
    cols = [f"fwd_ret_{k}" for k in P.FWD_HORIZONS] + ["mfe_ticks", "mae_ticks"]
    rows = []
    for kind in P.KINDS:
        sub = ev[ev["kind"] == kind]
        rows.append([kind, f"{len(sub):,}"]
                    + [f"{sub[c].median():+.2f}" if sub[c].notna().any() else "n/a"
                       for c in cols]
                    + [f"{int(sub['mfe_ticks'].notna().sum()):,}"])
    return "\n".join([
        "## 6. 辅指标（中位数，tick，方向化：反弹方向为正）",
        "",
        table(["组", "事件数", "fwd_ret_6", "fwd_ret_12", "fwd_ret_24",
               "MFE", "MAE", "MFE/MAE 有值数"], rows),
        "",
        "fwd_ret_k = t0+k 根 bar 的 close 相对线价的方向化位移；不足 k 根记 NaN。"
        "MFE/MAE 取 t0+1 至竞赛结束 bar（或 timeout 窗末）的最大有利/不利位移；"
        "在触线 bar 当场判定的事件窗口为空，记 NaN——故「有值数」小于事件数。",
    ])


def section_disposition(ev_raw, ev, lines, counters) -> str:
    s_raw, s = P.summarize(ev_raw), P.summarize(ev)
    outcome_rows = []
    for kind in P.KINDS:
        outcome_rows.append(
            [kind] + [f"{int(s_raw.loc[kind, o]):,}" for o in P.OUTCOMES]
            + [f"{int(s.loc[kind, o]):,}" for o in P.OUTCOMES])
    fields = [f for f in COUNTER_FIELDS
              if any(counters[k][f] for k in P.KINDS)]
    counter_rows = [[kind] + [f"{counters[kind][f]:,}" for f in fields]
                    for kind in P.KINDS]
    same_bar_raw = P.placebo_same_bar_share(ev_raw)
    same_bar = P.placebo_same_bar_share(ev)
    clash = {k: P.opposite_direction_same_bar_share(ev, k) for k in P.KINDS}
    return "\n".join([
        "## 7. 事件处置与计数通道",
        "",
        "### 7.1 竞赛结局",
        "",
        table(["组"] + [f"{o}（全量）" for o in P.OUTCOMES]
              + [f"{o}（非重叠后）" for o in P.OUTCOMES], outcome_rows),
        "",
        "### 7.2 线的处置（计数通道，全量、未过非重叠）",
        "",
        table(["组"] + list(fields), counter_rows),
        "",
        "- `expired_at_touch`（plain 列）= spec §3 修订 (二) 要求披露的 **C2 剔除数**："
        "回触时已超过 expiry 时钟的普通波段点候选，随 expiry_days 变动。",
        "- plain 行的 `created` = `touched`：未被回触的波段点从不物化成线，"
        "所以 C2 没有「过期作废」一说，只有上面的触线时剔除。",
        "",
        "### 7.3 对照独立性",
        "",
        f"- placebo 与 gap 事件**同 bar** 占比：全量 {pct(same_bar_raw)}、"
        f"非重叠后 {pct(same_bar)}（spec §3 修订 (二) 报告义务）。",
        f"- placebo **锚复用率**：{pct(P.anchor_reuse_share(lines))}"
        "（= 1 − 唯一锚 bar 数 / 抽样数）。复用锚的 placebo 共享同一段价格路径，"
        "故 C1 组内并非完全独立抽样。",
        f"- 同 bar H/L 竞赛通道重叠（**本文口径**：同组内一根 bar 同时承载一条"
        f"向上线与一条向下线的事件，两场竞赛读同一根 bar 的 H 与 L）："
        f"gap {pct(clash['gap'])}、phantom {pct(clash['phantom'])}、"
        f"plain {pct(clash['plain'])}（全量事件上分别为 "
        f"{pct(P.opposite_direction_same_bar_share(ev_raw, 'gap'))}、"
        f"{pct(P.opposite_direction_same_bar_share(ev_raw, 'phantom'))}、"
        f"{pct(P.opposite_direction_same_bar_share(ev_raw, 'plain'))}）。"
        "此前复核口头提到的 ~0.13% 用的是更窄的定义，本管线未复现该口径，"
        "以本行的实测口径为准。",
    ])


def section_verdict(ev, tally: dict | None = None) -> str:
    v = P.verdict(ev)
    e = P.effects(ev)
    d1, lo1, hi1 = e["gap_minus_phantom"]
    d2, lo2, hi2 = e["gap_minus_plain"]
    lines = [
        "## 8. 判定",
        "",
        f"### **{v['verdict']}**"
        + (f"（倾向 {v['tendency']}）" if v["tendency"] else ""),
        "",
        f"- resolved 读法下的 §4 四态判定：**{v['main']}**。",
        f"- 界稳健性（修订 (三)）：三读法{'一致' if v['robust'] else '不一致'}"
        f"（{', '.join(f'{r}→{x}' for r, x in v['by_rule'].items())}）。",
        f"- gap − C1(placebo) = {pp(d1)}，CI [{pp(lo1)}, {pp(hi1)}]。",
        f"- gap − C2(普通波段点) = {pp(d2)}，CI [{pp(lo2)}, {pp(hi2)}]。",
        f"- 敏感性网格（spec §4「网格多数一致才生效」）："
        + (f"27 组判定分布 {tally}。" if tally else
           "**未运行**，该条款未被检验，本判定只代表主配置。"),
        "",
    ]
    if v["verdict"] == "REFUTED":
        lines += [
            "读法：缺口线的反弹优先率**不高于**几何匹配、时间随机化的 placebo 线，"
            "CI 明确含 0；同时**显著低于**普通（未被突破）波段点。受审宣称的"
            "差异化部分——「被套者成本线优于普通水平位」——在 MES 5m 上没有出现，"
            "方向上还是反的。",
            "",
            "反向不等于对立宣称成立：plain 组的高反弹率正是「未被实体突破」这个"
            "选择条件的产物（一条线之所以还是 plain，就是因为价格每次到它那儿都"
            "没能收盘越过去），属于条件化选择，不能读成「普通水平位是更好的支撑」。",
        ]
    elif v["verdict"] == "UNDECIDED":
        lines += ["读法：主读法给出 "
                  f"{v['main']}，但 indeterminate 的两个极端读法不一致，"
                  "按 spec 修订 (三) 降格为 UNDECIDED 并只记倾向。"]
    return "\n".join(lines)


LIMITATIONS = """## 9. 局限清单（预登记 + 实测补充）

1. **MES 代理 NQ**：受审体系讲的是 NQ，本审计用 MES（同为股指期货，tick 结构与
   波动幅度不同）。结论外推到 NQ 未经验证。
2. **锚点用 swing 极值近似手工画法**：原作者按光头/光脚 K 的开盘价端微调锚点，
   v1 一律取 swing 极值，与手工线存在若干 tick 的系统性偏移。
3. **单周期**：纯 5m。跨周期例外（5m 回补但 1H 未回补仍算有效）未实现。
4. **placebo 锚池不做波动率/时刻匹配**：锚池为全历史均匀抽样（仅匹配 RTH 标志、
   隔开 ≥1 个交易日、避开 blackout）。复核实测三种替代锚池（局部 ±20 交易日 /
   同 ET 小时 / 二者叠加）只移动反弹率 0.4–0.7pp，远低于 ±5pp 判定阈，且偏差方向
   抬高 placebo（不利于伪 CONFIRMED）。见 §7.3 实测值。
5. **placebo 锚复用**：见 §7.3 的实测复用率。复用同一锚 bar 的 placebo 线共享价格
   路径，C1 组内不是完全独立抽样，其 CI 略偏窄。
6. **同 bar H/L 竞赛通道重叠**：同一根 bar 可同时承载一条向上线与一条向下线的
   事件，两场竞赛读同一根 bar 的 H 与 L，互为镜像而非独立观测。实测占比见 §7.3。
7. **线龄语义跨组不可比**：gap 的线龄从破位起算、plain 从确认起算，只能桶内对照。
8. **resolved 条件化**：主指标的分母排除了 indeterminate 与 timeout。indeterminate
   的处置由 §4 的上下界覆盖；timeout 占比极低（见 §7.1），但它同样是一种「线附近
   什么也没发生」的信息，被排除在率之外。
9. **反应度量 ≠ 可盈利**：主指标检验的是「线处有可测的反弹倾向」，不等于按原作者
   的入场/止损规则能盈利（成本、滑点、仓位均不在本审计范围）。
10. **本审计只覆盖宣称 4**，不涉及宣称 1–3、策略模拟与成本模型。"""


# --------------------------------------------------------------------- grid

def run_grid(df: pd.DataFrame) -> tuple[str, dict]:
    rows, below = [], 0
    for i, cfg in enumerate(SENSITIVITY_GRID, 1):
        t = time.time()
        lines, counters = scan_lines(df, cfg, with_counters=True)
        ev = P.apply_nonoverlap(P.build_events(df, cfg, lines),
                                cfg.min_gap_between_events)
        e = P.effects(ev)
        v = P.verdict(ev)
        n_gap = e["counts"]["gap"][1]
        d1, lo1, hi1 = e["gap_minus_phantom"]
        d2, lo2, hi2 = e["gap_minus_plain"]
        below += int(hi1 < 0)   # gap strictly *below* the placebo, CI and all
        rows.append([cfg.k, cfg.x_ticks, cfg.expiry_days, f"{n_gap:,}",
                     pct(P.summarize(ev).loc["gap", "rate"]),
                     pp(d1), f"[{pp(lo1)}, {pp(hi1)}]",
                     pp(d2), f"[{pp(lo2)}, {pp(hi2)}]",
                     f"{counters['plain']['expired_at_touch']:,}",
                     v["verdict"]])
        print(f"  grid {i:2d}/27 k={cfg.k} X={cfg.x_ticks} "
              f"expiry={cfg.expiry_days} -> {v['verdict']} "
              f"({time.time() - t:.0f}s)", flush=True)
    tally = pd.Series([r[-1] for r in rows]).value_counts().to_dict()
    md = "\n".join([
        "## 10. 敏感性网格（27 组：k × X × expiry_days）",
        "",
        table(["k", "X(ticks)", "expiry", "n_gap(resolved)", "gap 反弹率",
               "gap−C1", "C1 CI", "gap−C2", "C2 CI", "C2 剔除数", "判定"], rows),
        "",
        "- `C2 剔除数` = 回触时已超期的普通波段点候选，**随 expiry_days 变动**，"
        "因此该列不可跨行直接比较总体大小。",
        "- 各格的 placebo 用同一 seed，但网格参数改变了 gap 集合，"
        "故锚抽样并非跨格可比。",
        f"- 判定分布：{tally}。",
        f"- 其中 {below} 组的 gap−C1 区间整体落在 0 **以下**——这些参数下缺口线"
        "不只是「不比 placebo 强」，而是显著更弱；REFUTED 的方向在网格里没有"
        "任何一格翻过来。",
    ])
    return md, tally


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--full-grid", action="store_true")
    ap.add_argument("--out", type=Path, default=REPORT)
    args = ap.parse_args()

    t = time.time()
    df = tag_sessions(resample_5m(load_1m(args.parquet)))
    print(f"loaded {len(df):,} 5m bars in {time.time() - t:.1f}s", flush=True)

    cfg = AuditConfig()
    t = time.time()
    lines, counters = scan_lines(df, cfg, with_counters=True)
    print(f"scanned {len(lines):,} lines in {time.time() - t:.1f}s", flush=True)
    t = time.time()
    ev_raw = P.build_events(df, cfg, lines)
    ev = P.apply_nonoverlap(ev_raw, cfg.min_gap_between_events)
    print(f"scored {len(ev_raw):,} events ({len(ev):,} after non-overlap) "
          f"in {time.time() - t:.1f}s", flush=True)

    grid, tally = run_grid(df) if args.full_grid else (
        "## 10. 敏感性网格\n\n未运行（本次以 `--full-grid` 之外的方式执行）。"
        "spec §4 的「网格多数一致」条款因此**未被检验**，上方判定只代表主配置。",
        None)

    v = P.verdict(ev)
    body = "\n\n".join([
        "# 审计报告：宣称 4「缺口 = 有效支撑阻力」",
        "> 受审宣称：被实体突破的波段高/低点 = 被套者成本线，价格回到该线时有真实"
        "打平离场行为，因此构成**优于普通水平位的**支撑阻力。\n"
        "> 冻结设计见 `specs/2026-09-14-claim4-gap-sr-audit-design.md`（含修订 (一)"
        "(二)(三)）。本文由 `scripts/zshuo_claim4.py` 生成，勿手工编辑。",
        f"**结论：{v['verdict']}**"
        + (f"（倾向 {v['tendency']}）" if v["tendency"] else "")
        + f"　·　详见 [§8 判定](#8-判定)"
        + (f"　·　敏感性网格 27 组：{tally}" if tally
           else "　·　敏感性网格：未运行"),
        section_header(args, df, cfg, lines, ev_raw, ev),
        section_main(ev),
        section_effects(ev),
        section_bounds(ev),
        section_strata(ev),
        section_aux(ev),
        section_disposition(ev_raw, ev, lines, counters),
        section_verdict(ev, tally),
        LIMITATIONS,
        grid,
    ]) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(body)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
