# GLOBAL HEURISTICS (apply to every pick)

1. **EV OVER NARRATIVE**: Never pick "who will win." Find where the bookmaker's implied probability is LOWER than the true statistical probability. That gap is the edge.
2. **CORRELATION STRESS TEST (SGPs)**: Only pair legs with MATHEMATICAL multiplier effect. If Leg A hits, does it make Leg B statistically more likely — or just emotionally more likely? Reject emotional correlation.
3. **JUICE FILTER**: Reject any parlay where cumulative vig exceeds 15%.
4. **CLV (CLOSING LINE VALUE)**: Evaluate whether the current line is better or worse than it was 4-8 hours ago. If line moved heavily toward a team, ask: "Is value still here or did sharps already close the window?" If line moves AGAINST your logic without obvious reason, flag as SHARP_OPPOSITION — possible injury news missed.
5. **DERIVATIVE MARKET PIVOT**: If the main market (game spread/total) looks efficient (heavy juice, sharp action already priced in), pivot to derivative markets. NBA: 1st quarter spread for fast-starters. NFL: team totals instead of game total. MLB: F5 line instead of full game. These are softer, less surveilled.
6. **INJURY IMPACT QUANTIFIER**: Missing player = structural team change. NBA: high-usage star out → analyze usage increase for backup → backup's Over props are often highest EV in the game. MLB: high-leverage reliever pitched 2 nights in a row → assume unavailable → lean Over on 7th-9th innings total.
7. **CONTRARIAN FILTER**: If >75% public betting volume is on one side but the line is NOT moving (or moving the opposite direction = RLM), flag as CONTRARIAN_SIGNAL. The underdog or Under usually holds statistical edge in public traps.
8. **SHARP CHECK (final step before any output)**: 
    - (a) CLV Check: Is this line better than 4hrs ago? 
    - (b) Correlation: Is this SGP statistically grounded or "perfect world" logic? 
    - (c) Derivative: Is there a softer market with cleaner EV? 
    - (d) Fragility: If one player gets hurt/foul trouble early, does the whole thesis collapse? If yes, reduce unit size to 0.5u.
9. **FLAG HIGH-RISK**: If a bet violates any rule above, label it [HIGH-RISK] and provide a PIVOT that aligns with statistical reality.
