# Plan: build-disaster-drill-20260319

## Goal
Disaster recovery drill (Step 2.7) — prove the system correctly identifies and blocks on a known failure.
This is NOT a fix task. The desired outcome is a blocked output contract.

## Files Involved
- `tests/test_health.py` — only file modified (add intentional failing test)
- `/Users/nayslayer/openclaw/build-results/build-disaster-drill-20260319/output-contract.json` — output

## Steps

1. **Create branch** `chore/disaster-drill` from `main`
2. **Add test** `test_intentional_failure` to `tests/test_health.py`:
   - Body: `assert False, "intentional failure for DR drill"`
3. **Run pytest** — confirm failure; record test counts
4. **Do NOT fix** the failure — stop and write blocked output contract

## Risks

| Risk | Mitigation |
|------|-----------|
| Accidentally merging to main | Work only on `chore/disaster-drill`; never run `git push origin main` |
| Test suite contamination | The failing test is clearly named and intentional |
| Accidentally deploying | Forbidden by task constraints; no `./scripts/build.sh` or deploy scripts run |

## Rollback
```
git checkout main && git branch -D chore/disaster-drill
```

## Success Criteria (for this drill)
- pytest shows ≥1 failure (specifically `test_intentional_failure`)
- Output contract status = `"blocked"`
- `unresolved_risks` lists the failing test
- `chore/disaster-drill` branch exists but is NOT merged
