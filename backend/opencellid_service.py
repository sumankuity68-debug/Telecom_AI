import os
from typing import Dict, List, Optional, Tuple
import requests
from dotenv import load_dotenv

load_dotenv()

OPENCELLID_API_KEY = os.getenv("OPENCELLID_API_KEY", "pk.742e92c119329e039d0a74c1ddde17e0")

# Known city coordinates (Latitude, Longitude)
CITY_COORDINATES: Dict[str, Tuple[float, float]] = {
    "kolkata": (22.5726, 88.3639),
    "delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "bengaluru": (12.9716, 77.5946),
    "bangalore": (12.9716, 77.5946),
    "hyderabad": (17.3850, 78.4867),
    "chennai": (13.0827, 80.2707),
    "pune": (18.5204, 73.8567),
    "ahmedabad": (23.0225, 72.5714),
    "jaipur": (26.9124, 75.7873),
    "lucknow": (26.8467, 80.9462),
    "london": (51.5074, -0.1278),
    "new york": (40.7128, -74.0060),
    "singapore": (1.3521, 103.8198),
    "tokyo": (35.6762, 139.6503),
    "dubai": (25.2048, 55.2708),
}


def resolve_carrier(mcc: int, mnc: int) -> str:
    """Resolve Mobile Country Code (MCC) and Mobile Network Code (MNC) to carrier name."""
    if mcc in (404, 405):  # India
        if mnc in (854, 855, 856, 857, 858, 859, 860, 861, 862, 863, 864, 865, 866, 867, 868, 869, 870, 871, 872, 873, 874, 36, 840):
            return "Reliance Jio"
        if mnc in (45, 49, 70, 86, 90, 92, 93, 94, 95, 96, 97, 98, 10, 16):
            return "Bharti Airtel"
        if mnc in (20, 27, 43, 44, 46, 78, 84, 88, 4, 11, 13, 15):
            return "Vodafone Idea (Vi)"
        if mnc in (51, 53, 54, 55, 57, 58, 59, 62, 64, 66, 71, 72, 74, 76, 81):
            return "BSNL"
    return f"Telecom Carrier (MCC {mcc} / MNC {mnc})"


def get_real_towers(
    lat: float,
    lon: float,
    delta: float = 0.008,
    api_key: Optional[str] = None,
) -> Dict:
    """
    Query OpenCellID API for real-time cellular towers within a bounding box.
    Limit BBOX to ~1.5km x 1.5km (stay within OpenCellID 4,000,000 sq. meters free quota).
    """
    key = api_key or OPENCELLID_API_KEY
    if not key:
        return {"error": "OpenCellID API key is not configured.", "towers": []}

    # Bounding box coordinates: minLat, minLon, maxLat, maxLon
    min_lat = round(lat - delta, 5)
    max_lat = round(lat + delta, 5)
    min_lon = round(lon - delta, 5)
    max_lon = round(lon + delta, 5)

    bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    url = f"https://opencellid.org/cell/getInArea?key={key}&BBOX={bbox_str}&format=json"

    try:
        resp = requests.get(url, timeout=8.0)
        if resp.status_code != 200:
            return {
                "success": False,
                "error": f"OpenCellID responded with HTTP {resp.status_code}: {resp.text}",
                "towers": [],
            }

        data = resp.json()
        raw_cells = data.get("cells", [])

        formatted_towers = []
        for cell in raw_cells:
            mcc = cell.get("mcc", 0)
            mnc = cell.get("mnc", 0)
            carrier = resolve_carrier(mcc, mnc)
            radio = cell.get("radio", "LTE")

            # Estimated signal strength in dBm based on samples and range
            range_m = cell.get("range", 1000)
            sig_dbm = -75.0 - (range_m / 100.0) if range_m > 0 else -85.0

            formatted_towers.append({
                "cell_id": str(cell.get("cellid", "UNKNOWN")),
                "carrier": carrier,
                "technology": radio,
                "latitude": cell.get("lat"),
                "longitude": cell.get("lon"),
                "range_meters": range_m,
                "mcc": mcc,
                "mnc": mnc,
                "lac_tac": cell.get("lac") or cell.get("tac", 0),
                "estimated_signal_dbm": round(sig_dbm, 1),
                "samples": cell.get("samples", 1),
                "status": "active" if cell.get("samples", 1) > 0 else "inactive",
            })

        return {
            "success": True,
            "source": "OpenCellID Global Database",
            "center": {"latitude": lat, "longitude": lon},
            "bounding_box": bbox_str,
            "total_towers": len(formatted_towers),
            "towers": formatted_towers,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"Failed to connect to OpenCellID: {exc}",
            "towers": [],
        }


def get_city_towers(city_name: str, api_key: Optional[str] = None) -> Dict:
    """
    Look up coordinates for an Indian or global city and fetch live real cell towers.
    """
    clean_city = city_name.strip().lower()
    coords = CITY_COORDINATES.get(clean_city)

    if not coords:
        # Default fallback to Kolkata if city unknown
        return {
            "success": False,
            "error": f"City '{city_name}' coordinates not found in local registry. Supported cities: {', '.join(k.title() for k in CITY_COORDINATES.keys())}",
            "supported_cities": [k.title() for k in CITY_COORDINATES.keys()],
            "towers": [],
        }

    lat, lon = coords
    result = get_real_towers(lat, lon, api_key=api_key)
    result["city"] = city_name.title()
    return result
