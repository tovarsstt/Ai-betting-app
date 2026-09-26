# UFC / MMA — NICHE HEURISTICS v1.0
# 🥊 Caveman Locks — fight-night edges

---

## ENGINE
- `POST /predict-ufc` (edge_api, port 8001) — full board from one fight model:
  Moneyline, Method (KO/Sub/Dec), Round O/U (1.5/2.5 + 3.5/4.5 for 5-round),
  Fight-goes-distance, per-round finish.
- Win prob: explicit estimate → devigged moneyline → 50/50.
- Method/round/distance: fighter finish profile (finish_rate, ko_share,
  sub_share) when known; else documented UFC empirical priors — **flagged in
  `used_empirical_priors`. Say "league-average prior" when you cite it, never
  present it as the fighter's real stat.**

---

## DATA POLICY (don't invent)
- Real, citeable: career record, finish rate, KO/Sub/Dec split, reach, age,
  recent layoff, weight-miss, opponent caliber. Cite only what you have.
- **Not available from odds alone**: cardio, fight IQ, chin durability trend.
  Do NOT fabricate. If unknown, lean on devigged ML + empirical priors and SAY SO.
- Empirical fallbacks: ~52% of modern UFC fights finish inside the distance;
  of finishes ~62% KO/TKO, ~38% submission; finishes skew early (R1 heaviest).

---

## MARKET PRIORITY (where the value lives)
**Moneyline** — cleanest in a competitive fight (fav win prob < ~66%).
- Devig the 2-way (no draw to model). Underdog +EV when model prob > devig.

**Method / Distance — the value play on juiced favorites.**
- A -300+ favourite pays poorly. When the model supports it, route to a
  better-paying derivative for the SAME read:
  - Heavy fav who FINISHES (high finish share) → **Fight does NOT go the distance**
    or **Fav by KO/TKO**. More money, model-backed.
  - Heavy fav who GRINDS (low finish share, decision merchant) → **Fav by Decision**
    or **Fight goes the distance**.
- This is the UFC analog of soccer draw-insurance: take the path the fighter
  actually wins by, at a better price than the short ML.

**Round Totals** — Under when one side is a clear early finisher; Over when both
are durable point-fighters / wrestlers. Lines split at the 2:30 mid-round mark.

**Parlays / SGP**
- Heavy finisher: Fav ML + Under 2.5 rounds + Fav by KO (correlated, same story).
- Durable matchup: Fight goes distance + Over 2.5 rounds.
- **Never**: Fav by KO + Fight goes the distance (contradictory — instant reject).

---

## FIGHT-LEVEL EDGES
- **5-round main events**: more total finish chances but decision rate still high;
  Over rounds is live. Cardio separates rounds 4-5.
- **Short-notice replacement**: fade their cardio in R3+; lean opponent late finish / decision.
- **Heavy weight-cut / missed weight**: fade their late-fight output; lean Under-the-opponent / opponent finish.
- **Big reach + strike volume vs pressure brawler**: KO-by-volume or decision play.
- **Elite grappler vs weak takedown defense**: submission method live, lower round.
- **Layoff > 18 months (ring rust)**: fade Over-rounds confidence; early-round chaos up.
- **Southpaw vs orthodox debut**: more clinch/scramble, slightly lower clean-finish rate.

## REFEREE / JUDGING
- Decision-heavy divisions (flyweight, bantamweight) → lean goes-distance / Over rounds.
- Quick-stoppage refs raise KO-method and Under-rounds value.
- Close decisions favor the Octagon-control / forward-pressure fighter on the cards.

---
*UFC v1.0 — Caveman Locks. Devig first, then take the fighter's real path to victory.*
