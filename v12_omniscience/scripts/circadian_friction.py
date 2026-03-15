import numpy as np
import math
from datetime import datetime

class CircadianFriction:
    """
    Calculates metabolic cost based on time-zone delta, travel miles, and altitude.
    Goal: Quantify the 'Circadian Friction' (CF) variable for XGBoost.
    """
    
    def __init__(self):
        # Coordinates and altitudes for key sports cities (simplified for demonstration)
        # In production, this would be a full CSV or DB lookup
        self.city_lat_long = {
            "Lakers": (34.05, -118.24, 0),    # LA (Alt 0 is placeholder for sea level)
            "Knicks": (40.71, -74.00, 0),     # NYC
            "Nuggets": (39.73, -104.99, 5280), # Denver (High Altitude)
            "Celtics": (42.36, -71.05, 0),    # Boston
            "Heat": (25.76, -80.19, 0)        # Miami
        }

    def calculate_distance(self, origin, destination):
        """Haversine formula to calculate travel distance in miles."""
        if origin not in self.city_lat_long or destination not in self.city_lat_long:
            return 500 # Default fallback
            
        lat1, lon1, _ = self.city_lat_long[origin]
        lat2, lon2, _ = self.city_lat_long[destination]
        
        R = 3958.8 # Earth radius in miles
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def calculate_cf(self, origin_team, destination_team, days_since_last_game):
        """
        Computes the CF Variable.
        CF = (Distance_Weight * (Log10(Miles) / Days_Rest)) + (Timezone_Penalty * Hour_Delta) + (Altitude_Tax)
        """
        miles = self.calculate_distance(origin_team, destination_team)
        
        # 1. Distance Stress (Logarithmic)
        distance_stress = math.log10(max(1, miles)) / max(1, days_since_last_game)
        
        # 2. Timezone Shift (Metabolic Jetlag)
        # Simplified: Each 15 degrees longitude is roughly 1 hour
        lon1 = self.city_lat_long.get(origin_team, (0,0,0))[1]
        lon2 = self.city_lat_long.get(destination_team, (0,0,0))[1]
        tz_delta = abs(lon2 - lon1) / 15.0
        tz_penalty = (tz_delta ** 1.5) / max(1, days_since_last_game)
        
        # 3. Altitude Taxonomy
        alt_origin = self.city_lat_long.get(origin_team, (0,0,0))[2]
        alt_dest = self.city_lat_long.get(destination_team, (0,0,0))[2]
        altitude_tax = 0
        if alt_dest > 3000 and alt_origin < 1000:
            altitude_tax = 1.25 # Significant disadvantage for unacclimated teams
            
        cf_score = (distance_stress * 0.4) + (tz_penalty * 0.5) + (altitude_tax * 0.1)
        
        return round(float(cf_score), 4)

if __name__ == "__main__":
    cf_engine = CircadianFriction()
    # Example: Knicks (NYC) traveling to Nuggets (Denver) after 1 day rest
    score = cf_engine.calculate_cf("Knicks", "Nuggets", 1)
    print(f"📊 Circadian Friction Score [NYC -> DEN, 1 Day Rest]: {score}")
