# MASTER PROMPT 02 — Product Research, Competitive Benchmark & Scope Decisions

## Mission
Produce actionable research, not copied UI, to improve the Smart Decor MVP and make a credible client proposal.

## Mandatory virtual team
Delegate internally to: CPO/product strategist (manager), UX researcher, interior-design domain expert, competitive intelligence analyst, SEO/content strategist, data/product analyst, and legal/ethics reviewer. The CPO signs the final recommendation.

## Allowed scope
Only `docs/research/**`, `docs/product/**`, and `docs/agent-reports/research-*`. Do not modify frontend/backend code, dependencies, migrations or CI. Create `integration-request.md` for implementation requests.

## Research duties
1. Study comparable products such as Havenly, Modsy-style room planners, Wayfair recommendation/filter experiences, Pinterest moodboards, Houzz and relevant Persian/Iranian services. Use official/public sources where possible; cite URLs and date accessed. Do not copy protected assets or claim undocumented features.
2. Compare onboarding, quiz design, recommendation explanations, moodboard editing, paywall, designer collaboration, catalog operations, trust signals and mobile UX.
3. Separate globally transferable patterns from Iran-specific needs: تومان, Persian RTL, local payment, seller links, trust and data privacy.
4. Create prioritized opportunities using RICE or MoSCoW. Keep MVP living-room scope intact.
5. Design a measurable experiment plan: activation, quiz completion, recommendation click-through, add-to-moodboard, seller click, Pro conversion and designer share completion.
6. Produce a decision log for every recommendation, including effort, risk, acceptance metric and whether it is MVP/P1/post-MVP.
7. Review SEO basics for public share pages and landing pages without expanding scope into a full content platform.

## Deliverables
`docs/research/competitive-benchmark.md`, `docs/product/mvp-priorities.md`, `docs/product/analytics-plan.md`, `docs/agent-reports/research-benchmark-report.md`, cited evidence and an implementation backlog. No code is considered required in this stage.

## Quality gate
Every claim has a source or is labeled hypothesis. Recommendations must map to a route, event, acceptance test or explicit out-of-scope decision. The manager rejects generic advice.

## Parallel protocol
Branch `agent/research-benchmark-<date>`; documentation only; no merge/cherry-pick/rebase of other agents.
