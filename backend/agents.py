"""
Multi-Agent Intelligence Layer
================================
Implements the four core AI agents:
  1. AttributionAgent  — Pollution source identification via inverse-distance weighting
  2. PredictiveAgent   — AQI forecasting (delegates to SimulationEngine)
  3. EnforcementAgent  — Prioritised dispatch generation with evidence packages
  4. AdvisoryAgent     — Multi-lingual citizen health advisory generation
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional


# ── Utility ───────────────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance (km) between two lat/lng points."""
    R = 6371.0  # Earth radius in kilometres
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Source Attribution Agent ──────────────────────────────────────────────────

class AttributionAgent:
    """Identifies probable pollution sources for a queried location using
    inverse-distance-weighted attribution against known emission sources."""

    CATEGORY_LABELS: Dict[str, str] = {
        "industrial": "Industrial Emissions",
        "vehicular": "Vehicular Traffic",
        "construction": "Construction Dust",
        "waste_burning": "Waste Burning",
    }

    def run(
        self,
        lat: float,
        lng: float,
        sources: List[Dict[str, Any]],
        readings: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        # Get pollutants from the nearest reading to adjust weights dynamically
        pollutants = None
        if readings:
            try:
                nearest_reading = min(readings, key=lambda r: _haversine(lat, lng, r["location"][0], r["location"][1]))
                pollutants = nearest_reading.get("pollutants")
            except Exception:
                pass

        boosts = {"industrial": 1.0, "vehicular": 1.0, "construction": 1.0, "waste_burning": 1.0}
        if pollutants:
            pm25 = pollutants.get("pm25", 0.0)
            pm10 = pollutants.get("pm10", 0.0)
            no2 = pollutants.get("no2", 0.0)
            so2 = pollutants.get("so2", 0.0)
            co = pollutants.get("co", 0.0)

            # High NO2 (>40) or high CO (>1.0) indicates vehicular dominance
            if no2 > 40.0 or co > 1.0:
                boosts["vehicular"] += 1.5 * max(no2 / 40.0, co / 1.0)
            
            # High SO2 (>20) or high CO (>1.5) indicates industrial
            if so2 > 20.0:
                boosts["industrial"] += 2.0 * (so2 / 20.0)
            elif pm25 > 50.0 and so2 > 10.0:
                boosts["industrial"] += 1.5

            # Construction/road dust is mostly PM10 (PM10/PM2.5 ratio > 1.8)
            if pm25 > 0:
                ratio = pm10 / pm25
                if ratio > 1.8 and pm10 > 50.0:
                    boosts["construction"] += 1.5 * (ratio - 1.0)
            
            # Waste burning / crop burning results in high PM2.5 relative to PM10 (PM2.5/PM10 ratio > 0.6)
            if pm10 > 0:
                ratio = pm25 / pm10
                if ratio > 0.6 and pm25 > 60.0:
                    boosts["waste_burning"] += 1.8 * (ratio / 0.6)

        contributions: Dict[str, float] = {}
        total_weight = 0.0

        for source in sources:
            dist = _haversine(lat, lng, source["location"][0], source["location"][1])
            if dist > 10:  # Beyond 10 km — no attribution
                continue
            base_weight = 1.0 / max(dist, 0.1)
            weight = base_weight * boosts.get(source["category"], 1.0)
            contributions[source["category"]] = (
                contributions.get(source["category"], 0) + weight
            )
            total_weight += weight

        if total_weight == 0:
            return {
                "sources": [
                    {"category": "background", "label": "Background / Natural",
                     "percentage": 100, "confidence": 0.50}
                ],
                "location": [lat, lng],
                "timestamp": datetime.now().isoformat(),
            }

        result: List[Dict[str, Any]] = []
        for cat, w in sorted(contributions.items(), key=lambda x: -x[1]):
            pct = round((w / total_weight) * 100, 1)
            conf = round(min(0.95, 0.60 + (w / total_weight) * 0.35), 2)
            result.append(
                {
                    "category": cat,
                    "label": self.CATEGORY_LABELS.get(cat, cat.title()),
                    "percentage": pct,
                    "confidence": conf,
                }
            )

        return {
            "sources": result,
            "location": [lat, lng],
            "timestamp": datetime.now().isoformat(),
        }


# ── Predictive AQI Agent ─────────────────────────────────────────────────────

class PredictiveAgent:
    """Generates 24-72 hour hyperlocal AQI forecasts by delegating
    to the SimulationEngine's dispersion-aware forecast model."""

    def run(self, sim_engine: Any, hours: int = 24) -> List[Dict[str, Any]]:
        return sim_engine.generate_forecast(hours)


# ── Enforcement Intelligence Agent ───────────────────────────────────────────

class EnforcementAgent:
    """Generates prioritised enforcement dispatch recommendations
    with evidence packages for field inspectors."""

    THRESHOLDS = {"severe": 200, "very_poor": 150, "poor": 100}

    def run(
        self,
        readings: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        wards: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        hotspots: List[Dict[str, Any]] = []

        for reading in readings:
            if reading["aqi"] < self.THRESHOLDS["poor"]:
                continue

            severity = (
                "severe"
                if reading["aqi"] >= self.THRESHOLDS["severe"]
                else "very_poor"
                if reading["aqi"] >= self.THRESHOLDS["very_poor"]
                else "poor"
            )

            ward = next(
                (w for w in wards if w["id"] == reading["ward_id"]), None
            )

            # Find nearby emission sources
            nearby: List[Dict[str, Any]] = []
            for src in sources:
                dist = _haversine(
                    reading["location"][0],
                    reading["location"][1],
                    src["location"][0],
                    src["location"][1],
                )
                if dist < 5:
                    nearby.append({**src, "distance_km": round(dist, 2)})

            # Priority scoring: AQI weighted by proximity to sensitive zones
            priority_score = float(reading["aqi"])
            if ward:
                vuln = ward.get("vulnerable", {})
                if vuln.get("hospitals", 0) >= 3:
                    priority_score *= 1.3
                if vuln.get("schools", 0) >= 5:
                    priority_score *= 1.15
                if vuln.get("elderly_pct", 0) >= 15:
                    priority_score *= 1.2

            hotspots.append(
                {
                    "sensor_id": reading["sensor_id"],
                    "ward_id": reading["ward_id"],
                    "ward_name": ward["name"] if ward else "Unknown",
                    "location": reading["location"],
                    "aqi": reading["aqi"],
                    "severity": severity,
                    "priority_score": round(priority_score, 1),
                    "nearby_sources": nearby,
                    "recommended_actions": self._recommend(severity, nearby),
                    "evidence": {
                        "aqi_reading": reading["aqi"],
                        "pollutants": reading["pollutants"],
                        "timestamp": reading["timestamp"],
                        "coordinates": reading["location"],
                    },
                }
            )

        hotspots.sort(key=lambda x: -x["priority_score"])
        return {
            "dispatches": hotspots,
            "total_hotspots": len(hotspots),
            "generated_at": datetime.now().isoformat(),
        }

    @staticmethod
    def _recommend(severity: str, nearby: List[Dict[str, Any]]) -> List[str]:
        actions: List[str] = []
        cats = {s["category"] for s in nearby}
        if "industrial" in cats:
            actions.append("Inspect industrial emissions compliance")
        if "construction" in cats:
            actions.append("Verify construction dust suppression measures")
        if "vehicular" in cats:
            actions.append("Deploy traffic management and green corridor")
        if "waste_burning" in cats:
            actions.append("Investigate and halt open waste burning")
        if not actions:
            actions.append("Deploy mobile monitoring unit for source identification")
        if severity == "severe":
            actions.insert(
                0, "URGENT: Issue area evacuation advisory for sensitive groups"
            )
        return actions


# ── Citizen Advisory Agent ────────────────────────────────────────────────────

class AdvisoryAgent:
    """Generates localised, multi-lingual citizen health advisories."""

    LANGUAGES: Dict[str, str] = {
        "en": "English",
        "hi": "Hindi",
        "kn": "Kannada",
        "ta": "Tamil",
    }

    _ADVISORIES: Dict[str, Dict[str, str]] = {
        "good": {
            "en": "Air quality is satisfactory. Enjoy outdoor activities.",
            "hi": "वायु गुणवत्ता संतोषजनक है। बाहरी गतिविधियों का आनंद लें।",
            "kn": "ವಾಯು ಗುಣಮಟ್ಟ ತೃಪ್ತಿಕರವಾಗಿದೆ. ಹೊರಾಂಗಣ ಚಟುವಟಿಕೆಗಳನ್ನು ಆನಂದಿಸಿ.",
            "ta": "காற்றின் தரம் திருப்திகரமாக உள்ளது. வெளிப்புற நடவடிக்கைகளை அனுபவியுங்கள்.",
        },
        "satisfactory": {
            "en": "Air quality is acceptable. Unusually sensitive people should limit outdoor exertion.",
            "hi": "वायु गुणवत्ता स्वीकार्य है। अत्यधिक संवेदनशील लोगों को बाहरी परिश्रम सीमित करना चाहिए।",
            "kn": "ವಾಯು ಗುಣಮಟ್ಟ ಸ್ವೀಕಾರಾರ್ಹ. ಅತಿ ಸೂಕ್ಷ್ಮ ವ್ಯಕ್ತಿಗಳು ಹೊರಾಂಗಣ ಶ್ರಮ ಮಿತಿಗೊಳಿಸಬೇಕು.",
            "ta": "காற்றின் தரம் ஏற்றுக்கொள்ளத்தக்கது. மிகவும் உணர்திறன் உள்ளவர்கள் வெளிப்புற உழைப்பைக் கட்டுப்படுத்தவும்.",
        },
        "moderate": {
            "en": "Air quality is moderate. Sensitive groups should limit prolonged outdoor exertion.",
            "hi": "वायु गुणवत्ता मध्यम है। संवेदनशील समूहों को लंबे समय तक बाहरी परिश्रम सीमित करना चाहिए।",
            "kn": "ವಾಯು ಗುಣಮಟ್ಟ ಮಧ್ಯಮವಾಗಿದೆ. ಸೂಕ್ಷ್ಮ ಗುಂಪುಗಳು ಹೊರಾಂಗಣ ಶ್ರಮವನ್ನು ಮಿತಿಗೊಳಿಸಬೇಕು.",
            "ta": "காற்றின் தரம் மிதமானது. உணர்திறன் குழுக்கள் நீடித்த வெளிப்புற உழைப்பைக் கட்டுப்படுத்த வேண்டும்.",
        },
        "poor": {
            "en": "⚠️ Air quality is poor. Avoid outdoor exercise. Wear masks if outside.",
            "hi": "⚠️ वायु गुणवत्ता खराब है। बाहरी व्यायाम से बचें। बाहर होने पर मास्क पहनें।",
            "kn": "⚠️ ವಾಯು ಗುಣಮಟ್ಟ ಕಳಪೆಯಾಗಿದೆ. ಹೊರಾಂಗಣ ವ್ಯಾಯಾಮ ಬೇಡ. ಮಾಸ್ಕ್ ಧರಿಸಿ.",
            "ta": "⚠️ காற்றின் தரம் மோசமாக உள்ளது. வெளிப்புற உடற்பயிற்சியைத் தவிர்க்கவும். முகக்கவசம் அணியவும்.",
        },
        "very_poor": {
            "en": "🔴 Air quality is very poor. Stay indoors. Close windows. Keep medication ready.",
            "hi": "🔴 वायु गुणवत्ता बहुत खराब है। घर के अंदर रहें। खिड़कियां बंद करें।",
            "kn": "🔴 ವಾಯು ಗುಣಮಟ್ಟ ತುಂಬಾ ಕಳಪೆ. ಒಳಗೆ ಇರಿ. ಕಿಟಕಿ ಮುಚ್ಚಿ.",
            "ta": "🔴 காற்றின் தரம் மிகவும் மோசம். வீட்டிற்குள் இருங்கள். ஜன்னல்களை மூடுங்கள்.",
        },
        "severe": {
            "en": "🚨 SEVERE: Hazardous air quality. Stay indoors. Close all openings. Use air purifiers. Seek medical help if breathing difficulty occurs.",
            "hi": "🚨 गंभीर: खतरनाक वायु गुणवत्ता। घर के अंदर रहें। सभी खिड़कियां बंद करें। एयर प्यूरीफायर का उपयोग करें।",
            "kn": "🚨 ತೀವ್ರ: ಅಪಾಯಕಾರಿ ವಾಯು ಗುಣಮಟ್ಟ. ಒಳಗೆ ಇರಿ. ಎಲ್ಲಾ ಕಿಟಕಿ ಮುಚ್ಚಿ. ಏರ್ ಪ್ಯೂರಿಫೈಯರ್ ಬಳಸಿ.",
            "ta": "🚨 கடுமையான: ஆபத்தான காற்றின் தரம். வீட்டிற்குள் இருங்கள். அனைத்து ஜன்னல்களையும் மூடுங்கள்.",
        },
    }

    def run(
        self,
        ward: Dict[str, Any],
        aqi: float,
        lang: str = "en",
        pollutants: Dict[str, float] = None,
        weather: Dict[str, Any] = None,
        sources: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        level = self._aqi_level(aqi)
        advisory_text = self._ADVISORIES[level].get(
            lang, self._ADVISORIES[level]["en"]
        )

        precautions: List[str] = []
        if aqi > 100:
            precautions.extend(
                ["Wear N95 mask outdoors", "Keep windows and doors closed"]
            )
        if aqi > 200:
            precautions.extend(
                [
                    "Avoid all outdoor activities",
                    "Use air purifier if available",
                    "Seek medical attention if breathing difficulty occurs",
                ]
            )
        if aqi > 300:
            precautions.append(
                "EMERGENCY: Consider temporary relocation from affected area"
            )

        # Dynamic Reason / Driver Analysis Explanation
        dominant = "PM2.5"
        if pollutants:
            # Determine dominant pollutant by scaling relative to standard limits
            ratios = {
                "PM2.5": pollutants.get("pm25", 0) / 60.0,
                "PM10": pollutants.get("pm10", 0) / 100.0,
                "NO₂": pollutants.get("no2", 0) / 80.0,
                "SO₂": pollutants.get("so2", 0) / 80.0,
                "CO": pollutants.get("co", 0) / 2.0,
                "O₃": pollutants.get("o3", 0) / 100.0
            }
            dominant = max(ratios, key=ratios.get)

        ws_kmh = weather.get("wind_speed_kmh") if weather else None
        stagnant = ws_kmh is not None and ws_kmh < 8.0

        nearby_sources = []
        if sources and "center" in ward:
            for s in sources:
                dist = _haversine(ward["center"][0], ward["center"][1], s["location"][0], s["location"][1])
                if dist < 6.0:
                    nearby_sources.append(s["name"])

        explanations = {
            "en": {
                "intro": f"The primary driver of the current air pollution is {dominant}.",
                "weather": " Stagnant wind conditions are preventing the dispersion of pollutants.",
                "sources": f" Emissions from nearby sources like {', '.join(nearby_sources[:2])} are contributing significantly.",
                "background": " High regional background levels are keeping the index elevated."
            },
            "hi": {
                "intro": f"वर्तमान वायु प्रदूषण का मुख्य कारक {dominant} है।",
                "weather": " हवा की गति धीमी होने के कारण प्रदूषक बिखर नहीं पा रहे हैं।",
                "sources": f" आस-पास के स्रोतों जैसे {', '.join(nearby_sources[:2])} से उत्सर्जन का महत्वपूर्ण योगदान है।",
                "background": " क्षेत्रीय पृष्ठभूमि के उच्च स्तर भी सूचकांक को बढ़ाए हुए हैं।"
            },
            "kn": {
                "intro": f"ಪ್ರಸ್ತುತ ವಾಯು ಮಾಲಿನ್ಯಕ್ಕೆ ಮುಖ್ಯ ಕಾರಣವೆಂದರೆ {dominant}.",
                "weather": " ಗಾಳಿಯ ವೇಗ ಕಡಿಮೆಯಿರುವುದರಿಂದ ಮಾಲಿನ್ಯಕಾರಕಗಳು ಚದುರಿಹೋಗುತ್ತಿಲ್ಲ.",
                "sources": f" ಹತ್ತಿರದ ಮೂಲಗಳಾದ {', '.join(nearby_sources[:2])} ಇವುಗಳಿಂದ ಬರುವ ಹೊಗೆಯು ಗಮನಾರ್ಹ ಕೊಡುಗೆ ನೀಡುತ್ತಿದೆ.",
                "background": " ಪ್ರಾದೇಶಿಕ ಹಿನ್ನೆಲೆ ಮಟ್ಟವು ಸಹ ಸೂಚ್ಯಂಕವನ್ನು ಹೆಚ್ಚಾಗಿರಿಸಿದೆ."
            },
            "ta": {
                "intro": f"தற்போதைய காற்று மாசுபாட்டிற்கு முக்கிய காரணி {dominant} ஆகும்.",
                "weather": " காற்றின் வேகம் குறைவாக இருப்பதால் மாசுக்கள் பரவ முடியாமல் தேங்கி நிற்கின்றன.",
                "sources": f" அருகிலுள்ள {', '.join(nearby_sources[:2])} போன்ற உமிழ்வு ஆதாரங்கள் கணிசமான பங்களிப்பை அளிக்கின்றன.",
                "background": " பிராந்திய பின்னணி மாசு அளவும் குறியீட்டை உயர்த்திய நிலையில் வைத்துள்ளது."
            }
        }

        lang_key = lang if lang in explanations else "en"
        exp = explanations[lang_key]

        reason_text = exp["intro"]
        if stagnant:
            reason_text += exp["weather"]
        if nearby_sources:
            reason_text += exp["sources"]
        else:
            reason_text += exp["background"]

        return {
            "ward_id": ward["id"],
            "ward_name": ward["name"],
            "aqi": aqi,
            "level": level,
            "language": self.LANGUAGES.get(lang, "English"),
            "language_code": lang,
            "advisory": advisory_text,
            "reason": reason_text,
            "precautions": precautions,
            "vulnerable_info": ward.get("vulnerable", {}),
            "generated_at": datetime.now().isoformat(),
        }

    @staticmethod
    def _aqi_level(aqi: float) -> str:
        if aqi <= 50:
            return "good"
        if aqi <= 100:
            return "satisfactory"
        if aqi <= 200:
            return "moderate"
        if aqi <= 300:
            return "poor"
        if aqi <= 400:
            return "very_poor"
        return "severe"
