"""IBKR Activity-Statement behavioral review engine.

Read-only. Parses one or more IBKR *Activity Statement* CSV exports
(multi-section, Flex v2) and produces a quantified **behavioral** diagnosis:
overtrading, stop discipline, win/loss asymmetry, tilt, sizing, options
autopsy, a counterfactual replay of the signed Contract rules on real fills,
and the MES/MGC profile.

Boundary: this is behavioral diagnosis + Contract validation **only**. It does
not fit, suggest, or backtest a trading strategy. Counterfactuals are
rule-overlays on actual fills at historical sizing (later same-day trades are
the ones dropped — a selection caveat, directionally robust given magnitudes).

Build-vs-reuse: there is no existing IBKR Activity-Statement CSV parser in the
project, and maintained libraries (ibflex, quantstats, pyfolio) target Flex
*XML* or a returns series — not the multi-section statement CSV nor the
bespoke behavioral metrics here. A custom, tested stdlib module is therefore
justified under the project dependency policy. No new dependencies are added.
"""

from __future__ import annotations

import csv
import re
import statistics as st
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

_DATE_TOKEN = re.compile(r"^\d{1,2}[A-Za-z]{3}\d{2}$")
_OPTIONS = "Equity and Index Options"


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
@dataclass
class Fill:
    dt: datetime
    sym: str
    ccy: str
    qty: float
    price: float
    comm: float
    realized: float
    code: str
    asset: str

    @property
    def year(self) -> int:
        return self.dt.year


def _num(s: str) -> float:
    s = (s or "").replace(",", "").strip()
    if s in ("", "-", "--"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_dt(s: str) -> datetime | None:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d, %H:%M:%S", "%Y-%m-%d, %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_option_symbol(sym: str) -> tuple[str, datetime | None, str | None]:
    """`'SPY 03MAR25 612 C'` -> (underlying, expiry, 'C'|'P')."""
    tokens = sym.split()
    if not tokens:
        return (sym, None, None)
    underlying, expiry, cp = tokens[0], None, None
    for tok in tokens[1:]:
        if _DATE_TOKEN.match(tok):
            try:
                expiry = datetime.strptime(tok.title(), "%d%b%y")
            except ValueError:
                expiry = None
        if tok.upper() in ("C", "P", "CALL", "PUT"):
            cp = tok.upper()[0]
    return (underlying, expiry, cp)


def _expand_paths(paths: Iterable[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            out.extend(sorted(p.glob("*.csv")))
        else:
            out.append(p)
    return out


def load_statements(
    paths: Iterable[Path], cad_usd: float = 0.73
) -> tuple[list[Fill], dict[str, float]]:
    """Return (fills sorted by time, {filename: IBKR Total P/L for period})."""
    fills: list[Fill] = []
    anchors: dict[str, float] = {}
    seen: set[tuple] = set()
    for path in _expand_paths(paths):
        if not path.exists():
            continue
        with open(path, newline="", encoding="utf-8-sig") as fh:
            header: dict[str, int] | None = None
            for row in csv.reader(fh):
                if not row:
                    continue
                sec = row[0]
                if sec == "Trades" and len(row) > 1 and row[1] == "Header":
                    header = {name: i for i, name in enumerate(row)}
                    continue
                if (
                    sec == "Trades"
                    and len(row) > 1
                    and row[1] == "Data"
                    and header
                    and "Realized P/L" in header
                    and row[2] == "Order"
                ):
                    def g(key: str) -> str:
                        i = header.get(key, -1)
                        return row[i] if 0 <= i < len(row) else ""

                    dt = _parse_dt(g("Date/Time"))
                    if dt is None:
                        continue
                    key = (
                        g("Date/Time"), g("Symbol"), g("Quantity"),
                        g("T. Price"), g("Currency"),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    fills.append(
                        Fill(
                            dt=dt, sym=g("Symbol"), ccy=g("Currency"),
                            qty=_num(g("Quantity")), price=_num(g("T. Price")),
                            comm=_num(g("Comm/Fee")),
                            realized=_num(g("Realized P/L")),
                            code=g("Code"), asset=g("Asset Category"),
                        )
                    )
                elif sec == "Total P/L for Statement Period":
                    for cell in reversed(row):
                        v = _num(cell)
                        if v != 0.0:
                            anchors[path.name] = v
                            break
    fills.sort(key=lambda f: f.dt)
    return fills, anchors


# --------------------------------------------------------------------------- #
# Reconstruction
# --------------------------------------------------------------------------- #
@dataclass
class ClosingFill:
    dt: datetime
    usd: float
    sym: str
    direction: str  # "LONG" | "SHORT"
    hold_s: float
    asset: str
    underlying: str | None = None
    cp: str | None = None
    dte: int | None = None

    @property
    def year(self) -> int:
        return self.dt.year


def _usd(f: Fill, cad_usd: float) -> float:
    return f.realized * (cad_usd if f.ccy == "CAD" else 1.0)


@dataclass
class Reconstruction:
    closings: list[ClosingFill]
    avg_down_events: int
    avg_down_legs: int


def reconstruct(fills: list[Fill], cad_usd: float = 0.73) -> Reconstruction:
    """FIFO round-trip reconstruction -> per-closing-fill records."""
    lots: dict[tuple, list[list]] = defaultdict(list)
    entry: dict[tuple, list[float]] = defaultdict(lambda: [0.0, 0.0])
    closings: list[ClosingFill] = []
    avg_down = 0
    avg_down_legs: set[tuple] = set()
    for f in fills:
        k = (f.sym, f.ccy)
        q = f.qty
        pq, pavg = entry[k]
        book = lots[k]
        same_dir = pq == 0 or (pq > 0 and q > 0) or (pq < 0 and q < 0)
        if same_dir:
            if pq > 0 and q > 0 and f.price < pavg:
                avg_down += 1
                avg_down_legs.add(k)
            if pq < 0 and q < 0 and f.price > pavg:
                avg_down += 1
                avg_down_legs.add(k)
            new_q = pq + q
            if new_q != 0:
                entry[k][1] = (pavg * pq + f.price * q) / new_q
            entry[k][0] = new_q
            book.append([q, f.dt])
        else:
            first_dt = book[0][1] if book else f.dt
            direction = "LONG" if (book and book[0][0] > 0) else "SHORT"
            rem = q
            while rem != 0 and book:
                lot = book[0]
                take = min(abs(lot[0]), abs(rem))
                lot[0] += take if lot[0] < 0 else -take
                rem += take if rem < 0 else -take
                if lot[0] == 0:
                    book.pop(0)
            entry[k][0] = pq + q
            if f.realized != 0:
                und = cp = None
                dte = None
                if f.asset == _OPTIONS:
                    und, exp, cp = parse_option_symbol(f.sym)
                    if exp is not None:
                        dte = (exp.date() - first_dt.date()).days
                closings.append(
                    ClosingFill(
                        dt=f.dt, usd=_usd(f, cad_usd), sym=f.sym,
                        direction=direction,
                        hold_s=(f.dt - first_dt).total_seconds(),
                        asset=f.asset, underlying=und, cp=cp, dte=dte,
                    )
                )
            if rem != 0:
                book.append([rem, f.dt])
                entry[k] = [rem, f.price]
    return Reconstruction(closings, avg_down, len(avg_down_legs))


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def _pctile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, int(round(p / 100 * (len(sorted_vals) - 1))))
    return sorted_vals[i]


@dataclass
class ReviewReport:
    sections: list[tuple[str, list[str]]] = field(default_factory=list)

    def add(self, title: str, lines: list[str]) -> None:
        self.sections.append((title, lines))

    def text(self) -> str:
        out: list[str] = []
        for title, lines in self.sections:
            out.append("=" * 64)
            out.append(title)
            out.append("=" * 64)
            out.extend(lines)
            out.append("")
        return "\n".join(out)

    def markdown(self) -> str:
        out = [
            "# IBKR Behavioral Review — machine-generated data report",
            "",
            "_Behavioral diagnosis only; not strategy advice. Generated by "
            "`daytrader journal review-history`._",
            "",
        ]
        for title, lines in self.sections:
            out.append(f"## {title}")
            out.append("")
            out.append("```")
            out.extend(lines)
            out.append("```")
            out.append("")
        return "\n".join(out)


def build_report(
    fills: list[Fill],
    anchors: dict[str, float],
    cad_usd: float = 0.73,
    r_unit: float = 50.0,
) -> ReviewReport:
    rep = ReviewReport()
    rec = reconstruct(fills, cad_usd)
    closings = rec.closings
    if not fills:
        rep.add("No data", ["No Trades/Order rows parsed from the input."])
        return rep

    def u(f: Fill) -> float:
        return _usd(f, cad_usd)

    closed = [f for f in fills if f.realized != 0]
    years = sorted({f.year for f in fills})

    # 1. Truth anchors + overtrading
    lines = ["IBKR-reported Total P/L per statement (hard anchor):"]
    for name, v in anchors.items():
        lines.append(f"  {name[:42]:42s}  ${v:,.2f}")
    lines.append("")
    for y in years:
        yt = [f for f in fills if f.year == y]
        days: dict = defaultdict(int)
        for f in yt:
            days[f.dt.date()] += 1
        dv = sorted(days.values())
        over3 = sum(1 for x in dv if x > 3)
        lines.append(
            f"{y}: {len(yt):5d} orders | {len(dv):3d} days | "
            f"median {st.median(dv):.0f}/day mean {st.mean(dv):.1f} "
            f"max {max(dv)} | days>3: {over3}/{len(dv)} "
            f"({100 * over3 / len(dv):.0f}%)"
        )
    rep.add("1. TRUTH ANCHORS + OVERTRADING", lines)

    # 2. No preset stop — loss tail
    losses = sorted(abs(u(f)) for f in closed if u(f) < 0)
    wins = [u(f) for f in closed if u(f) > 0]
    if losses:
        med = st.median(losses)
        big = [x for x in losses if x > 10 * r_unit]
        rep.add(
            "2. NO PRESET STOP (loss tail)",
            [
                f"closed {len(closed)} | wins {len(wins)} losses {len(losses)}",
                f"loss median ${med:,.0f} | p90 ${_pctile(losses,90):,.0f} "
                f"| p99 ${_pctile(losses,99):,.0f} | MAX ${max(losses):,.0f}",
                f"MAX/median = {max(losses)/med:.0f}x "
                f"(disciplined stop ~1-3x) | worst = {max(losses)/r_unit:.0f}R",
                f"losses >10R (>${10*r_unit:,.0f}): {len(big)} trades, "
                f"bled ${sum(big):,.0f}",
            ],
        )

    # 3. Win/loss asymmetry + hold time
    if wins and losses and closed:
        aw, al = st.mean(wins), st.mean(losses)
        wr = 100 * len(wins) / len(closed)
        exp = sum(u(f) for f in closed) / len(closed)
        hw = [c.hold_s for c in closings if c.usd > 0]
        hl = [c.hold_s for c in closings if c.usd < 0]
        line2 = ""
        if hw and hl:
            line2 = (
                f"hold: winners median {st.median(hw)/3600:.1f}h vs "
                f"losers {st.median(hl)/3600:.1f}h "
                f"({st.median(hl)/max(st.median(hw),1):.1f}x)"
            )
        rep.add(
            "3. WIN SMALL / LOSE BIG",
            [
                f"win rate {wr:.1f}% | avg win ${aw:,.0f} avg loss "
                f"${al:,.0f} | payoff {aw/al:.2f}",
                f"expectancy per closed trade ${exp:,.2f}",
                line2,
            ],
        )

    # 4. Holding segment
    seg: dict = defaultdict(list)
    for c in closings:
        h = c.hold_s / 3600
        b = (
            "intraday <8h" if h < 8
            else "overnight 8-36h" if h < 36
            else "multi-day 1-7d" if h < 168
            else ">1 week"
        )
        seg[b].append(c.usd)
    seg_lines = []
    for b in ("intraday <8h", "overnight 8-36h", "multi-day 1-7d", ">1 week"):
        v = seg.get(b, [])
        if v:
            w = 100 * sum(1 for x in v if x > 0) / len(v)
            seg_lines.append(
                f"{b:16s}: n {len(v):5d} | net ${sum(v):11,.0f} | win% {w:3.0f}"
            )
    rep.add("4. HOLDING SEGMENT (are you day-trading?)", seg_lines)

    # 5. Tilt
    seq = sorted(closed, key=lambda f: f.dt)
    after, base = [], []
    for i in range(1, len(seq)):
        p, c = seq[i - 1], seq[i]
        gap = (c.dt - p.dt).total_seconds()
        if p.dt.date() == c.dt.date() and u(p) < 0 and gap <= 600:
            after.append(u(c))
        else:
            base.append(u(c))
    if after:
        rep.add(
            "5. POST-LOSS TILT (<=10 min after a loss)",
            [
                f"after a loss: n {len(after)} avg ${st.mean(after):,.2f} "
                f"win% {100*sum(1 for x in after if x>0)/len(after):.0f}",
                f"all others : n {len(base)} avg ${st.mean(base):,.2f} "
                f"win% {100*sum(1 for x in base if x>0)/len(base):.0f}",
            ],
        )

    # 6. First trade of day + next-day after a big-loss day
    by: dict = defaultdict(list)
    for f in closed:
        by[f.dt.date()].append(f)
    fl_tot, fw_tot, fl_red, saved = [], [], 0, 0.0
    for d, ts in by.items():
        ts.sort(key=lambda f: f.dt)
        first = u(ts[0])
        tot = sum(u(f) for f in ts)
        if first < 0:
            fl_tot.append(tot)
            fl_red += 1 if tot < 0 else 0
            saved += first - tot
        elif first > 0:
            fw_tot.append(tot)
    fl_lines = []
    if fl_tot:
        fl_lines.append(
            f"first trade LOST ({len(fl_tot)} days): ends red "
            f"{100*fl_red/len(fl_tot):.0f}% | avg day ${st.mean(fl_tot):,.0f}"
        )
    if fw_tot:
        fl_lines.append(
            f"first trade WON ({len(fw_tot)} days): "
            f"avg day ${st.mean(fw_tot):,.0f}"
        )
    if fl_tot:
        fl_lines.append(
            f">>> stopping after a losing first trade = "
            f"${saved:,.0f} swing over {len(fl_tot)} days"
        )
    dates = sorted(by)
    dtot = {d: sum(u(f) for f in by[d]) for d in dates}
    mloss = st.median(losses) if losses else r_unit
    ab, ao = [], []
    for i in range(1, len(dates)):
        (ab if dtot[dates[i - 1]] <= -2 * mloss else ao).append(dtot[dates[i]])
    if ab:
        fl_lines.append(
            f"day AFTER a big-loss day: n {len(ab)} avg ${st.mean(ab):,.0f} "
            f"(others avg ${st.mean(ao):,.0f})"
        )
    rep.add("6. FIRST-TRADE-OF-DAY + NEXT-DAY TILT", fl_lines)

    # 7. Sizing (futures) + averaging down
    fut = [(abs(f.qty), u(f)) for f in closed if f.asset == "Futures" and f.qty]
    sz_lines = []
    for lo, hi, lab in ((1, 1, "1"), (2, 3, "2-3"), (4, 9, "4-9"), (10, 1e9, "10+")):
        v = [p for q, p in fut if lo <= q <= hi]
        if v:
            sz_lines.append(
                f"{lab:4s} contracts: n {len(v):4d} exp ${st.mean(v):8.2f} "
                f"win% {100*sum(1 for x in v if x>0)/len(v):.0f} "
                f"net ${sum(v):,.0f}"
            )
    sz_lines.append(
        f"averaging-down events: {rec.avg_down_events} "
        f"across {rec.avg_down_legs} symbol-legs"
    )
    rep.add("7. SIZING vs OUTCOME + AVERAGING DOWN", sz_lines)

    # 8. Counterfactual replay
    def replay(level: int) -> tuple[int, float]:
        keep_sum = 0.0
        kept = 0
        for d in sorted(by):
            ts = sorted(by[d], key=lambda f: f.dt)
            cnt = 0
            daypnl = 0.0
            last_loss = None
            halted = False
            for f in ts:
                if level >= 1 and cnt >= 3:
                    continue
                if (
                    level >= 2
                    and last_loss
                    and (f.dt - last_loss).total_seconds() <= 600
                ):
                    continue
                if level >= 3 and halted:
                    continue
                keep_sum += u(f)
                kept += 1
                cnt += 1
                daypnl += u(f)
                if u(f) < 0:
                    last_loss = f.dt
                if level >= 3 and daypnl <= -2 * mloss:
                    halted = True
        return kept, keep_sum

    actual = sum(u(f) for f in closed)
    cf = [
        ("actual (no rules)", len(closed), actual),
        ("<=3 trades/day", *replay(1)),
        ("+ no trade <=10m after loss", *replay(2)),
        ("+ halt day after -2x med-loss", *replay(3)),
    ]
    rep.add(
        "8. CONTRACT COUNTERFACTUAL (rule-overlay on real fills)",
        [
            f"{lab:34s}: kept {k:4d} | sim ${s:12,.0f} "
            f"(vs actual {s-actual:+,.0f})"
            for lab, k, s in cf
        ],
    )

    # 9. Options autopsy
    opt = [c for c in closings if c.asset == _OPTIONS]
    if opt:
        long_o = [c.usd for c in opt if c.direction == "LONG"]
        short_o = [c.usd for c in opt if c.direction == "SHORT"]
        calls = [c.usd for c in opt if c.cp == "C"]
        puts = [c.usd for c in opt if c.cp == "P"]
        o_lines = [
            f"options closings {len(opt)} | net ${sum(c.usd for c in opt):,.0f}",
            f"LONG-bought n {len(long_o)} net ${sum(long_o):,.0f} | "
            f"SHORT-sold n {len(short_o)} net ${sum(short_o):,.0f}",
            f"CALLS net ${sum(calls):,.0f} | PUTS net ${sum(puts):,.0f}",
        ]
        for lo, hi, lab in ((-9, 0, "0DTE"), (1, 7, "1-7d"),
                            (8, 30, "8-30d"), (31, 90, "31-90d"),
                            (91, 9999, ">90d")):
            v = [c.usd for c in opt if c.dte is not None and lo <= c.dte <= hi]
            if v:
                o_lines.append(
                    f"  {lab:7s}: n {len(v):4d} net ${sum(v):10,.0f} "
                    f"exp ${st.mean(v):7.2f}"
                )
        rep.add("9. OPTIONS AUTOPSY (cross-instrument root-cause check)", o_lines)

    # 10. MES/MGC profile
    mm_lines = []
    for root in ("MES", "MGC"):
        g = [c for c in closings if c.sym.upper().startswith(root)]
        if not g:
            continue
        net = sum(c.usd for c in g)
        wr = 100 * sum(1 for c in g if c.usd > 0) / len(g)
        L = [c.usd for c in g if c.direction == "LONG"]
        S = [c.usd for c in g if c.direction == "SHORT"]
        mm_lines.append(
            f"{root}: n {len(g)} | net ${net:,.0f} | win% {wr:.0f} | "
            f"exp ${net/len(g):.2f} | LONG ${sum(L):,.0f} "
            f"SHORT ${sum(S):,.0f}"
        )
    if mm_lines:
        rep.add("10. MES / MGC PROFILE (Contract instruments)", mm_lines)

    # 11. 30-trade block variance
    s = [u(f) for f in sorted(closed, key=lambda f: f.dt)]
    blocks = [sum(s[i:i + 30]) for i in range(0, len(s) - 29, 30)]
    if blocks:
        bs = sorted(blocks)
        pos = sum(1 for b in blocks if b > 0)
        rep.add(
            "11. ANY 30-TRADE BLOCK (undisciplined baseline)",
            [
                f"{len(blocks)} non-overlapping blocks | "
                f"green {pos}/{len(blocks)} ({100*pos/len(blocks):.0f}%)",
                f"median ${st.median(blocks):,.0f} | p10 "
                f"${_pctile(bs,10):,.0f} | p90 ${_pctile(bs,90):,.0f} | "
                f"worst ${min(blocks):,.0f} | best ${max(blocks):,.0f}",
                "30 trades is high variance — judge process adherence, "
                "not 30-trade P/L.",
            ],
        )
    return rep
