/**
 * SwarmPredictor module simulating a MiroFish-like Swarm Intelligence architecture.
 * This spins up lightweight 'Agents' representing different market personas (Bull, Bear, Statistical, Sentiment)
 * to debate an outcome, yielding a unified Swarm Consensus Factor and Confidence Score.
 */

export interface SwarmSimulationParams {
    eventTitle: string;
    impliedOdds: number; // 0 to 1
    historicalWinRate: number; // 0 to 1
    newsSentimentScore: number; // -1 to 1 (-1 extreme negative, 1 extreme positive)
}

export interface SwarmConsensus {
    predictedProbability: number;
    swarmConfidence: number; // 0 to 1
    debateSummary: string;
}

export class SwarmPredictor {
    /**
     * Executes a mock multi-agent debate based on the input parameters.
     * In a live environment, this could hook directly into an LLM provider to run actual prompt chains.
     */
    static runSimulation(params: SwarmSimulationParams): SwarmConsensus {
        // Personas
        const statAgent = { weight: 0.4, estimate: params.historicalWinRate };
        
        let sentimentAgentEstimate = 0.5; // neutral base
        if (params.newsSentimentScore > 0.5) sentimentAgentEstimate = 0.8;
        else if (params.newsSentimentScore < -0.5) sentimentAgentEstimate = 0.2;
        const sentimentAgent = { weight: 0.3, estimate: sentimentAgentEstimate };

        const marketAgent = { weight: 0.3, estimate: params.impliedOdds };

        // Swarm resolution logic
        const rawPrediction = (statAgent.estimate * statAgent.weight) +
                              (sentimentAgent.estimate * sentimentAgent.weight) +
                              (marketAgent.estimate * marketAgent.weight);

        // Calculate variance amongst agents to determine Swarm Confidence
        const estimates = [statAgent.estimate, sentimentAgent.estimate, marketAgent.estimate];
        const variance = this.calculateVariance(estimates);
        
        // High variance = low confidence, low variance = high confidence
        const swarmConfidence = Math.max(0, 1 - Math.sqrt(variance));

        return {
            predictedProbability: parseFloat(rawPrediction.toFixed(4)),
            swarmConfidence: parseFloat(swarmConfidence.toFixed(4)),
            debateSummary: `Swarm resolved. Statistical Agent leaned ${statAgent.estimate.toFixed(2)}, Sentiment Agent leaned ${sentimentAgent.estimate.toFixed(2)}, Market Agent leaned ${marketAgent.estimate.toFixed(2)}.`
        };
    }

    private static calculateVariance(values: number[]): number {
        const mean = values.reduce((a, b) => a + b) / values.length;
        const squareDiffs = values.map(v => Math.pow(v - mean, 2));
        return squareDiffs.reduce((a, b) => a + b) / values.length;
    }
}
