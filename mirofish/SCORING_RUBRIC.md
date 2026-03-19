# MiroFish Scoring Rubric

> Score each MiroFish simulation report against this rubric before any client-facing use.
> Gate: Average score must be ≥3.5/5 across all dimensions before any client demo.

---

## Dimensions (score 1-5 each)

### 1. Accuracy
Does the report align with verifiable facts?
- 1: Major factual errors
- 2: Several inaccuracies
- 3: Mostly accurate, minor errors
- 4: Accurate with rare minor issues
- 5: Fully accurate, verifiable claims

### 2. Specificity
Are recommendations concrete or generic?
- 1: Entirely generic advice
- 2: Mostly platitudes
- 3: Mix of specific and generic
- 4: Mostly specific, actionable items
- 5: All recommendations are concrete with clear next steps

### 3. Format
Is the report clean, readable, and well-structured?
- 1: Disorganized, hard to follow
- 2: Rough structure, inconsistent formatting
- 3: Readable but could be cleaner
- 4: Well-structured with clear sections
- 5: Professional quality, ready for external delivery

### 4. Confidence Calibration
Does stated confidence match actual quality?
- 1: Wildly overconfident or underconfident
- 2: Frequently miscalibrated
- 3: Sometimes off, but direction is right
- 4: Well-calibrated with minor exceptions
- 5: Stated confidence accurately reflects evidence quality

### 5. Actionability
Can the reader take clear next steps?
- 1: No clear actions possible
- 2: Vague suggestions only
- 3: Some actionable items buried in text
- 4: Clear action items, mostly prioritized
- 5: Prioritized action list with timelines and owners

---

## Scoring Template

```markdown
## MiroFish Report Evaluation — [date]
- **Report:** [filename]
- **Topic:** [subject]
- **Agents:** [count] | **Rounds:** [count]

| Dimension | Score | Notes |
|-----------|-------|-------|
| Accuracy | /5 | |
| Specificity | /5 | |
| Format | /5 | |
| Confidence | /5 | |
| Actionability | /5 | |
| **Average** | **/5** | |

**Pass/Fail:** [≥3.5 = PASS]
**Improvement notes:** [what to change for next run]
```

---

## Validation Process

1. Run 3 sample reports on PAST events (last 30 days — outcomes verifiable)
2. Score each report against this rubric
3. Save scores to `~/openclaw/mirofish/validation-[date].md`
4. If average <3.5: identify failure mode, improve simulation parameters, re-score
5. If average ≥3.5: cleared for demo — but still Tier-2 approval before any client delivery
