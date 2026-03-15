export interface AnalysisRequest {
    sport: string;
    matchup: string;
    context: string;
    isMoonshot?: boolean;
    isQuickMoney?: boolean;
    isBankrollRecovery?: boolean;
    isGrader?: boolean;
    isNBAPlayerProps?: boolean;
    isAlphaScan?: boolean;
    onRetry?: () => void;
}

export class BettingAIService {
    constructor() {
        // API Key is now handled by the backend
    }

    /**
     * v600.0 ULTRON COGNITIVE BEHAVIORAL ENGINE
     * Optimized for psychological market analysis.
     */
    private async retryWithBackoff<T>(fn: () => Promise<T>, retries = 2, delay = 4000, onRetry?: () => void): Promise<T> {
        try {
            return await fn();
        } catch (error: any) {
            const status = error.status || error.response?.status;
            const errorMsg = error.message?.toLowerCase() || "";
            const isRateLimit = status === 429 || status === 503 || errorMsg.includes("429") || errorMsg.includes("503") || errorMsg.includes("resource exhausted") || errorMsg.includes("too many requests") || errorMsg.includes("quota") || errorMsg.includes("fetch");

            if (isRateLimit && retries > 0) {
                console.warn(`🏦 APEX ROUTING: Congestion detected (${status}). Re-syncing in ${delay}ms... (${retries} retries left)`);
                if (onRetry) onRetry();
                await new Promise(res => setTimeout(res, delay));
                return this.retryWithBackoff(fn, retries - 1, delay * 2, onRetry);
            }

            if (isRateLimit) {
                throw new Error("RATE_LIMIT");
            }

            console.error("Fatal API Error in Engine:", error);
            throw error;
        }
    }

    async analyzeMatchup(request: AnalysisRequest): Promise<string> {
        return await this.retryWithBackoff(async () => {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sport: request.sport,
                    matchup: request.matchup,
                    context: request.context,
                    sharpOdds: 1.90, // Placeholder for future integration
                    softOdds: 2.10   // Placeholder for future integration
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || "Backend Analysis Failed");
            }

            const data = await response.json();
            return JSON.stringify(data, null, 2);
        }, 5, 10000, request.onRetry);
    }

    async verifyOdds(sport: string): Promise<string> {
        return this.analyzeMatchup({
            sport,
            matchup: "LIVE ODDS CHECK",
            context: `Identify the highest efficiency Stake.com lines for ${sport} on ${new Date().toLocaleDateString()}.`
        });
    }

    async gradeSlip(slipText: string): Promise<string> {
        return this.analyzeMatchup({
            sport: "MULTI",
            matchup: "BET SLIP AUDIT",
            context: slipText,
            isGrader: true
        });
    }
}

export const bettingAIService = new BettingAIService();
