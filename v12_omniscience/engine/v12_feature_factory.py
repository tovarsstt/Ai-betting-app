import numpy as np
import math
from datetime import datetime

class V12FeatureFactory:
    """
    Consolidated 'Deep Feature' engine for V12 SHARP-PRO.
    Handles Sentiment, Circadian Friction, and Psych Factors (Tilt/Fatigue).
    """

    def __init__(self):
        # Coordinates and altitudes for key sports cities
        self.city_lat_long = {
            "LAL": (34.05, -118.24, 0),    
            "NYK": (40.71, -74.00, 0),     
            "DEN": (39.73, -104.99, 5280), 
            "BOS": (42.36, -71.05, 0),    
            "MIA": (25.76, -80.19, 0),
            "GSW": (37.77, -122.41, 0),
            "PHI": (39.95, -75.16, 0),
            "LIV": (53.40, -2.99, 0),     # Liverpool
            "GAL": (41.01, 28.97, 0),     # Istanbul (Galatasaray)
            "BAR": (41.38, 2.17, 0),      # Barcelona
            "NEW": (54.97, -1.61, 0)      # Newcastle
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

    def get_circadian_friction(self, origin_team, destination_team, days_rest):
        """Metabolic cost based on travel and altitude."""
        miles = self.calculate_distance(origin_team, destination_team)
        
        # Distance Stress
        distance_stress = math.log10(max(10, miles)) / max(1, days_rest)
        
        # Timezone Shift
        lon1 = self.city_lat_long.get(origin_team, (0,0,0))[1]
        lon2 = self.city_lat_long.get(destination_team, (0,0,0))[1]
        tz_delta = abs(lon2 - lon1) / 15.0
        tz_penalty = (tz_delta ** 1.5) / max(1, days_rest)
        
        # Altitude Tax
        alt_dest = self.city_lat_long.get(destination_team, (0,0,0))[2]
        altitude_tax = 1.25 if alt_dest > 3000 else 0.0
            
        return round((distance_stress * 0.4) + (tz_penalty * 0.5) + (altitude_tax * 0.1), 4)

    def get_narrative_sentiment(self, text):
        """
        Analyzes text for 'Micro-Injuries' or 'Locker Room Beef'.
        Simple trigger-based logic for fast execution.
        """
        if not text: return 1.0
        triggers = {
            "limping": 0.15, "soreness": 0.10, "beef": 0.20, 
            "frustrated": 0.10, "limited": 0.15, "revenge": -0.10 # Revenge can be a positive motivator
        }
        score = 1.0
        text_lower = text.lower()
        for trigger, penalty in triggers.items():
            if trigger in text_lower:
                score += penalty
        return round(float(score), 2)

    def get_tilt_tensor(self, prev_margin, prev_spread, is_loss=True):
        """Quantifies variance after high-stress outcomes."""
        if not is_loss: return 1.0
        stress_score = abs(prev_margin - prev_spread)
        tilt_factor = 1.0 + min(0.5, stress_score / 30.0)
        return round(float(tilt_factor), 2)

    def extract_deep_features(self, matchup_data):
        """
        Main entry point for God-Engine context injection.
        """
        # Example extraction logic
        home_team = matchup_data.get('home_team', 'GAL')
        away_team = matchup_data.get('away_team', 'LIV')
        
        cf_score = self.get_circadian_friction(away_team, home_team, matchup_data.get('away_rest', 3))
        sentiment_score = self.get_narrative_sentiment(matchup_data.get('news_ticker', ''))
        tilt_score = self.get_tilt_tensor(
            matchup_data.get('prev_margin', 0), 
            matchup_data.get('prev_spread', 0),
            matchup_data.get('prev_result_loss', False)
        )
        
        # Combined Friction Index (CFI)
        # CFI > 1.0 means unfavorable performance environment (Beta decay)
        cfi = (cf_score * 0.4) + (sentiment_score * 0.4) + (tilt_score * 0.2)
        
        return {
            "CFI": round(cfi, 4),
            "JET_LAG_TAX": cf_score,
            "NARRATIVE_STRESS": sentiment_score,
            "TILT_LOAD": tilt_score
        }
