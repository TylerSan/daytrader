# Intraday 4H Report Template

You are generating an intraday 4-hour cadence report. Today's RTH session is in progress.

## Required Sections (output MUST contain ALL of these in this order)

1. **🔒 Lock-in Metadata**: today's trades count update, daily R so far, week R, position state
2. **📊 MES — Multi-TF (D / 4H / 1H)**: today's bars analysis per TF
3. **📊 MNQ — Multi-TF** (context only)
4. **📊 MGC — Multi-TF**
5. **🌐 Cross-Asset Narrative** (so far today)
6. **📰 Breaking News (past N hours)** — N = 1h for 4h-1, 5h for 4h-2
7. **F. 期货结构 / Futures Positioning** (basis + term + RTH-formed VP — embed verbatim from input)
8. **D. 情绪面 / Sentiment Index** (verbatim from sentiment_md input — may be from premarket cache for 4h-1 or refreshed for 4h-2)
9. **今日交易档案 / Today's Trade Archive (since 06:30 PT)** — light list table only (NO §6/§9 audit; that's EOD's job)
10. **🔄 Plan Retrospective / 计划复盘** — **4h-2 ONLY**; 4h-1 must omit this entire section and instead show "下次复盘 4h-2 (11:00 PT)" placeholder
11. **C. 计划复核 / Plan Adherence Assessment**: VERBATIM quote of today's premarket C-MES / C-MGC blocks (embed from today_plan_blocks input), then plan-vs-actual comparison
12. **B. 市场叙事 / Today's Narrative (so far)** (past-tense for the period 06:30 PT → now; FORBIDDEN: forward predictions for rest of session)
13. **A. 建议 / Recommendation (rest-of-session)** — A-3 default (ladder of trigger conditions); A-2 escalation if conditions met; **NO A-1** (direct buy/sell calls). Mixed form A.3: each instrument has mini-A inside F section; main A is cross-instrument integration.
14. **📑 数据快照 / Data Snapshot** (key numbers in compact table)

## CRITICAL Output Constraints

- **C must verbatim-quote today's premarket plan** before adding adherence commentary.
- **B is past-tense**: describe what happened so far today, NOT what will happen.
- **A is forward-looking** but uses A-3 ladder, NOT direct calls.
- **🔄 Plan Retrospective**: 4h-2 only. 4h-1 explicitly says "retrospective deferred to 4h-2".
- **Sources**: when web search is used, cite real URLs at end.

## Output Format Notes

- Use Chinese where input data is Chinese; mixed Chinese/English is acceptable.
- Total length 5-7K characters (per spec §2.2).
- No preamble; start directly with the # heading.
