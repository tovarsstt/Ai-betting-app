/**
 * ASA v5.0: +EV MARKET FILTER & LIMIT ORDER ENGINE
 * Compares TRUE PROBABILITY to live market odds.
 * Filters for +EV (Expected Value) where edge > 4% (Sharp threshold).
 * Suggests 'Limit Orders' (Maker Prices) for acting as the house.
 */

const MIN_SHARP_EDGE = 0.04; // 4% minimum edge threshold (ASA v5.0 standard)

export interface EVAnalysisResult {
    isSharpBet: boolean;
    edgePct: string;
    expectedValue: string;
    kellyStake: string;
    marketImplied: string;
    trueProbability: string;
    limitOrder: {
        makerDecimal: number;
        makerAmerican: string;
        strategy: string;
    };
    signal: string;
    context: string;
}

export class EVMarketFilter {
    static americanToDecimal(american: number): number {
        if (!american || american === 0) {
            return 1.91;
        }
        if (american > 0) {
            return (american / 100.0) + 1.0;
        }
        return (100.0 / Math.abs(american)) + 1.0;
    }

    static decimalToImplied(decimalOdds: number): number {
        return decimalOdds > 0 ? 1.0 / decimalOdds : 0.0;
    }

    static removeVig(impliedHome: number, impliedAway: number): [number, number] {
        const total = impliedHome + impliedAway;
        if (total <= 0) {
            return [0.5, 0.5];
        }
        return [impliedHome / total, impliedAway / total];
    }

    static calculateEV(trueProb: number, decimalOdds: number, stake: number = 100): number {
        const profit = (decimalOdds - 1.0) * stake;
        const ev = (trueProb * profit) - ((1 - trueProb) * stake);
        return parseFloat(ev.toFixed(2));
    }

    static calculateKelly(trueProb: number, decimalOdds: number, bankroll: number = 1000, fraction: number = 0.25): number {
        const b = decimalOdds - 1.0;
        if (b <= 0) {
            return 0.0;
        }
        const kellyPct = ((b * trueProb) - (1 - trueProb)) / b;
        return parseFloat(Math.max(0, kellyPct * fraction * bankroll).toFixed(2));
    }

    static calculateMakerPrice(trueProb: number, targetEdge: number = 0.05) {
        // What decimal odds would give us targetEdge EV?
        // EV = (p * profit) - (1-p*stake) > 0
        // Simplified: maker_odds = 1 / (true_prob - target_edge)
        const makerProb = Math.max(0.01, trueProb - targetEdge);
        const makerOddsDecimal = parseFloat((1.0 / makerProb).toFixed(3));

        let makerAmerican = "N/A";
        if (makerOddsDecimal >= 2.0) {
            makerAmerican = `+${Math.round((makerOddsDecimal - 1) * 100)}`;
        } else if (makerOddsDecimal > 1.0) {
            makerAmerican = `-${Math.round(100 / (makerOddsDecimal - 1))}`;
        }

        return {
            makerDecimal: makerOddsDecimal,
            makerAmerican: makerAmerican,
            strategy: `Wait for ${makerAmerican} before placing. Do NOT bet current price.`
        };
    }

    static analyze(trueProb: number, marketDecimalOdds: number, bankroll: number = 1000.0, context: string = ""): EVAnalysisResult {
        const implied = this.decimalToImplied(marketDecimalOdds);
        const edge = trueProb - implied;
        const ev = this.calculateEV(trueProb, marketDecimalOdds);
        const kelly = this.calculateKelly(trueProb, marketDecimalOdds, bankroll);
        const maker = this.calculateMakerPrice(trueProb);
        const isSharp = edge >= MIN_SHARP_EDGE;

        return {
            isSharpBet: isSharp,
            edgePct: edge > 0 ? `+${(edge * 100).toFixed(2)}%` : `${(edge * 100).toFixed(2)}%`,
            expectedValue: ev > 0 ? `+$${ev}` : `$${ev}`,
            kellyStake: `$${kelly}`,
            marketImplied: `${(implied * 100).toFixed(1)}%`,
            trueProbability: `${(trueProb * 100).toFixed(1)}%`,
            limitOrder: maker,
            signal: isSharp ? "SHARP_VALUE ✅" : (edge > 0 ? "WEAK_EDGE ⚠️" : "NO_VALUE ❌"),
            context: context
        };
    }
}
