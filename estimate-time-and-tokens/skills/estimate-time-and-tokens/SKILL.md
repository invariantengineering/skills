---
name: estimate-time-and-tokens
description: Use whenever proposing future work, presenting an implementation or remediation plan, offering to make changes, comparing approaches, or asking whether to proceed. Add an honest elapsed-time and token estimate for every proposed scope, including phrases such as "I can implement this," "proposed fix," "next steps," "should I proceed," or "would you like me to."
---

# Estimate Time and Tokens

Give the user a practical cost signal before they approve or choose proposed work.

## Estimate the complete scope

1. Identify the work being proposed. Include discovery, implementation, validation, review, and handoff when they are part of completing it.
2. Estimate wall-clock elapsed time for the agent to execute the work in the current environment, not the time a human engineer might bill.
3. Estimate total model-token use across the proposed work. Treat this as a forecast, not measured usage.
4. Use rounded ranges. Widen the range when the repository, failure mode, approval path, or test duration is uncertain.
5. Name the largest assumption or uncertainty only when it could materially change the estimate.

Do not pause solely to gather details needed for a precise estimate. State a conditional estimate from the known scope and identify the assumption that matters.

## Present estimates at the decision point

Place the estimate immediately after the proposed scope and before asking the user to proceed.

Use this compact default:

> Estimated effort: 20–30 minutes, roughly 8k–12k tokens.

Add one short qualifier when needed:

> Estimated effort: 30–50 minutes, roughly 12k–20k tokens. Biggest uncertainty: whether the full integration suite exposes related failures.

For multiple options, give each option its own estimate so the user can compare them. For work with independently useful phases, provide phase estimates and a total only when the breakdown improves the decision.

## Calibrate honestly

- Prefer ranges over point estimates and rounded values over false precision.
- Include likely tool latency, test runtime, and review time in the elapsed-time range.
- Increase both ranges for unfamiliar code, broad search, flaky tests, external approvals, or likely iteration.
- Decrease both ranges for localized, well-specified, mechanically verifiable changes.
- Keep time and tokens independently calibrated; a long-running build can consume time without many tokens.
- Never present an estimate as a guarantee or imply that forecast tokens are measured billing data.
- Never omit validation merely to make the estimate smaller.

## Re-estimate when reality changes

Refresh the estimate when the user changes scope or when inspection reveals a materially different task. Briefly state what changed. Do not repeat unchanged estimates in routine progress updates.

Do not add an estimate to a direct answer, completed result, or status report unless it also proposes additional future work.
