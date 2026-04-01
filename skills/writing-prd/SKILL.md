---
name: writing-prd
description: Use when the user asks for a PRD, feature spec, or product requirements document, especially when inputs are incomplete and the final deliverable should also be exported as a Word document.
---

# Writing PRDs

## Overview

Write PRDs that are decision-ready, not presentation-ready. A good PRD defines the problem, target outcome, scope, and acceptance criteria without drifting into implementation design.

**Core principle:** If a requirement cannot be verified, scoped, or tied to a user/problem outcome, it does not belong in the PRD yet.

## When to Use

Use for:
- New feature PRDs
- Product requirement summaries
- MVP scope docs for design/engineering handoff
- Requests that explicitly need a Word deliverable

Do not use for:
- Technical design docs
- API/interface specs
- Project plans, task breakdowns, or sprint tickets

## Workflow

1. Fill the input gaps first.
2. Separate product requirements from implementation choices.
3. Produce a reviewable PRD.
4. Export the final document to Word.

If the user provides too little context, do not bluff. State assumptions explicitly or ask concise follow-up questions before writing the final PRD.

## Required Inputs

Before finalizing the PRD, get or infer:
- Problem statement
- Target users
- Business goal
- In-scope release boundary
- Out-of-scope items
- Success metrics
- Acceptance criteria
- Known constraints, dependencies, or risks

If any item is missing, add an `Assumptions` section or ask for it.

## PRD Structure

Use this order unless the user requests another format:

1. Summary
2. Background / problem
3. Goals
4. Non-goals
5. Users / scenarios
6. Requirements
7. Acceptance criteria
8. Metrics
9. Risks / dependencies
10. Open questions

## Rules

- Keep product intent and technical implementation separate.
- Write requirements as observable behavior, not architecture.
- Every goal must map to at least one metric or acceptance criterion.
- Every requirement should be testable by product, design, or engineering review.
- Mark assumptions clearly; do not hide them as facts.
- Prefer explicit scope cuts over vague “future optimization”.

## Requirement Pattern

Use requirement language like:

| Good | Bad |
|------|-----|
| “Users can schedule one message for a future send time.” | “Build a scheduler service backed by Redis.” |
| “Users can cancel a scheduled message before send time.” | “Use cron to manage retries.” |
| “If delivery fails, the sender sees the failure state.” | “Implement exponential backoff with a dead-letter queue.” |

## Metrics Pattern

Metrics must be measurable:

| Good | Bad |
|------|-----|
| “Scheduled-message send success rate >= 99.5%” | “Improve reliability” |
| “Adoption: 15% of weekly active senders use the feature in 30 days” | “Users like it” |
| “Manual follow-up sends drop 20% in target workflow” | “Reduce forgetfulness” |

## Common Mistakes

- Mixing PRD with system design
- Listing features without the user/problem context
- Writing goals that cannot be measured
- Missing non-goals, which causes scope creep
- Missing acceptance criteria, which blocks handoff

## Word Export

Final delivery should include a Word document when the user asks for one.

Preferred artifact set:
- `topic-prd.md` for editable source
- `topic-prd.html` for Word-friendly rich formatting
- `topic-prd.docx` as the final handoff file

Use the bundled template at `prd-template-zh.html` when writing Chinese PRDs. Replace bracketed placeholders with real content, keep headings stable, and preserve simple tables/bullets so Word conversion stays clean.

Recommended flow:

1. Write the source PRD in Markdown.
2. Fill `prd-template-zh.html` with the final content.
3. Export `.docx` from the HTML.

Export command:

```bash
textutil -convert docx topic-prd.html -output topic-prd.docx
```

For repeatability:
- Keep tables simple
- Avoid custom CSS and embedded assets unless necessary
- Use UTF-8 HTML
- Verify the `.docx` opens and headings/tables survive conversion

## Template Notes

The Chinese template is optimized for:
- Standard PRD section ordering
- Clear Word heading hierarchy
- Chinese body copy with basic typography
- Simple metadata and assumptions blocks

Reference example:
- `example-prd-zh.md` shows the expected level of detail, section quality, and measurable metrics for a Chinese PRD.

When filling the template:
- Replace every `[placeholder]`
- Delete sections that are truly empty instead of leaving placeholders behind
- Keep requirement statements and metrics specific and testable
- Do not add implementation architecture into the template body unless the user explicitly asks for a combined document

## Quick Reference

- Missing context: ask or add `Assumptions`
- Unsure about scope: add `Non-goals`
- Requirement sounds technical: rewrite as user-visible behavior
- Metric sounds vague: add a number, time window, and target population
- User wants Chinese Word output: start from `prd-template-zh.html`
- Need a quality bar: compare against `example-prd-zh.md`
- Final Word export: run `textutil -convert docx`
