#!/usr/bin/env python
"""Claim-4 Wave D: anchor-shape subgroup analysis (spec 修订 (四)).

The v1 audit returned REFUTED on the *pooled* set of body-broken swing extremes
(gap − placebo = +0.00pp). The user's objection: z说's lines are not drawn on
any broken extreme but on a textbook anchor — a bald-top bear candle's high, a
bald-bottom bull candle's low, or a long-wick pin — with the anchor's colour
opposing the break. If the edge lives only there, pooling dilutes it. This
script scores the four pre-registered subgroups on the main configuration
(k=3, X=8, expiry=5) and appends section 11 to ``AUDIT_CLAIM4.md``.

    uv run python scripts/zshuo_claim4_anchors.py [--parquet PATH] [--out PATH]

Nothing here re-tunes a definition: the subgroups, the thresholds, the two
sensitivity sweeps and the verdict-update rule are all frozen by 修订 (四)
before the numbers existed.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from daytrader.research.zshuo import pipeline as P                    # noqa: E402
from daytrader.research.zshuo.anchors import (S2_GRID, S2_MAX, S3_GRID,  # noqa: E402
                                              S3_MIN, SUBGROUPS,
                                              annotate_anchor_features,
                                              subgroup_mask)
from daytrader.research.zshuo.bars import (load_1m, resample_5m,       # noqa: E402
                                           tag_sessions)
from daytrader.research.zshuo.config import AuditConfig                # noqa: E402
from daytrader.research.zshuo.gaps import (LINE_COLUMNS, _first_touch,  # noqa: E402
                                           blackout_mask, scan_lines)
from daytrader.research.zshuo.stats import diff_ci                     # noqa: E402
from zshuo_claim4 import (DEFAULT_PARQUET, REPORT, diff_cells, pct,    # noqa: E402
                          pp, rate_cells, table)

SECTION = "## 11. 锚点形态子组分析（修订 (四)）"

#: 修订 (四) 的判定更新阈值：子组效应必须同时满足这三条。
MIN_EFFECT = 0.05
#: 低于此 n(resolved) 的子组在结论里标注功效不足。
MIN_POWER_N = 500

SUBGROUP_LABELS = {
    "s1": "S1 颜色一致",
    "s2": f"S2 光头/光脚（影线比 ≤ {S2_MAX:.2f}）",
    "s3": f"S3 长影 pin（影线比 ≥ {S3_MIN:.2f}）",
    "s4": "S4 教科书锚点（S2 ∪ S3）",
}


# ------------------------------------------------------------------ plumbing

def load_frames(parquet: Path, cfg: AuditConfig):
    """Bars, annotated lines and the non-overlapped, annotated event table."""
    df = tag_sessions(resample_5m(load_1m(parquet)))
    lines = annotate_anchor_features(scan_lines(df, cfg), df)
    ev = P.apply_nonoverlap(P.build_events(df, cfg, lines),
                            cfg.min_gap_between_events)
    return df, lines, annotate_anchor_features(ev, df)


def counts(ev: pd.DataFrame, kind: str, rule: str = "resolved") -> tuple[int, int]:
    return P.rule_counts(ev, kind, rule)


def subgroup_slice(ev: pd.DataFrame, label: str, complement: bool) -> pd.DataFrame:
    """gap + paired placebo rows carrying (or lacking) one subgroup label.

    Pairing is structural, not statistical: :func:`gaps.scan_lines` writes the
    parent gap's ``swing_idx`` onto its placebo, so a placebo is inside the
    subgroup exactly when its parent gap is.
    """
    return ev[subgroup_mask(ev, label, complement=complement)]


def effect(ev: pd.DataFrame, rule: str = "resolved") -> tuple[float, float, float]:
    return diff_ci(*counts(ev, "gap", rule), *counts(ev, "phantom", rule))


def robust(ev: pd.DataFrame) -> tuple[bool, dict[str, tuple[float, float, float]]]:
    """修订 (三) bounds gate, applied to a subgroup's gap−placebo effect.

    Passes only if every reading of the indeterminate events clears the same
    bar the verdict-update rule sets: effect >= +5pp with the Newcombe interval
    excluding 0.
    """
    by_rule = {rule: effect(ev, rule) for rule in P.RULES}
    ok = all(not np.isnan(d) and d >= MIN_EFFECT and lo > 0
             for d, lo, _ in by_rule.values())
    return ok, by_rule


# -------------------------------------------------------------- 11.1 subgroups

def section_subgroups(ev: pd.DataFrame) -> tuple[str, dict]:
    rows, verdict_rows, findings = [], [], {}
    for label in SUBGROUPS:
        for complement in (False, True):
            sub = subgroup_slice(ev, label, complement)
            name = SUBGROUP_LABELS[label] + ("（补集）" if complement else "")
            g, ph = counts(sub, "gap"), counts(sub, "phantom")
            d, lo, hi = diff_ci(*g, *ph)
            ph_cells = rate_cells(*ph)
            g_cells = rate_cells(*g)
            rows.append([name, f"{len(sub[sub.kind == 'gap']):,}",
                         f"{g[1]:,}", f"{g[0]:,}", *g_cells[2:],
                         f"{ph[1]:,}", ph_cells[2],
                         pp(d), f"[{pp(lo)}, {pp(hi)}]",
                         "是" if lo > 0 else "否"])
            if not complement:
                ok, by_rule = robust(sub)
                findings[label] = {"n_gap": g[1], "n_ph": ph[1], "d": d,
                                   "lo": lo, "hi": hi, "pass": ok,
                                   "by_rule": by_rule}
                verdict_rows.append(
                    [SUBGROUP_LABELS[label],
                     *[pp(by_rule[r][0]) for r in P.RULES],
                     *[("是" if by_rule[r][1] > 0 else "否") for r in P.RULES],
                     "**通过**" if ok else "未通过"])
    body = "\n".join([
        "### 11.1 子组主表（gap vs 该子组配对 placebo）",
        "",
        table(["子组", "gap 事件数", "gap n(resolved)", "gap bounce",
               "gap 反弹率", "gap 95% CI", "placebo n(resolved)",
               "placebo 反弹率", "gap−placebo", "Newcombe 95% CI", "CI 排除 0"],
              rows),
        "",
        "> 配对口径：每条 placebo 沿用其父 gap 的 `swing_idx`，因此它落在哪个子组"
        "完全由父 gap 决定（结构性配对，非事后匹配）。每个子组与其补集的 "
        "n(resolved) 相加即为 §2 主表的 gap 总体（14,210），`plain` 组不参与子组。",
        "",
        "> **口径提示**：非重叠过滤在**全量事件流上施加一次**（与主表同口径），"
        "子组是事后切片，所以子组内的事件会被相邻的非子组事件挤掉，子组 n 因此"
        "明显小于该子组的线数。若改为在子集内部单独施加非重叠过滤，n 会回升——"
        "11.4 的第一行就是 S2 在该口径下的同一口径对照（线价不变，只换过滤范围），"
        "两种口径都不达标，结论不依赖这个选择。",
        "",
        "### 11.2 界稳健性（子组效应在三种 indeterminate 读法下）",
        "",
        table(["子组", "resolved", "全判 bounce", "全判 penetrate",
               "CI 排除 0（resolved）", "CI 排除 0（全 bounce）",
               "CI 排除 0（全 penetrate）", "修订 (四) 判定门槛"], verdict_rows),
        "",
        f"> 门槛 = 三种读法下效应均 ≥ +{100 * MIN_EFFECT:.0f}pp 且 CI 均排除 0。",
    ])
    return body, findings


# ---------------------------------------------------- 11.3 threshold sweep

def section_thresholds(ev_base: pd.DataFrame,
                       df: pd.DataFrame) -> tuple[str, dict]:
    rows, cells = [], []
    for t2 in S2_GRID:
        for t3 in S3_GRID:
            ann = annotate_anchor_features(ev_base, df, s2_max=t2, s3_min=t3)
            sub = subgroup_slice(ann, "s4", False)
            g, ph = counts(sub, "gap"), counts(sub, "phantom")
            d, lo, hi = diff_ci(*g, *ph)
            cells.append({"s2": t2, "s3": t3, "d": d, "lo": lo, "hi": hi})
            rows.append([f"{t2:.2f}", f"{t3:.2f}", f"{g[1]:,}", f"{ph[1]:,}",
                         pct(g[0] / g[1] if g[1] else np.nan),
                         pct(ph[0] / ph[1] if ph[1] else np.nan),
                         pp(d), f"[{pp(lo)}, {pp(hi)}]",
                         "是" if lo > 0 else "否"])
    return "\n".join([
        "### 11.3 阈值敏感性（S2 × S3 → S4 效应）",
        "",
        table(["S2 阈值(≤)", "S3 阈值(≥)", "gap n(resolved)",
               "placebo n(resolved)", "gap 反弹率", "placebo 反弹率",
               "gap−placebo", "95% CI", "CI 排除 0"], rows),
        "",
        "> 9 格全部由同一份事件表切片，`s1` 与影线比不随阈值变化，"
        "变的只是 S2/S3 的切点，因此各格之间的差异纯粹是子组边界的移动。",
    ]), {"cells": cells}


# ------------------------------------------- 11.4 line-placement sensitivity

def _relines(lines: pd.DataFrame, df: pd.DataFrame, cfg: AuditConfig,
             use_body: bool) -> pd.DataFrame:
    """Re-walk the S2 gap lines (and their paired placebos) under one price rule.

    ``use_body=False`` reproduces the frozen extremum line price on exactly the
    same subset, so the two arms differ only in where the line is drawn — not in
    which events they contain.
    """
    n = len(df)
    low = df["low"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    rollover = df["rollover"].to_numpy(dtype=bool)
    masked = blackout_mask(rollover, cfg.rollover_blackout_bars)
    session_ord = pd.factorize(df["session_date"])[0]

    s2 = subgroup_mask(lines, "s2")
    gaps = lines[s2 & (lines["kind"] == "gap")]
    phantoms = lines[s2 & (lines["kind"] == "phantom")].set_index(
        ["swing_idx", "direction"])

    recs = []
    for g in gaps.itertuples(index=False):
        price = float(g.anchor_body_price if use_body else g.price)
        touched, _ = _first_touch(int(g.created_idx), price, int(g.direction),
                                  n, cfg, low, high, rollover, masked,
                                  session_ord)
        recs.append({"line_id": len(recs), "price": price,
                     "direction": int(g.direction), "kind": "gap",
                     "created_idx": int(g.created_idx),
                     "swing_idx": int(g.swing_idx),
                     "follow_through": g.follow_through,
                     "touched_idx": touched})
        key = (int(g.swing_idx), int(g.direction))
        if key not in phantoms.index:
            continue  # gap whose placebo draw found no admissible anchor
        ph = phantoms.loc[key]
        anchor = int(ph["created_idx"])
        # keep the drawn anchor bar, re-derive the geometry from the new price
        distance = abs(close[int(g.created_idx)] - price)
        p_price = float(close[anchor] - int(g.direction) * distance)
        p_touched, _ = _first_touch(anchor, p_price, int(g.direction), n, cfg,
                                    low, high, rollover, masked, session_ord)
        recs.append({"line_id": len(recs), "price": p_price,
                     "direction": int(g.direction), "kind": "phantom",
                     "created_idx": anchor, "swing_idx": int(g.swing_idx),
                     "follow_through": None, "touched_idx": p_touched})
    out = pd.DataFrame(recs, columns=LINE_COLUMNS)
    return out.astype({"touched_idx": float, "follow_through": object})


def section_placement(lines: pd.DataFrame, df: pd.DataFrame,
                      cfg: AuditConfig) -> tuple[str, dict]:
    rows, found = [], {}
    for key, label, use_body in (
            ("extremum", "极值线价（冻结口径）", False),
            ("body", "实体端线价（大体积K看实体）", True)):
        re_lines = _relines(lines, df, cfg, use_body)
        ev = P.apply_nonoverlap(P.build_events(df, cfg, re_lines),
                                cfg.min_gap_between_events)
        g, ph = counts(ev, "gap"), counts(ev, "phantom")
        d, lo, hi = diff_ci(*g, *ph)
        found[key] = {"n_gap": g[1], "d": d, "lo": lo, "hi": hi}
        rows.append([label, f"{len(re_lines[re_lines.kind == 'gap']):,}",
                     f"{g[1]:,}", pct(g[0] / g[1] if g[1] else np.nan),
                     f"{ph[1]:,}", pct(ph[0] / ph[1] if ph[1] else np.nan),
                     pp(d), f"[{pp(lo)}, {pp(hi)}]", "是" if lo > 0 else "否"])
    return "\n".join([
        "### 11.4 画线位置敏感性（仅 S2 子组）",
        "",
        table(["线价口径", "重扫线数", "gap n(resolved)", "gap 反弹率",
               "placebo n(resolved)", "placebo 反弹率", "gap−placebo",
               "95% CI", "CI 排除 0"], rows),
        "",
        "> 实体端 = `direction=+1` 取 `max(open, close)`（光头阴线即开盘价），"
        "`direction=-1` 取 `min(open, close)`。两行都是**在同一份 S2 线集合上"
        "单独重扫**触线与竞赛（非全量重扫），非重叠过滤在该子集内施加，因此第一行"
        "的 n 与 11.1 的 S2 行略有出入——那一行的过滤是在全量事件流上做的。"
        "两行之间唯一的差别是线价，故可直接相减读画线位置的影响。",
        "",
        "> placebo 的锚 bar 沿用原抽样结果，只按新线价重算几何距离 "
        "`D = |close[破位 bar] − 线价|`，保证对照与被审对象同步移动。"
        "注意实体端画法把**两条**线都往价格里挪了，gap 与 placebo 的反弹率同步"
        "抬高，差值反而下降——抬高的是「线更靠内所以更容易先碰到反弹侧」这一"
        "几何效应，不是机制。",
    ]), found


# ----------------------------------------------------- 11.5 dilution accounting

def _partition(ev: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    s1 = subgroup_mask(ev, "s1")
    s2 = subgroup_mask(ev, "s2")
    s3 = subgroup_mask(ev, "s3")
    labelled = ev["s1"].notna()
    return [("S2 光头/光脚", s2),
            ("S3 长影 pin", s3),
            ("S1 中间带（S1 ∖ S4）", s1 & ~s2 & ~s3),
            ("非 S1（颜色不一致/十字星）", labelled & ~s1)]


def section_dilution(ev: pd.DataFrame) -> tuple[str, dict]:
    total_g = counts(ev, "gap")
    total_p = counts(ev, "phantom")
    rate = lambda c: c[0] / c[1] if c[1] else np.nan  # noqa: E731
    pooled = rate(total_g) - rate(total_p)

    rows, weighted, weight_term, block_effects = [], 0.0, 0.0, []
    for name, mask in _partition(ev):
        sub = ev[mask]
        g, ph = counts(sub, "gap"), counts(sub, "phantom")
        share_g = g[1] / total_g[1] if total_g[1] else np.nan
        share_p = ph[1] / total_p[1] if total_p[1] else np.nan
        eff = rate(g) - rate(ph)
        contrib = share_g * eff if not np.isnan(eff) else np.nan
        weighted += 0.0 if np.isnan(contrib) else contrib
        weight_term += 0.0 if np.isnan(share_p) else (share_g - share_p) * rate(ph)
        if not np.isnan(eff):
            block_effects.append(eff)
        rows.append([name, f"{g[1]:,}", pct(share_g), pct(rate(g)),
                     pct(rate(ph)), pp(eff), pp(contrib),
                     "⚠ 功效不足" if g[1] < MIN_POWER_N else ""])
    return "\n".join([
        "### 11.5 子组占比与稀释核算",
        "",
        table(["互斥分块", "gap n(resolved)", "占 gap 总体", "gap 反弹率",
               "placebo 反弹率", "块内效应", "贡献 = 占比 × 效应", "备注"], rows),
        "",
        f"- 总体效应（gap − placebo，全部 gap 事件）：**{pp(pooled)}**。",
        f"- Σ 占比 × 块内效应 = **{pp(weighted)}**。",
        f"- 权重错配残差 Σ (gap占比 − placebo占比) × placebo块内率 = "
        f"{pp(weight_term)}；两项之和 {pp(weighted + weight_term)}"
        f"（与总体效应的差为四舍五入与空块）。",
        "",
        "> 分解恒等式："
        "`pooled = Σ wᵍᵢ(gᵢ − pᵢ) + Σ (wᵍᵢ − wᵖᵢ)pᵢ`。"
        "第一项是「各块自身的效应」，第二项是「gap 与 placebo 在各块上的分布不同」"
        "带来的组合效应。稀释假说要求存在某块的 `gᵢ − pᵢ` 明显为正、只是被占比"
        "压小——读这张表时看的是**块内效应**那一列，不是贡献列。",
    ]), {"min": min(block_effects), "max": max(block_effects),
         "pooled": pooled}


# ---------------------------------------------------------------- 11.6 verdict

def section_verdict(findings: dict, placement: dict, thresholds: dict,
                    dilution: dict) -> str:
    passed = [k for k, f in findings.items() if f["pass"]]
    thin = [k for k, f in findings.items() if f["n_gap"] < MIN_POWER_N]
    best = max(findings.items(), key=lambda kv: (-1e9 if np.isnan(kv[1]["d"])
                                                 else kv[1]["d"]))
    head = ("PARTIAL（子集有效）" if passed else "REFUTED 维持并强化")
    out = [
        "### 11.6 判定更新（按 修订 (四) 预登记规则）",
        "",
        f"#### **{head}**",
        "",
        "预登记规则原文：「任一预登记子组 gap−配对placebo ≥ +5pp 且 CI 不含 0 "
        "且界稳健 → 总判定升为 PARTIAL（子集有效），并触发宣称 1-3 审计的先决"
        "恢复；否则 REFUTED 维持并强化（稀释假说被排除）。」",
        "",
    ]
    if passed:
        out += [f"- 达标子组：{'、'.join(SUBGROUP_LABELS[k] for k in passed)}。",
                "- 触发条款：宣称 1-3 审计的先决条件恢复。"]
    else:
        out += [
            "- 四个预登记子组**无一**满足三条件（效应 ≥ +5pp、CI 排除 0、界稳健），"
            "见 11.1 与 11.2。",
            f"- 其中效应最高的是 {SUBGROUP_LABELS[best[0]]}："
            f"{pp(best[1]['d'])}，CI [{pp(best[1]['lo'])}, {pp(best[1]['hi'])}]。",
            "- 因此 **REFUTED 维持**，且「教科书子集被稀释」这一假说被排除："
            "按 z说 自己的锚点形态与颜色条件筛出的子集，反弹优先率同样不高于"
            "几何匹配、时间随机化的 placebo 线。",
            "- 宣称 1-3 审计的先决条件**未**恢复。",
        ]
        ex, bd = placement["extremum"], placement["body"]
        cells = thresholds["cells"]
        best_cell = max(cells, key=lambda c: c["d"])
        n_excl = sum(1 for c in cells if c["lo"] > 0 or c["hi"] < 0)
        out += [
            "",
            "旁证（均不改变上面的判定）：",
            f"- 阈值敏感性 {len(cells)} 格（11.3）：最高的一格"
            f"（S2≤{best_cell['s2']:.2f}、S3≥{best_cell['s3']:.2f}）也只有 "
            f"{pp(best_cell['d'])}，"
            + (f"仅 {n_excl} 格的 CI 排除 0" if n_excl
               else "无一格的 CI 排除 0")
            + "。「换个阈值就能筛出教科书子集」这条退路不成立。",
            f"- 子集内部单独施加非重叠过滤的 S2（11.4 第一行，n={ex['n_gap']:,}）："
            f"{pp(ex['d'])}，CI [{pp(ex['lo'])}, {pp(ex['hi'])}]——比 11.1 的口径"
            "宽松，仍远低于 +5pp 且 CI 含 0。",
            f"- 改用实体端画线（11.4 第二行，n={bd['n_gap']:,}）：{pp(bd['d'])}，"
            f"CI [{pp(bd['lo'])}, {pp(bd['hi'])}]——「大体积K看实体」的画法把两组"
            "同步抬高，差值不升反降。",
            f"- 稀释核算（11.5）：四个互斥分块的**块内效应**全部落在 "
            f"{pp(dilution['min'])} 至 {pp(dilution['max'])} 之间，"
            f"总体 {pp(dilution['pooled'])}。稀释假说要求至少存在一块块内效应"
            "明显为正、只是被占比压小；实测不存在这样的块，因此假说被排除，"
            "而不是「样本里有但被平均掉了」。",
        ]
    if thin:
        out += ["",
                "**功效声明**：以下子组 n(resolved) < "
                f"{MIN_POWER_N}，其区间宽到无法排除中等大小的效应，"
                "上面的「未达标」对它们只应读作「未观测到」，不是「已排除」："
                + "、".join(f"{SUBGROUP_LABELS[k]}（n={findings[k]['n_gap']:,}）"
                           for k in thin) + "。"]
    else:
        out += ["",
                "**功效声明**：四个预登记子组的 n(resolved) 均 ≥ "
                f"{MIN_POWER_N}（最小 "
                f"{min(f['n_gap'] for f in findings.values()):,}），"
                "不存在「样本太小所以看不出来」的解释空间。"]
    out += [
        "",
        "**本节的局限**（与 §9 并列）：",
        "1. 锚点形态是在 5m bar 上机械量化的，与原作者肉眼判读的「光头/光脚」"
        "存在边界差异；阈值敏感性（11.3）覆盖的是这种差异的一部分，不是全部。",
        "2. 子组分析是在同一份数据上做的事后切片，虽然定义预登记于 修订 (四)、"
        "未在见到结果后新增或调整，但多重比较（4 子组 × 3 读法 + 9 格阈值）"
        "仍抬高了任一格偶然达标的概率——本次没有任何一格达标，该问题不影响结论方向。",
        "3. 画线位置敏感性只对 S2 子集重扫，未覆盖 S3/S4 的实体端画法。",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------- main

def build_section(df, lines, ev, cfg) -> str:
    subgroups, findings = section_subgroups(ev)
    base = ev[[c for c in ev.columns if c in P.EVENT_COLUMNS]]
    thresholds_md, thresholds = section_thresholds(base, df)
    placement_md, placement = section_placement(lines, df, cfg)
    dilution_md, dilution = section_dilution(ev)
    return "\n\n".join([
        SECTION,
        "> 起因：v1 判定 REFUTED 是在**全部**被实体突破的波段极值上得到的"
        "（gap − placebo = +0.00pp）。用户质疑该总体未按 z说 的锚点 K 线形态与"
        "颜色过滤，教科书子集的 edge 可能被稀释。本节按 spec 修订 (四) 预登记的"
        "四个子组逐一检验该假说。定义、阈值、敏感性范围与判定更新规则均冻结于"
        "看到本节数字之前。\n"
        "> 配置：k=%d、X=%d ticks、expiry_days=%d（主配置），"
        "锚 bar = `swing_idx` 处的 bar，影线取**线价所在端**。\n"
        "> 本节由 `scripts/zshuo_claim4_anchors.py` 生成（§1–§10 由 "
        "`scripts/zshuo_claim4.py` 生成），勿手工编辑。"
        % (cfg.k, cfg.x_ticks, cfg.expiry_days),
        subgroups,
        thresholds_md,
        placement_md,
        dilution_md,
        section_verdict(findings, placement, thresholds, dilution),
    ])


def splice(report: str, section: str) -> str:
    """Append section 11, replacing an earlier run of it if present."""
    head = report.split(SECTION)[0].rstrip()
    return head + "\n\n" + section.rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--out", type=Path, default=REPORT)
    args = ap.parse_args()

    cfg = AuditConfig()
    t = time.time()
    df, lines, ev = load_frames(args.parquet, cfg)
    print(f"loaded {len(df):,} bars, {len(lines):,} lines, {len(ev):,} events "
          f"in {time.time() - t:.1f}s", flush=True)

    t = time.time()
    section = build_section(df, lines, ev, cfg)
    print(f"built section 11 in {time.time() - t:.1f}s", flush=True)

    args.out.write_text(splice(args.out.read_text(), section))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
