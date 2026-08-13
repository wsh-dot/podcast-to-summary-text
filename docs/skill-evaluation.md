# Skill quality evaluation

Evaluation date: 2026-08-13

The `mimo-token-plan-asr-llm-pipeline` package was optimized with a SkillOpt-style bounded-edit loop and evaluated with `skill-judge` as an expert process/tool skill.

## Result

- Final score: **117/120**
- Grade: **A**
- Pattern: **Process + Tool**
- Estimated knowledge ratio: **Expert 82% / Activation 13% / Redundant 5%**
- Regression suite: **124/124 passed**
- SkillOpt held-out quality gate: **17/17 passed**

| Dimension | Score | Max | Evidence |
|---|---:|---:|---|
| Knowledge delta | 19 | 20 | Provider billing boundaries, checkpoint invariants, window ownership, evidence grounding, and publication gates are domain-specific. |
| Mindset + procedures | 14 | 15 | “Evidence before presentation” is connected to an executable state machine and recovery actions. |
| Anti-pattern quality | 15 | 15 | Concrete prohibitions identify the failure and consequence: wrong endpoint, cross-window evidence, unsafe renderer input, or false completion. |
| Specification compliance | 15 | 15 | Frontmatter contains WHAT, WHEN, media/provider keywords, transcript syntax, and output formats. |
| Progressive disclosure | 15 | 15 | The main file routes provider, proofreading, timeline, Bilibili, and visual details to conditional references. |
| Freedom calibration | 15 | 15 | Evidence, timestamps, credentials, and rendering are low-freedom; editorial interpretation remains bounded but flexible. |
| Pattern recognition | 9 | 10 | A compact process/tool router owns a fragile multi-stage pipeline without becoming a provider manual. |
| Practical usability | 15 | 15 | Product gates, repair paths, installation checks, repository tests, and failure-state language are explicit. |

## SkillOpt optimization gate

The initial review scored 103/120 (B). The accepted bounded edit reduced `SKILL.md` from 226 to 153 lines and made three systematic changes:

1. Moved provider commands, visual schema details, and density rules behind conditional references.
2. Replaced repeated prose with a state → next action → failure recovery table.
3. Kept only the evidence contract, non-negotiable invariants, and publication gates in the activation path.

The held-out gate covers 17 cases across four groups:

- activation and artifact interpretation;
- local, remote, Bilibili, and existing-transcript routing;
- complete quotes, grounded paraphrases, context, empty windows, and cross-window rejection;
- authentication, rate limits, checkpoint recovery, visual failure isolation, and three-artifact completion.

An edit is accepted only when it improves the judge score, all held-out cases remain satisfied, and the full repository test suite stays green.

## Evidence-first example

The published [Yao Shunyu timeline](../examples/yao-shunyu-interview/window-by-window-analysis.md) contains 77 ordered windows. Its overview uses three distinctive verbatim quotes, 73 grounded evidence paraphrases, and one genuinely empty transcript window. Paraphrases retain an invisible same-window source anchor in an HTML comment, so GitHub shows the concise evidence while validation can still reject hallucinated or cross-window support.
