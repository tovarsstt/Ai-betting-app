import type { OddsEvent } from "./oddsService";
import { toDecimal } from "../utils/mathUtils.js";

export interface ArbitrageLeg {
  name: string;
  odds: number;
  book: string;
}

export interface ArbitrageOpportunity {
  game: string;
  market: string;
  legs: ArbitrageLeg[];
  totalImpliedProb: number;
  expectedReturn: number;
}

export class ArbitrageService {
  /**
   * Scans a list of events from the Odds API and detects arbitrage opportunities.
   * Covers ALL outcomes in the market (2-way ML, 3-way soccer with draw) —
   * an arb only exists if every outcome is bought below 100% combined.
   */
  static findOpportunities(events: OddsEvent[]): ArbitrageOpportunity[] {
    const opportunities: ArbitrageOpportunity[] = [];

    for (const event of events) {
      // We only scan H2H (Moneyline) for simplicity, but can expand to spreads/totals
      const marketKey = "h2h";

      const outcomesByName: Record<string, { price: number; book: string }[]> = {};
      let expectedLegCount = 0;

      for (const bookmaker of event.bookmakers) {
        const market = bookmaker.markets.find(m => m.key === marketKey);
        if (!market) continue;

        expectedLegCount = Math.max(expectedLegCount, market.outcomes.length);
        for (const outcome of market.outcomes) {
          if (!outcomesByName[outcome.name]) outcomesByName[outcome.name] = [];
          outcomesByName[outcome.name].push({ price: outcome.price, book: bookmaker.title });
        }
      }

      const names = Object.keys(outcomesByName);
      // Every outcome of the market must be priced somewhere, or the "arb" is fake
      if (names.length < 2 || names.length < expectedLegCount) continue;

      // Best odds for each outcome across all books
      const legs: ArbitrageLeg[] = names.map(name => {
        const best = outcomesByName[name].reduce((a, b) => (b.price > a.price ? b : a));
        return { name, odds: best.price, book: best.book };
      });

      const totalProb = legs.reduce((sum, leg) => sum + 1 / toDecimal(leg.odds), 0);

      // Arbitrage exists if combined implied probability < 1.0
      if (totalProb < 1.0) {
        opportunities.push({
          game: `${event.away_team} @ ${event.home_team}`,
          market: marketKey,
          legs,
          totalImpliedProb: totalProb,
          expectedReturn: (1 / totalProb) - 1
        });
      }
    }

    return opportunities;
  }
}
