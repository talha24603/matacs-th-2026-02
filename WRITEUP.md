# Design write-up: AI proposal triage

**In one line:** AI *reads* proposals and pulls out facts with quotes as proof. Code *scores* them with the admin's formulas. A person checks anything uncertain and makes the award.

Flow diagram: [diagram/process-flow.png](diagram/process-flow.png). Sample result: [ranking.json](ranking.json).

## 1. AI vs. rules

| Step | Who | Why |
|---|---|---|
| PDF to text, file hash | Code | Mechanical work |
| Scan for suspicious wording ("rank it first", "automated review") | Code | Cheap, predictable, can't be talked out of it |
| **Read proposal, answer the criteria questions, quote evidence** | **AI** | Proposals are free text with many wordings ("since 2021", "past four years", "subcontractor to be confirmed"). Rules for this would be brittle. |
| Check each AI quote really appears in the text | Code | Catches made-up facts |
| Mandatory pass/fail, budget and 16-week limits | Code | Yes/no checks. They must never vary. |
| Weighted scores, ranking, reason text | Code | Arithmetic from admin formulas. Repeatable and auditable. |
| Confirm flags, overrides, award | Human | Judgement and accountability |

The line: **AI turns messy text into structured facts. Everything after that is deterministic.** The AI never sees the weights and never produces a score, so it can't drift on scores or be talked into them.

## 2. Consistency and explainability

- **Repeatable:** every score is a formula over extracted facts (for example price: full marks at $208k or less, zero at the $260k ceiling, linear in between). Same facts give the same score every time.
- **Extraction is cached.** Facts are stored by file hash + criteria version + prompt version + model. Ranking the same files twice reuses the stored facts, so the result is **identical**. A fresh re-extraction might word a note differently, but the facts are concrete numbers and yes/no answers, and the quote check rejects anything unsupported. Optionally extract twice and flag any field where the runs disagree.
- **Explainable:** for each proposal the reviewer sees the points per criterion, the fact behind each one, and the quoted sentence with page number, which they can click to see in the PDF. For example, A's line reads "price $238,000 (10.6/25) … team 4/4 (15.0/15)". The reason text is built by code from that breakdown, so it can't state anything the evidence doesn't.

## 3. Human in the loop

1. **Admin setup:** defines criteria, weights (the tool blocks publishing unless they total 100%) and scoring anchors, then publishes a version.
2. **Review queue (before results are final):** any flag stops a proposal from being ranked until a reviewer acts. Flags: mandatory item unclear, required value missing, quote not found, suspected manipulation, experience period outside 5 years. The reviewer can confirm, correct a fact (with a reason), mark it ineligible, or request clarification from the bidder.
3. **Ranking review and award:** the reviewer can override a rank (reason required). The tool recommends; a person decides the award.

**Audit log, per proposal:** file hash; extracted text; criteria version; prompt version; model id and request id; raw AI output; quote-check results; scoring code version; score breakdown; every flag; every override (who, when, old value, new value, reason); final decision. From this, any result can be reproduced exactly.

## 4. Changing criteria

Criteria are **versioned, never edited in place**. Every scoring run is tied to one version, and a ranking never mixes versions.

- **Weights or scoring anchors change:** scores are recalculated from the stored facts straight away. No AI call, no cost.
- **New or reworded criterion:** only the new or changed questions are sent to the AI again.
- Earlier results stay visible, labelled "scored under v1", with a banner saying they are out of date until re-run. Human corrections carry forward when the field still exists; otherwise they are flagged for a second look.
- A mid-evaluation change records who made it and why, and shows rankings under both versions, because changing weights after seeing scores could be used to favour a bidder.

## 5. Risks and safeguards

| Risk | Safeguard |
|---|---|
| **Wrong extraction** (misread number, "not mentioned" vs "no") | Quote required for every answer; code checks the number appears in the quote; null means "not stated" and goes to a human, never a silent zero on mandatory items |
| **Made-up facts** | A quote not found in the document means the value is discarded and flagged. The AI writes no free-text reasons. |
| **Manipulation / prompt injection** (Proposal C) | Proposal is wrapped and labelled as untrusted data; AI told to report, not follow, instructions; separate code pattern scan; AI has no power over scores anyway. A hit flags the proposal for a human. |
| **Bias** (polished or long proposals win; brand names) | Scores come only from facts, so writing style earns nothing. Each proposal is read on its own, so bids don't influence each other. Bidder names could be hidden from reviewers until ranking. |
| **Missing information punishes short bids** | Missing hard requirement = flag + "request clarification", not automatic rejection (Proposal D) |
| **Cost** | One AI call per proposal; cached results; weight changes cost nothing; smallest model that passes the checks |

## Sample set

A ranks 1st (73.6) and E 2nd (58.5). D is **flagged** because it has no committed schedule. C is **flagged** because of the embedded instruction to automated reviewers. B is **ineligible** because the bidder holds no licence. The full breakdown is in the [README](README.md#sample-ranking-walkthrough) and [ranking.json](ranking.json).

**Assumptions** (not confirmed with MATACS): evaluation date October 2026, so "last 5 years" means projects since 2021, judged by year; "named project lead" is accepted as stated even when the name is not printed; "monitoring plan" means system performance monitoring after installation, not construction progress reports (this cost C a point); scoring anchors (full marks at 15 installs, 8 weeks, 20% under budget, 15-year workmanship warranty) are example admin settings. They change scores, not eligibility.
