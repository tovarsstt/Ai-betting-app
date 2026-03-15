/**
 * Calculates metabolic cost based on time-zone delta, travel miles, and altitude.
 * Goal: Quantify the 'Circadian Friction' (CF) variable for XGBoost.
 */
export class CircadianFriction {
    // Coordinates and altitudes for key sports cities (simplified for demonstration)
    // In production, this would be a full CSV or DB lookup
    static cityLatLong: Record<string, [number, number, number]> = {
        "Lakers": [34.05, -118.24, 0],    // LA (Alt 0 is placeholder for sea level)
        "Knicks": [40.71, -74.00, 0],     // NYC
        "Nuggets": [39.73, -104.99, 5280], // Denver (High Altitude)
        "Celtics": [42.36, -71.05, 0],    // Boston
        "Heat": [25.76, -80.19, 0]        // Miami
    };

    /** Haversine formula to calculate travel distance in miles. */
    static calculateDistance(origin: string, destination: string): number {
        if (!this.cityLatLong[origin] || !this.cityLatLong[destination]) {
            return 500; // Default fallback
        }
            
        const [lat1, lon1] = this.cityLatLong[origin];
        const [lat2, lon2] = this.cityLatLong[destination];
        
        const R = 3958.8; // Earth radius in miles
        const phi1 = (lat1 * Math.PI) / 180;
        const phi2 = (lat2 * Math.PI) / 180;
        const dphi = ((lat2 - lat1) * Math.PI) / 180;
        const dlambda = ((lon2 - lon1) * Math.PI) / 180;
        
        const a = Math.sin(dphi/2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dlambda/2) ** 2;
        return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    /**
     * Computes the CF Variable.
     * CF = (Distance_Weight * (Log10(Miles) / Days_Rest)) + (Timezone_Penalty * Hour_Delta) + (Altitude_Tax)
     */
    static calculateCF(originTeam: string, destinationTeam: string, daysSinceLastGame: number): number {
        const miles = this.calculateDistance(originTeam, destinationTeam);
        
        // 1. Distance Stress (Logarithmic)
        const distanceStress = Math.log10(Math.max(1, miles)) / Math.max(1, daysSinceLastGame);
        
        // 2. Timezone Shift (Metabolic Jetlag)
        // Simplified: Each 15 degrees longitude is roughly 1 hour
        const lon1 = this.cityLatLong[originTeam] ? this.cityLatLong[originTeam][1] : 0;
        const lon2 = this.cityLatLong[destinationTeam] ? this.cityLatLong[destinationTeam][1] : 0;
        const tzDelta = Math.abs(lon2 - lon1) / 15.0;
        const tzPenalty = Math.pow(tzDelta, 1.5) / Math.max(1, daysSinceLastGame);
        
        // 3. Altitude Taxonomy
        const altOrigin = this.cityLatLong[originTeam] ? this.cityLatLong[originTeam][2] : 0;
        const altDest = this.cityLatLong[destinationTeam] ? this.cityLatLong[destinationTeam][2] : 0;
        let altitudeTax = 0;
        if (altDest > 3000 && altOrigin < 1000) {
            altitudeTax = 1.25; // Significant disadvantage for unacclimated teams
        }
            
        const cfScore = (distanceStress * 0.4) + (tzPenalty * 0.5) + (altitudeTax * 0.1);
        
        return parseFloat(cfScore.toFixed(4));
    }
}
