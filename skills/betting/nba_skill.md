# NBA Betting Analysis Skill

## Context
Use this skill when analyzing NBA games, player props, or same-game parlays (SGPs). It provides the mathematical and situational heuristics required for the **CTE LOCKS** engine to identify edge cases.

## Instructions

### 1. Evaluate Advanced Metrics
- **NetRtg Analysis**: Identify the gap between teams. A gap of 5+ points is a high-conviction signal.
- **OffRtg vs DefRtg**: Calculate the "true scoring edge" by comparing offensive efficiency against opponent defensive efficiency.
- **Pace Mismatch**: Compare the model's expected total against the bookmaker's line. Lean Over/Under if the gap is >4 points.

### 2. Apply Situational Variables
- **Altitude Factor**: Add a +2.5 point edge for the Denver Nuggets in home games.
- **Rest Differential**: Prioritize teams with 2+ days of rest against opponents on 0 days of rest (+1.5-2 pts edge).
- **B2B Fatigue**: Flag veteran star props for a -3.5 point regression on the second night of a back-to-back.

### 3. Quantify Blowout & Usage
- **Blowout Risk**: If the spread is >10, discount "Over" on star props due to 4th quarter rest risk.
- **Usage Redistribution**: When a star is out, redistribute missing possessions to backups (typically 25-35% usage rise).

## Reference

### SGP Rules
- **Correlation**: Pair Team Total Over with Lead Playmaker Assists (proxy for pace).
- **Contradiction**: Avoid pairing Star Points Over with Team ML for heavy favorites (blowout rest kills the prop).

### Key Numbers
- Focus on margins of **3, 5, 7, and 10**. Moving across these numbers significantly impacts cover probability.

---
*Generated for the CTE LOCKS (Caveman Locks) Betting Engine.*
