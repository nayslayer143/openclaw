
## 2026-04-05 05:20

**Regime:** trending (confidence: 80%)

**Alerts:**
- RivalClaw: The 'fair_value_directional' strategy is showing clear performance degradation when the predictive edge is low; immediate filtering is required.
- QuantumentalClaw: The 'asymmetry' module accuracy is trending downward; investigate data source integrity or concept drift for this module.

**Lessons extracted:** 6
- [rivalclaw] The 'fair_value_directional' strategy shows high consistency in generating profitable trades when the edge is high (e.g., 0.888, 0.899), suggesting it performs well in predictable, high-edge environments.
- [rivalclaw] Trades with low 'edge' values (e.g., 0.164, 0.219) are correlated with losses, indicating the strategy is over-leveraging when predictive edge is weak.
- [quantclaw] The weight adjustments are stable, showing consistent weight allocation across 'narrative', 'event', and 'edgar' modules, suggesting the model is in a stable learning phase.
- [quantclaw] The 'asymmetry' module's accuracy shows a slight, gradual decline over the last 24 hours (from 0.3628 to 0.3422), suggesting diminishing returns or concept drift.
- [cross-system] Both systems are operating under conditions where high-confidence, short-term signals (sprint/day) are being generated, suggesting a period of high, actionable market activity.
- ... and 1 more

---
