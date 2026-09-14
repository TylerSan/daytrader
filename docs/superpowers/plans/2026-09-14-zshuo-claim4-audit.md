# Claim-4 缺口 S/R 审计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 MES 5min 事件研究检验「缺口线（被实体突破的波段极值）是否为优于普通/随机水平位的支撑阻力」，产出 AUDIT_CLAIM4.md。

**Architecture:** 单遍扫描 5min bar 流生成三类线（gap/phantom/plain）及其首触事件 → 竞赛法度量反弹优先率 → Wilson/Newcombe 统计对比 → 27 组敏感性网格 + 分层表。纯 pandas/numpy，无策略模拟。

**Tech Stack:** Python 3.12 + uv, pandas, numpy, pytest。数据：主检出 `data/cache/ohlcv/MES_1m_2018-05-01_2024-12-31_raw.parquet`（实际 2019-05 起）。

**Spec:** `docs/research/zshuo-price-action/specs/2026-09-14-claim4-gap-sr-audit-design.md`（定义冻结，实现不得偏离；发现 spec 歧义时停下报告，不自行发挥）。

> **⚠️ 作废声明（2026-09-14 修订(二) 后追加）**：本计划 Task 3/4 的示例代码与 Self-Review 中关于 phantom（"靠价格一侧"偏移）与 t0 判定（"只能判 penetrate"）的内容已被 spec 修订(二) 作废——合规审查证明原 phantom 设计产生 88.6% 路过式秒触的退化对照。现行权威实现见 commit 7e4aa852（时移 placebo、t0 双侧判 indeterminate、触线须含线价、双侧 blackout mask）。Task 6/7 执行时以 spec 修订(二) 与实际代码为准，并须实现修订(二)新增的报告义务（placebo 同 bar 占比、C2 剔除计数、跳空作废计数、C2 总体随 expiry 变动注记、indeterminate 上下界稳健性）。

**约定:** 所有命令在 worktree 根 `/Users/tylersan/Projects/Day trading/.claude/worktrees/mystifying-keller-cd440b` 下执行；测试跑 `uv run pytest`。每个 Task 结束提交一次。

---

### Task 1: 配置与数据层 `bars.py`

**Files:**
- Create: `src/daytrader/research/zshuo/__init__.py`（空文件）
- Create: `src/daytrader/research/zshuo/config.py`
- Create: `src/daytrader/research/zshuo/bars.py`
- Test: `tests/research/zshuo/__init__.py`（空）、`tests/research/zshuo/test_bars.py`

- [ ] **Step 1.1: 写 config.py**（无逻辑，直接写实现）

```python
"""Frozen audit parameters. Spec §2/§4. Do not mutate at runtime."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditConfig:
    k: int = 3                      # fractal half-window (spec §2.1)
    x_ticks: int = 8                # race half-width (spec §3)
    tick_size: float = 0.25         # MES tick
    expiry_days: int = 5            # trading days a line stays open (spec §2.5)
    race_timeout_bars: int = 48     # 4h at 5min; unresolved -> "timeout"
    rollover_blackout_bars: int = 12  # 1h each side of instrument_id change
    min_gap_between_events: int = 24  # non-overlap spacing within group+dir (spec §3)
    phantom_offset_ticks: tuple[int, int] = (8, 24)  # uniform range, toward price side
    seed: int = 42


SENSITIVITY_GRID = [
    AuditConfig(k=k, x_ticks=x, expiry_days=e)
    for k in (2, 3, 5)
    for x in (4, 8, 16)
    for e in (2, 5, 10)
]
```

- [ ] **Step 1.2: 写失败测试 test_bars.py**

```python
import numpy as np
import pandas as pd
import pytest

from daytrader.research.zshuo.bars import resample_5m, tag_sessions


def _mk_1m(start="2024-06-03 13:30", n=10, iid=1):
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": np.arange(n, dtype=float) + 100,
            "high": np.arange(n, dtype=float) + 100.5,
            "low": np.arange(n, dtype=float) + 99.5,
            "close": np.arange(n, dtype=float) + 100.25,
            "volume": np.ones(n),
            "instrument_id": iid,
        },
        index=idx,
    )


def test_resample_5m_ohlcv():
    df = resample_5m(_mk_1m())
    assert len(df) == 2
    r = df.iloc[0]
    assert r.open == 100.0 and r.high == 104.5 and r.low == 99.5 and r.close == 104.25
    assert r.volume == 5


def test_resample_marks_rollover():
    a = _mk_1m(n=5, iid=1)
    b = _mk_1m(start="2024-06-03 13:35", n=5, iid=2)
    df = resample_5m(pd.concat([a, b]))
    assert list(df.rollover) == [False, True]


def test_tag_sessions_rth():
    df = resample_5m(_mk_1m(start="2024-06-03 13:30", n=5))   # 09:30 ET
    night = resample_5m(_mk_1m(start="2024-06-03 22:00", n=5))  # 18:00 ET
    assert tag_sessions(df).rth.all()
    assert not tag_sessions(night).rth.any()
```

- [ ] **Step 1.3: 跑测试确认失败**

Run: `uv run pytest tests/research/zshuo/test_bars.py -q`
Expected: FAIL（ModuleNotFoundError: bars）

- [ ] **Step 1.4: 写 bars.py 实现**

```python
"""1m parquet -> 5m bars with session tags and rollover marks."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_AGG = {"open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum", "instrument_id": "first"}


def load_1m(parquet_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(parquet_path)
    cols = ["open", "high", "low", "close", "volume", "instrument_id"]
    df = df[cols].sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def resample_5m(df1m: pd.DataFrame) -> pd.DataFrame:
    df = df1m.resample("5min", label="left", closed="left").agg(_AGG).dropna(
        subset=["open"])
    df["instrument_id"] = df["instrument_id"].astype(int)
    df["rollover"] = df["instrument_id"].ne(df["instrument_id"].shift()).fillna(
        False)
    df.iloc[0, df.columns.get_loc("rollover")] = False
    return df


def tag_sessions(df5m: pd.DataFrame) -> pd.DataFrame:
    et = df5m.index.tz_convert("America/New_York")
    df = df5m.copy()
    df["rth"] = (et.time >= pd.Timestamp("09:30").time()) & (
        et.time < pd.Timestamp("16:00").time())
    df["session_date"] = et.date  # calendar date in ET; used for expiry counting
    return df
```

- [ ] **Step 1.5: 跑测试确认通过**

Run: `uv run pytest tests/research/zshuo/test_bars.py -q`
Expected: 3 passed

- [ ] **Step 1.6: Commit**

```bash
git add src/daytrader/research/zshuo tests/research/zshuo
git commit -m "feat(zshuo): audit config and 5m bar layer"
```

---

### Task 2: 波段点检测 `swings.py`

**Files:**
- Create: `src/daytrader/research/zshuo/swings.py`
- Test: `tests/research/zshuo/test_swings.py`

- [ ] **Step 2.1: 写失败测试**

```python
import pandas as pd

from daytrader.research.zshuo.swings import find_swings


def _series(vals):
    return pd.Series(vals, dtype=float)


def test_finds_strict_swing_high_and_low():
    high = _series([1, 2, 5, 2, 1, 2, 3])
    low = _series([0, 1, 4, 1, 0.5, 1, 2])
    sw = find_swings(high, low - 1, k=2)
    hs = sw[sw.kind == "H"]
    assert list(hs.idx) == [2] and list(hs.price) == [5.0]
    assert list(hs.confirmed_idx) == [4]


def test_ties_are_not_swings():
    high = _series([1, 5, 5, 1, 1])
    low = _series([0, 0, 0, 0, 0])
    sw = find_swings(high, low, k=1)
    assert (sw.kind == "H").sum() == 0  # tie at max -> no strict swing


def test_edges_excluded():
    high = _series([9, 1, 1, 1, 9])
    low = _series([0, 0, 0, 0, 0])
    sw = find_swings(high, low, k=2)
    assert len(sw[sw.kind == "H"]) == 0  # peaks at edges lack full window
```

- [ ] **Step 2.2: 跑测试确认失败**

Run: `uv run pytest tests/research/zshuo/test_swings.py -q`
Expected: FAIL（ModuleNotFoundError: swings）

- [ ] **Step 2.3: 写实现**

```python
"""Confirmed fractal swing points (spec §2.1). No lookahead: a swing at i is
usable only from bar confirmed_idx = i + k onward."""
from __future__ import annotations

import pandas as pd


def find_swings(high: pd.Series, low: pd.Series, k: int) -> pd.DataFrame:
    h, l = high.to_numpy(), low.to_numpy()
    rows = []
    for i in range(k, len(h) - k):
        wh = h[i - k:i + k + 1]
        if h[i] == wh.max() and (wh == h[i]).sum() == 1:
            rows.append((i, float(h[i]), "H", i + k))
        wl = l[i - k:i + k + 1]
        if l[i] == wl.min() and (wl == l[i]).sum() == 1:
            rows.append((i, float(l[i]), "L", i + k))
    return pd.DataFrame(rows, columns=["idx", "price", "kind", "confirmed_idx"])
```

- [ ] **Step 2.4: 跑测试确认通过**

Run: `uv run pytest tests/research/zshuo/test_swings.py -q`
Expected: 3 passed

- [ ] **Step 2.5: Commit**

```bash
git add src/daytrader/research/zshuo/swings.py tests/research/zshuo/test_swings.py
git commit -m "feat(zshuo): confirmed fractal swing detection"
```

---

### Task 3: 线的生命周期与首触事件 `gaps.py`

三类线统一建模：`gap`（实体突破波段极值，宣称 4 主体）、`plain`（未被突破的波段点 = 对照 C2）、`phantom`（gap 创建时在**靠价格一侧**偏移 δ∈U[8,24] ticks 的无结构线 = 对照 C1）。方向语义：up-break 破 swing H → 支撑线 `direction=+1`（反弹=向上）；down-break 破 swing L → 阻力线 `direction=-1`。plain 相反：未破 swing H 是阻力（direction=-1），swing L 是支撑（+1）。

**Files:**
- Create: `src/daytrader/research/zshuo/gaps.py`
- Test: `tests/research/zshuo/test_gaps.py`

- [ ] **Step 3.1: 写失败测试**（合成K线场景为准绳）

```python
import numpy as np
import pandas as pd

from daytrader.research.zshuo.config import AuditConfig
from daytrader.research.zshuo.gaps import scan_lines


def _bars(rows, start="2024-06-03 14:00"):
    """rows: list of (o, h, l, c). 5min UTC bars, RTH-ish."""
    idx = pd.date_range(start, periods=len(rows), freq="5min", tz="UTC")
    o, h, l, c = map(np.array, zip(*rows))
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                       "volume": 1.0, "instrument_id": 1, "rollover": False},
                      index=idx)
    et = df.index.tz_convert("America/New_York")
    df["rth"] = True
    df["session_date"] = et.date
    return df


CFG = AuditConfig(k=1, expiry_days=5)

# 场景A: swing H @103 (idx2, k=1 -> confirmed idx3), idx4 close 104 实体突破
#   -> gap line price=103 dir=+1, FT 看 idx5, idx6 low 102.9 首触 -> event t0=6
SCEN_A = [
    (100, 101, 99, 100),   # 0
    (100, 102, 100, 101),  # 1
    (101, 103, 101, 102),  # 2  swing high 103
    (102, 102.5, 101, 102),# 3  confirmed here
    (102, 104.5, 102, 104),# 4  body-break (close 104 > 103) -> line created
    (104, 105, 103.8, 104.8),# 5 follow-through (close > 103)
    (104.8, 104.9, 102.9, 103.5),# 6 low <= 103 -> first touch
]


def test_gap_line_created_ft_and_touched():
    ev = scan_lines(_bars(SCEN_A), CFG)
    g = ev[ev.kind == "gap"]
    assert len(g) == 1
    r = g.iloc[0]
    assert r.price == 103.0 and r.direction == 1
    assert r.created_idx == 4 and bool(r.follow_through) is True
    assert r.touched_idx == 6


def test_no_touch_before_creation_bar_low():
    # 突破bar自身low在线下不算触线（触线从 created_idx+1 起）
    ev = scan_lines(_bars(SCEN_A[:6]), CFG)
    g = ev[ev.kind == "gap"].iloc[0]
    assert pd.isna(g.touched_idx)


def test_plain_swing_touch_is_c2_event():
    # swing H @103 confirmed, 价格从下方回触 103 但 close 未破 -> plain 事件
    rows = SCEN_A[:4] + [(102, 103.2, 101.5, 102.5)]  # idx4 high>=103, close<103
    ev = scan_lines(_bars(rows), CFG)
    p = ev[ev.kind == "plain"]
    assert len(p) == 1
    assert p.iloc[0].price == 103.0 and p.iloc[0].direction == -1
    assert p.iloc[0].touched_idx == 4


def test_phantom_created_with_gap_on_price_side():
    ev = scan_lines(_bars(SCEN_A), CFG)
    ph = ev[ev.kind == "phantom"]
    assert len(ph) == 1
    assert ph.iloc[0].price > 103.0  # +1 线的 phantom 在价格一侧(上方)
    off = (ph.iloc[0].price - 103.0) / CFG.tick_size
    assert 8 <= off <= 24


def test_rollover_kills_open_lines_and_blackout():
    rows = list(SCEN_A[:6])
    df = _bars(rows)
    df.iloc[5, df.columns.get_loc("rollover")] = True
    ev = scan_lines(df, CFG)
    g = ev[ev.kind == "gap"].iloc[0]
    assert pd.isna(g.touched_idx)  # line killed at rollover, later touch 不计
```

- [ ] **Step 3.2: 跑测试确认失败**

Run: `uv run pytest tests/research/zshuo/test_gaps.py -q`
Expected: FAIL（ModuleNotFoundError: gaps）

- [ ] **Step 3.3: 写实现**

```python
"""Line lifecycle scan (spec §2, §3 controls). Single forward pass, no lookahead:
swings usable from confirmed_idx; touches counted from created_idx+1."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import AuditConfig
from .swings import find_swings


@dataclass
class _Line:
    line_id: int
    price: float
    direction: int      # bounce direction: +1 support, -1 resistance
    kind: str           # gap | plain | phantom
    created_idx: int
    swing_idx: int
    expiry_date_pos: int          # index into unique session_date array
    follow_through: bool | None = None
    touched_idx: float = np.nan


def _touched(line: _Line, hi: float, lo: float) -> bool:
    return lo <= line.price if line.direction == 1 else hi >= line.price


def scan_lines(df: pd.DataFrame, cfg: AuditConfig) -> pd.DataFrame:
    rng = np.random.default_rng(cfg.seed)
    h, l, c = df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy()
    roll = df.rollover.to_numpy()
    dates = pd.factorize(df.session_date)[0]  # ascending session ordinal
    sw = find_swings(df.high, df.low, cfg.k)
    sw_by_confirm: dict[int, list] = {}
    for r in sw.itertuples():
        sw_by_confirm.setdefault(r.confirmed_idx, []).append(r)

    active: list = []            # confirmed, unbroken swings
    open_lines: list[_Line] = []
    done: list[_Line] = []
    next_id = 0
    blackout_until = -1

    for t in range(len(df)):
        if roll[t]:
            done.extend(open_lines)      # killed untouched
            open_lines = []
            active = []
            blackout_until = t + cfg.rollover_blackout_bars
        in_blackout = t <= blackout_until

        # 1) touches on open lines (from created_idx+1 onward)
        still = []
        for ln in open_lines:
            if dates[t] - dates[ln.created_idx] >= cfg.expiry_days:
                done.append(ln)          # expired untouched
                continue
            if t > ln.created_idx and not in_blackout and _touched(ln, h[t], l[t]):
                ln.touched_idx = t
                done.append(ln)
            else:
                still.append(ln)
        open_lines = still

        # 2) follow-through check for lines created at t-1
        for ln in open_lines:
            if ln.created_idx == t - 1 and ln.kind == "gap":
                ln.follow_through = bool(
                    c[t] > ln.price if ln.direction == 1 else c[t] < ln.price)

        # 3) plain (C2) touches + gap creation on active swings
        remaining = []
        for s in active:
            broken = c[t] > s.price if s.kind == "H" else c[t] < s.price
            if broken and not in_blackout:
                direction = 1 if s.kind == "H" else -1
                gap = _Line(next_id, s.price, direction, "gap", t, s.idx,
                            dates[t] + cfg.expiry_days)
                next_id += 1
                open_lines.append(gap)
                lo_off, hi_off = cfg.phantom_offset_ticks
                delta = int(rng.integers(lo_off, hi_off + 1)) * cfg.tick_size
                open_lines.append(_Line(next_id, s.price + direction * delta,
                                        direction, "phantom", t, s.idx,
                                        dates[t] + cfg.expiry_days))
                next_id += 1
                continue                 # swing consumed
            touched = h[t] >= s.price if s.kind == "H" else l[t] <= s.price
            if touched and t > s.confirmed_idx and not in_blackout \
                    and not getattr(s, "_tested", False):
                direction = -1 if s.kind == "H" else 1
                pl = _Line(next_id, s.price, direction, "plain", s.confirmed_idx,
                           s.idx, 0, touched_idx=t)
                next_id += 1
                done.append(pl)
                s = s._replace() if hasattr(s, "_replace") else s
                object.__setattr__(s, "_tested", True) if False else None
                s_tested = True
            remaining.append(s)
        active = remaining

        # 4) newly confirmed swings become active
        for s in sw_by_confirm.get(t, []):
            active.append(s)

    done.extend(open_lines)
    rows = [(ln.line_id, ln.price, ln.direction, ln.kind, ln.created_idx,
             ln.swing_idx, ln.follow_through, ln.touched_idx) for ln in done]
    return pd.DataFrame(rows, columns=["line_id", "price", "direction", "kind",
                                       "created_idx", "swing_idx",
                                       "follow_through", "touched_idx"])
```

注意：上面 `s_tested` 一段是刻意暴露的坑——`sw.itertuples()` 的行是不可变的，"每条 plain 线只出一次事件"需要用一个 `tested_swing_ids: set` 来实现，而不是给 namedtuple 设属性。**实现者必须重写第 3 段为**：维护 `tested: set[int]`（存 s.idx），touched 且 `s.idx not in tested` 时出事件并 `tested.add(s.idx)`。测试 3.1 的 `test_plain_swing_touch_is_c2_event` 会验证；再补一个二次回触不重复出事件的测试：

```python
def test_plain_swing_only_first_touch_counts():
    rows = SCEN_A[:4] + [(102, 103.2, 101.5, 102.5), (102.5, 103.4, 102, 102.8)]
    ev = scan_lines(_bars(rows), CFG)
    assert len(ev[ev.kind == "plain"]) == 1
```

- [ ] **Step 3.4: 跑测试确认全部通过**

Run: `uv run pytest tests/research/zshuo/test_gaps.py -q`
Expected: 6 passed

- [ ] **Step 3.5: Commit**

```bash
git add src/daytrader/research/zshuo/gaps.py tests/research/zshuo/test_gaps.py
git commit -m "feat(zshuo): gap/plain/phantom line lifecycle and first-touch events"
```

---

### Task 4: 竞赛度量 `race.py`

**Files:**
- Create: `src/daytrader/research/zshuo/race.py`
- Test: `tests/research/zshuo/test_race.py`

- [ ] **Step 4.1: 写失败测试**

```python
import numpy as np
import pandas as pd

from daytrader.research.zshuo.race import run_race

TICK = 0.25


def _df(rows):
    o = np.array([r[0] for r in rows], float)
    return pd.DataFrame({"open": o, "high": [r[1] for r in rows],
                         "low": [r[2] for r in rows], "close": [r[3] for r in rows]})


def test_bounce_win():
    # line 100, dir +1, X=8 ticks -> bounce tgt 102, pen tgt 98
    df = _df([(101, 101, 100, 100.5),      # t0 touch
              (100.5, 102.5, 100.2, 102)])  # hits 102 first
    assert run_race(df, 0, 100.0, 1, 8, TICK, 48) == "bounce"


def test_penetrate_win():
    df = _df([(101, 101, 100, 100.5), (100.5, 101, 97.9, 98)])
    assert run_race(df, 0, 100.0, 1, 8, TICK, 48) == "penetrate"


def test_touch_bar_blowthrough_is_penetrate():
    df = _df([(101, 101, 97.5, 98)])
    assert run_race(df, 0, 100.0, 1, 8, TICK, 48) == "penetrate"


def test_same_bar_both_sides_indeterminate():
    df = _df([(101, 101, 100, 100.5), (100.5, 102.5, 97.5, 100)])
    assert run_race(df, 0, 100.0, 1, 8, TICK, 48) == "indeterminate"


def test_timeout():
    df = _df([(101, 101, 100, 100.5)] + [(100.5, 101, 100.2, 100.6)] * 3)
    assert run_race(df, 0, 100.0, 1, 8, TICK, 2) == "timeout"


def test_resistance_direction_symmetric():
    # dir -1: bounce tgt 98, pen tgt 102
    df = _df([(99, 100, 99, 99.5), (99.5, 99.8, 97.9, 98)])
    assert run_race(df, 0, 100.0, -1, 8, TICK, 48) == "bounce"
```

- [ ] **Step 4.2: 跑测试确认失败**

Run: `uv run pytest tests/research/zshuo/test_race.py -q`
Expected: FAIL

- [ ] **Step 4.3: 写实现**

```python
"""Race metric (spec §3): from line price, which side of ±X ticks is hit first.
t0 bar can only decide 'penetrate' (blow-through); bounce evaluation starts t0+1
because the pre-touch part of t0's range contaminates the bounce side."""
from __future__ import annotations

import pandas as pd


def run_race(df: pd.DataFrame, t0: int, line_price: float, bounce_dir: int,
             x_ticks: int, tick_size: float, timeout_bars: int) -> str:
    half = x_ticks * tick_size
    b_tgt = line_price + bounce_dir * half
    p_tgt = line_price - bounce_dir * half
    lo, hi = df.low.to_numpy(), df.high.to_numpy()

    def hit_b(t):
        return hi[t] >= b_tgt if bounce_dir == 1 else lo[t] <= b_tgt

    def hit_p(t):
        return lo[t] <= p_tgt if bounce_dir == 1 else hi[t] >= p_tgt

    if hit_p(t0):
        return "penetrate"
    for t in range(t0 + 1, min(t0 + 1 + timeout_bars, len(df))):
        b, p = hit_b(t), hit_p(t)
        if b and p:
            return "indeterminate"
        if b:
            return "bounce"
        if p:
            return "penetrate"
    return "timeout"
```

- [ ] **Step 4.4: 跑测试确认通过**

Run: `uv run pytest tests/research/zshuo/test_race.py -q`
Expected: 6 passed

- [ ] **Step 4.5: Commit**

```bash
git add src/daytrader/research/zshuo/race.py tests/research/zshuo/test_race.py
git commit -m "feat(zshuo): bounce-vs-penetrate race metric"
```

---

### Task 5: 统计 `stats.py`

**Files:**
- Create: `src/daytrader/research/zshuo/stats.py`
- Test: `tests/research/zshuo/test_stats.py`

- [ ] **Step 5.1: 写失败测试**（Wilson 已知值：k=8,n=10 → CI≈[0.490, 0.943]）

```python
import pytest

from daytrader.research.zshuo.stats import wilson, diff_ci


def test_wilson_known_value():
    p, lo, hi = wilson(8, 10)
    assert p == pytest.approx(0.8)
    assert lo == pytest.approx(0.490, abs=0.005)
    assert hi == pytest.approx(0.943, abs=0.005)


def test_wilson_empty():
    p, lo, hi = wilson(0, 0)
    assert p != p  # NaN


def test_diff_ci_sign_and_containment():
    d, lo, hi = diff_ci(80, 100, 50, 100)
    assert d == pytest.approx(0.30)
    assert lo < d < hi and lo > 0  # clearly separated proportions
```

- [ ] **Step 5.2: 跑测试确认失败**

Run: `uv run pytest tests/research/zshuo/test_stats.py -q`
Expected: FAIL

- [ ] **Step 5.3: 写实现**

```python
"""Wilson CI and Newcombe (method 10) difference CI. No scipy dependency."""
from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        nan = float("nan")
        return nan, nan, nan
    p = k / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return p, (center - half) / denom, (center + half) / denom


def diff_ci(k1: int, n1: int, k2: int, n2: int,
            z: float = 1.96) -> tuple[float, float, float]:
    p1, l1, u1 = wilson(k1, n1, z)
    p2, l2, u2 = wilson(k2, n2, z)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return d, lo, hi
```

- [ ] **Step 5.4: 跑测试确认通过**

Run: `uv run pytest tests/research/zshuo/test_stats.py -q`
Expected: 3 passed

- [ ] **Step 5.5: Commit**

```bash
git add src/daytrader/research/zshuo/stats.py tests/research/zshuo/test_stats.py
git commit -m "feat(zshuo): wilson and newcombe interval stats"
```

---

### Task 6: 管线组装 `pipeline.py` + 入口脚本

**Files:**
- Create: `src/daytrader/research/zshuo/pipeline.py`
- Create: `scripts/zshuo_claim4.py`
- Test: `tests/research/zshuo/test_pipeline.py`

- [ ] **Step 6.1: 写失败测试**（合成数据端到端 + 非重叠规则）

```python
import numpy as np
import pandas as pd

from daytrader.research.zshuo.config import AuditConfig
from daytrader.research.zshuo.pipeline import build_events, apply_nonoverlap


def test_apply_nonoverlap_keeps_first():
    ev = pd.DataFrame({
        "kind": ["gap"] * 3, "direction": [1, 1, 1],
        "touched_idx": [100.0, 110.0, 140.0],
    })
    out = apply_nonoverlap(ev, min_gap=24)
    assert list(out.touched_idx) == [100.0, 140.0]


def test_build_events_columns():
    # 复用 Task 3 场景A 构造 bars（复制 _bars 与 SCEN_A 的代码到本测试文件）
    from tests.research.zshuo.test_gaps import _bars, SCEN_A, CFG
    ev = build_events(_bars(SCEN_A), CFG)
    assert {"kind", "direction", "outcome", "rth", "line_age_bars",
            "follow_through"} <= set(ev.columns)
    g = ev[ev.kind == "gap"]
    assert len(g) == 1 and g.iloc[0].outcome in {"bounce", "penetrate",
                                                 "indeterminate", "timeout"}
```

- [ ] **Step 6.2: 跑测试确认失败**

Run: `uv run pytest tests/research/zshuo/test_pipeline.py -q`
Expected: FAIL

- [ ] **Step 6.3: 写 pipeline.py**

```python
"""Assemble: bars -> lines -> touched events -> race outcomes -> tidy frame."""
from __future__ import annotations

import pandas as pd

from .config import AuditConfig
from .gaps import scan_lines
from .race import run_race


def build_events(df: pd.DataFrame, cfg: AuditConfig) -> pd.DataFrame:
    lines = scan_lines(df, cfg)
    ev = lines.dropna(subset=["touched_idx"]).copy()
    ev["touched_idx"] = ev.touched_idx.astype(int)
    ev["outcome"] = [
        run_race(df, int(r.touched_idx), float(r.price), int(r.direction),
                 cfg.x_ticks, cfg.tick_size, cfg.race_timeout_bars)
        for r in ev.itertuples()
    ]
    ev["rth"] = df.rth.to_numpy()[ev.touched_idx]
    ev["line_age_bars"] = ev.touched_idx - ev.created_idx
    return ev.reset_index(drop=True)


def apply_nonoverlap(ev: pd.DataFrame, min_gap: int) -> pd.DataFrame:
    kept = []
    for (_, _), grp in ev.groupby(["kind", "direction"]):
        last = None
        for r in grp.sort_values("touched_idx").itertuples():
            if last is None or r.touched_idx - last >= min_gap:
                kept.append(r.Index)
                last = r.touched_idx
    return ev.loc[sorted(kept)].reset_index(drop=True)


def summarize(ev: pd.DataFrame) -> pd.DataFrame:
    """Per kind: n(resolved), bounce count, bounce rate. resolved = bounce|penetrate."""
    res = ev[ev.outcome.isin(["bounce", "penetrate"])]
    rows = []
    for kind, grp in res.groupby("kind"):
        rows.append((kind, len(grp), int((grp.outcome == "bounce").sum())))
    return pd.DataFrame(rows, columns=["kind", "n", "bounce"])
```

- [ ] **Step 6.4: 写 scripts/zshuo_claim4.py**

```python
"""Claim-4 audit runner. Usage:
  uv run python scripts/zshuo_claim4.py --parquet <path> [--full-grid]
Writes docs/research/zshuo-price-action/AUDIT_CLAIM4.md
"""
from __future__ import annotations

import argparse
from pathlib import Path

from daytrader.research.zshuo.bars import load_1m, resample_5m, tag_sessions
from daytrader.research.zshuo.config import SENSITIVITY_GRID, AuditConfig
from daytrader.research.zshuo.pipeline import (apply_nonoverlap, build_events,
                                               summarize)
from daytrader.research.zshuo.stats import diff_ci, wilson

DEFAULT_PARQUET = Path(
    "/Users/tylersan/Projects/Day trading/data/cache/ohlcv/"
    "MES_1m_2018-05-01_2024-12-31_raw.parquet")
REPORT = Path("docs/research/zshuo-price-action/AUDIT_CLAIM4.md")


def run_one(df5, cfg):
    ev = apply_nonoverlap(build_events(df5, cfg), cfg.min_gap_between_events)
    s = summarize(ev).set_index("kind")
    return ev, s


def fmt_group(s, kind):
    if kind not in s.index:
        return f"| {kind} | 0 | — | — |"
    n, b = int(s.loc[kind].n), int(s.loc[kind].bounce)
    p, lo, hi = wilson(b, n)
    return f"| {kind} | {n} | {p:.1%} | [{lo:.1%}, {hi:.1%}] |"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--full-grid", action="store_true")
    args = ap.parse_args()

    df5 = tag_sessions(resample_5m(load_1m(args.parquet)))
    main_cfg = AuditConfig()
    ev, s = run_one(df5, main_cfg)

    lines = ["# Claim-4 审计结果：缺口线 vs 对照", "",
             f"数据：MES 5min，{df5.index.min().date()} → {df5.index.max().date()}，"
             f"主配置 k={main_cfg.k}, X={main_cfg.x_ticks} ticks, "
             f"expiry={main_cfg.expiry_days}d", "",
             "## 主表（反弹优先率，仅 resolved 事件）", "",
             "| 组 | n | 反弹率 | Wilson 95% CI |", "|---|---|---|---|"]
    for kind in ("gap", "phantom", "plain"):
        lines.append(fmt_group(s, kind))

    def _diff(a, b):
        if a in s.index and b in s.index:
            d, lo, hi = diff_ci(int(s.loc[a].bounce), int(s.loc[a].n),
                                int(s.loc[b].bounce), int(s.loc[b].n))
            return f"gap − {b}: {d:+.1%}  CI [{lo:+.1%}, {hi:+.1%}]"
        return f"gap − {b}: 数据不足"

    lines += ["", "## 效应量（Newcombe 95% CI）", "",
              f"- {_diff('gap', 'phantom')}   ← C1 随机水平位",
              f"- {_diff('gap', 'plain')}   ← C2 普通波段点", ""]

    # 分层：RTH / FT / 线龄
    res = ev[ev.outcome.isin(["bounce", "penetrate"])]
    lines += ["## 分层（gap 组）", "", "| 层 | n | 反弹率 |", "|---|---|---|"]
    g = res[res.kind == "gap"]
    for name, sub in [("RTH", g[g.rth]), ("overnight", g[~g.rth]),
                      ("FT+", g[g.follow_through == True]),   # noqa: E712
                      ("FT-", g[g.follow_through == False]),  # noqa: E712
                      ("age 1-6 bars", g[g.line_age_bars <= 6]),
                      ("age 7-24", g[(g.line_age_bars > 6) & (g.line_age_bars <= 24)]),
                      ("age >24", g[g.line_age_bars > 24])]:
        n = len(sub)
        rate = f"{(sub.outcome == 'bounce').mean():.1%}" if n else "—"
        lines.append(f"| {name} | {n} | {rate} |")

    # 事件处置统计
    lines += ["", "## 事件处置", "",
              ev.groupby(["kind", "outcome"]).size().to_frame("n").to_markdown(), ""]

    if args.full_grid:
        lines += ["## 敏感性网格（gap−phantom 效应，27 组）", "",
                  "| k | X | expiry | n_gap | 效应 | CI |", "|---|---|---|---|---|---|"]
        for cfg in SENSITIVITY_GRID:
            _, sg = run_one(df5, cfg)
            if "gap" in sg.index and "phantom" in sg.index:
                d, lo, hi = diff_ci(int(sg.loc["gap"].bounce), int(sg.loc["gap"].n),
                                    int(sg.loc["phantom"].bounce),
                                    int(sg.loc["phantom"].n))
                lines.append(f"| {cfg.k} | {cfg.x_ticks} | {cfg.expiry_days} | "
                             f"{int(sg.loc['gap'].n)} | {d:+.1%} | "
                             f"[{lo:+.1%}, {hi:+.1%}] |")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines))
    print(f"wrote {REPORT}; gap events (resolved): "
          f"{int(s.loc['gap'].n) if 'gap' in s.index else 0}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6.5: 跑测试确认通过 + 全量回归**

Run: `uv run pytest tests/research/zshuo -q`
Expected: 全部 passed（约 18 项）

- [ ] **Step 6.6: Commit**

```bash
git add src/daytrader/research/zshuo/pipeline.py scripts/zshuo_claim4.py tests/research/zshuo/test_pipeline.py
git commit -m "feat(zshuo): claim-4 pipeline and report runner"
```

---

### Task 7: 真实数据运行与报告

**Files:**
- Create（脚本产出）: `docs/research/zshuo-price-action/AUDIT_CLAIM4.md`

- [ ] **Step 7.1: 主配置运行（先不跑 grid，验证量级与耗时）**

Run: `uv run python scripts/zshuo_claim4.py`
Expected: 打印 `wrote docs/.../AUDIT_CLAIM4.md; gap events (resolved): <n>`，n 预计在数千量级。若 n < 200：停下报告（样本不足以判定，可能检测规则或数据有 bug）；若脚本超过 15 分钟未完成：停下报告耗时（1m→5m 约 40 万根 bar，纯 python 扫描可能需要优化，报告而非自行改算法）。

- [ ] **Step 7.2: 抽查合理性**

写一段一次性检查（不入库）：随机抽 5 个 gap 事件，打印其 created/touched 前后各 8 根 bar 的 OHLC，人工核对"实体突破→回触"肉眼成立。发现明显错位（如线价不在被破波段极值上）→ 停下报告。

- [ ] **Step 7.3: 全网格运行**

Run: `uv run python scripts/zshuo_claim4.py --full-grid`
Expected: 报告含 27 行敏感性表。耗时约为主配置的 27 倍（可接受则跑完；不可接受先报告）。

- [ ] **Step 7.4: Commit 报告**

```bash
git add docs/research/zshuo-price-action/AUDIT_CLAIM4.md
git commit -m "docs(zshuo): claim-4 audit results on MES 5m"
```

---

## Self-Review 记录

- Spec 覆盖：§1 数据（Task 1）；§2.1-2.5 检测（Task 2/3；§2.6 跨周期例外按 spec 排除）；§3 事件+对照+非重叠（Task 3/6）+竞赛（Task 4）；§4 统计+网格（Task 5/6）；§5 产出（Task 6/7）。分层三桶（RTH/FT/线龄）在 Task 6 runner 中。
- 已知设计取舍（与 spec 一致或已注明）：phantom 偏移在**靠价格一侧**（同一回调先触无结构线，匹配时间与波动语境）；plain 线的 direction 与 gap 相反侧；t0 bar 只能判 penetrate。
- Task 3 的示例实现中 plain-swing 去重段刻意标注为必须重写（set 方案），并配了锁定测试。
- 类型一致性：`scan_lines` 输出列与 `build_events` 消费列已对齐；`summarize` 只计 resolved。
