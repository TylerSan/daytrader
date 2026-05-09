# Night/Asia D-Archive Report Template

You are generating a D-only learning archive report. The US RTH session has closed.

## Required Sections (output MUST contain ALL of these in this order)

1. **🔒 Lock-in Metadata (compact)** — trades count + last trade summary; NO analysis
2. **📊 MES — Multi-TF (4H / 1H)** — overnight session bars
3. **📊 MNQ — Multi-TF**
4. **📊 MGC — Multi-TF**
5. **F. 期货结构 / Futures Positioning (compact)**: settlement + OI Δ + basis (if cash open)
6. **📰 Breaking News (past 4h)**
7. **D. Pattern Archive** — bar-by-bar pattern description per symbol; pattern_tags populated for future query
8. **📑 数据快照 / Data Snapshot**

## CRITICAL Output Constraints

- **NO A. section** (no recommendation — D purpose only).
- **NO B. section** (no narrative beyond fact statement).
- **NO C. section** (no plan recheck — overnight has no premarket plan to review).
- **NO sentiment block** — D purpose is descriptive archive, not decision aid.
- **D body is brief**: bar data + pattern description + news summary.
- **pattern_tags in frontmatter**: AI populates from observed patterns (e.g. ["bullish_engulf", "support_test", "doji_at_resistance"]).
- **news_event_tags in frontmatter**: AI populates (e.g. ["FOMC_minutes", "boj_intervention"]).

## Output Format Notes

- **Output MUST be in Chinese** (same style as premarket/EOD reports). Section headers and emoji may stay English (📊 Multi-TF, F. 期货结构, etc.) as anchors, but body content under each section must be Chinese. AI defaulting to English here would break consistency with the rest of the report family.
- Total length 3.5-5K characters.
- No preamble; start directly with the # heading.
- Frontmatter at top (YAML) with pattern_tags + news_event_tags arrays — these enable future programmatic query like "all bullish_engulf at support_test in last 30 days".
