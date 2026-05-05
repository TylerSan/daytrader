# EOD Daily Report Template

You are generating an end-of-day report. Today's market session has closed (RTH cash close at 13:00 PT for ES/NQ; futures globex still active).

## Required Sections (output MUST contain ALL of these in this order)

1. **🔒 Lock-in Metadata**: today's trades count update, daily R, week R, cool-off entering tomorrow
2. **📊 MES — Multi-TF (W / D / 4H)**: today's close updates per TF
3. **📊 MNQ — Multi-TF** (context only)
4. **📊 MGC — Multi-TF**
5. **🌐 Cross-Asset Narrative** (today past-tense; NO predictions)
6. **📰 Breaking News (today)** (web search if D. Sentiment block doesn't already cover it)
7. **F. 期货结构 / Futures Positioning** (post-cash-close basis + term + RTH-formed VP — embed verbatim from input)
8. **D. 情绪面 / Sentiment Index** (embed verbatim from sentiment_md input)
9. **今日交易档案 / Today's Trade Archive** (trade ledger table + §6 / §9 audit; if 0 trades, render "今天没交易. 原因: [analysis]")
10. **🔄 Plan Retrospective / 计划复盘** (per-level table per symbol + plan accuracy summary + iteration insight; embed verbatim from retrospective_md input)
11. **C. 计划复核 / Plan Adherence Assessment**: VERBATIM quote of today's premarket C-MES / C-MGC blocks (embed from today_plan_blocks input), then plan-vs-actual comparison
12. **B. 市场叙事 / Today's Narrative** (past-tense; FORBIDDEN: forward-looking predictions — that's premarket's job)
13. **📅 Tomorrow Preliminary Plan** (use tomorrow_preliminary_md input; mark "preliminary — premarket 06:00 PT will finalize")
14. **📑 数据快照 / Data Snapshot** (key numbers in compact table)

## CRITICAL Output Constraints

- **NO A. section** (decision aid is forbidden in EOD per spec §6). The A 段 (建议 / Recommendation) is reserved for the premarket report only — EOD is descriptive/retrospective, not prescriptive.
- **B is past-tense**: describe what happened, NOT what will happen.
- **C must verbatim-quote today's premarket plan** before adding adherence commentary.
- **🔄 Plan Retrospective and 📅 Tomorrow Preliminary**: embed the input markdown VERBATIM; do NOT re-summarize.
- **Sources**: when web search is used (econ calendar for tomorrow, news verification), cite at least 3 real URLs at the end.

## Output Format Notes

- Use Chinese where input data is Chinese; mixed Chinese/English is acceptable.
- Total length 6.5–9K characters (per spec §2.2).
- No preamble; start directly with the # heading.
