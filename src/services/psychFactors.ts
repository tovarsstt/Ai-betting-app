/**
 * Implements 'The Tilt Tensor' and 'Fatigue Decay' logic along with 'Swarm Consensus'.
 */

import { SwarmPredictor } from './swarmPredictor';
import type { SwarmSimulationParams, SwarmConsensus } from './swarmPredictor';

export class PsychFactors {
    /**
     * Quantifies a team's performance variance after a 'High-Stress/Low-Outcome' event.
     * Tilt = (abs(Actual_Margin - Spread) / Time_Delta) * Impact_Weight
     */
    static calculateTiltTensor(lastGameMargin: number, spreadDiff: number, isLoss: boolean = true): number {
        if (!isLoss) {
            return 0.0; // Positive wins rarely cause 'tilt' in the same negative sense
        }
        
        // A 'heartbreaking loss' is one where they lost by more than the spread in a close game,
        // or lost a game they were heavily favored in.
        const stressScore = Math.abs(lastGameMargin - spreadDiff);
        
        // Normalize stress score to [0, 1]
        const tiltFactor = Math.min(1.0, stressScore / 20.0);
        return parseFloat(tiltFactor.toFixed(4));
    }

    /**
     * Recovery-curve variable (R) based on minutes played in a rolling 7-day window.
     * Fatigue = 1 - exp(-minutes / Baseline)
     */
    static calculateFatigueDecay(minutesPlayed7d: number): number {
        // Baseline: 120 minutes in 7 days is high for a star, 240 for a team average?
        // Let's say 200 minutes is the 'red zone'.
        const baseline = 200.0;
        const rValue = 1 - Math.exp(-minutesPlayed7d / baseline);
        return parseFloat(rValue.toFixed(4));
    }

    /**
     * Integrates Swarm Intelligence by running a multi-agent debate simulation.
     * The resulting swarm confidence is combined with negative psych factors (Tilt, Fatigue)
     * to provide a final Confluence Multiplier.
     */
    static getSwarmConfluenceMultiplier(swarmParams: SwarmSimulationParams, tiltFactor: number, fatigueDecay: number): number {
        const consensus: SwarmConsensus = SwarmPredictor.runSimulation(swarmParams);
        
        // Base multiplier starts at Swarm predicted probability
        const baseMultiplier = consensus.predictedProbability;
        
        // If swarm confidence is very high, it mitigates some tilt/fatigue
        const confidenceBuffer = consensus.swarmConfidence * 0.5; // Up to 50% buffer

        // Effective negative factors
        const effectiveTilt = Math.max(0, tiltFactor - confidenceBuffer);
        const effectiveFatigue = Math.max(0, fatigueDecay - (confidenceBuffer / 2));

        // Penalty application
        const finalMultiplier = baseMultiplier * (1 - effectiveTilt) * (1 - effectiveFatigue);
        
        // Return bounded [0, 1]
        return parseFloat(Math.max(0, Math.min(1, finalMultiplier)).toFixed(4));
    }
}
