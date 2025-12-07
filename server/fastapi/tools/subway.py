"""
NYC Subway Real-time Tool

Fetches real-time subway arrivals using the official MTA GTFS-RT feeds
via the nyct-gtfs library. No API key required!

https://github.com/Andrew-Dickinson/nyct-gtfs
"""

import csv
import math
import re
from pathlib import Path

import httpx
from langchain_core.tools import tool

VALID_LINES = [
    "1", "2", "3", "4", "5", "6", "7", "S",
    "A", "C", "E", "B", "D", "F", "M",
    "G", "J", "Z", "L", "N", "Q", "R", "W",
    "H", "FS", "SIR"
]

LINE_NAMES = {
    "1": "Broadway-7th Ave Local",
    "2": "7th Ave Express",
    "3": "7th Ave Express",
    "4": "Lexington Ave Express",
    "5": "Lexington Ave Express",
    "6": "Lexington Ave Local",
    "7": "Flushing Local/Express",
    "A": "8th Ave Express",
    "C": "8th Ave Local",
    "E": "8th Ave Local",
    "B": "6th Ave Express",
    "D": "6th Ave Express",
    "F": "6th Ave Local",
    "M": "6th Ave Local",
    "G": "Brooklyn-Queens Crosstown",
    "J": "Nassau St Local",
    "Z": "Nassau St Express",
    "L": "14th St-Canarsie Local",
    "N": "Broadway Express",
    "Q": "Broadway Express",
    "R": "Broadway Local",
    "W": "Broadway Local",
    "S": "42nd St Shuttle",
    "H": "Rockaway Park Shuttle",
    "FS": "Franklin Ave Shuttle",
    "SIR": "Staten Island Railway",
}

# Street type suffixes to normalize or strip
STREET_TYPES = {
    "street", "st",
    "avenue", "ave", "av", "avs",
    "boulevard", "blvd",
    "parkway", "pkwy",
    "square", "sq",
    "place", "pl",
    "road", "rd",
    "drive", "dr",
    "junction", "jct",
    "terminal", "term",
    "center", "ctr",
    "heights", "hts",
    "beach", "bch",
    "lane", "ln",
    "court", "ct",
}


# ============================================================================
# Station Coordinate Data (from MTA GTFS stops.txt)
# ============================================================================

def load_station_coordinates() -> dict[str, dict]:
    """Load station coordinates from stops.txt."""
    stations = {}
    stops_file = Path(__file__).parent / "data" / "stops.txt"

    if not stops_file.exists():
        return stations

    with open(stops_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only include parent stations (location_type=1) to avoid duplicates
            if row.get("location_type") == "1":
                stations[row["stop_id"]] = {
                    "name": row["stop_name"],
                    "lat": float(row["stop_lat"]),
                    "lon": float(row["stop_lon"]),
                    "stop_id": row["stop_id"],
                }
    return stations


# Load station coordinates once at module import
STATION_COORDS = load_station_coordinates()


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two coordinates using Haversine formula."""
    R = 6371  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def find_nearest_stations(lat: float, lon: float, n: int = 5) -> list[dict]:
    """Find the n nearest subway stations to given coordinates."""
    stations_with_dist = []

    for stop_id, station in STATION_COORDS.items():
        dist = haversine_distance(lat, lon, station["lat"], station["lon"])
        stations_with_dist.append({
            **station,
            "distance_km": round(dist, 2),
            "distance_mi": round(dist * 0.621371, 2),
        })

    stations_with_dist.sort(key=lambda x: x["distance_km"])
    return stations_with_dist[:n]


def geocode_location(location: str) -> tuple[float, float, str] | None:
    """Convert a location name to coordinates using Open-Meteo Geocoding API."""
    # Add "NYC" context if not present for better results
    search_query = location
    if "nyc" not in location.lower() and "new york" not in location.lower():
        search_query = f"{location}, New York City"

    try:
        response = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": search_query, "count": 1, "language": "en", "format": "json"},
            timeout=10.0,
        )

        if response.status_code != 200:
            return None

        data = response.json()
        if not data.get("results"):
            return None

        result = data["results"][0]
        display_name = result.get("name", location)
        if result.get("admin1"):
            display_name += f", {result['admin1']}"

        return (result["latitude"], result["longitude"], display_name)
    except Exception:
        return None


# ============================================================================
# Station Name Matching Utilities
# ============================================================================

def normalize_station_name(name: str) -> str:
    """Normalize station name for better matching."""
    name = name.lower().strip()

    # Common abbreviations used by MTA
    replacements = [
        ("street", "st"),
        ("avenue", "av"),
        ("boulevard", "blvd"),
        ("parkway", "pkwy"),
        ("square", "sq"),
        ("place", "pl"),
        ("road", "rd"),
        ("drive", "dr"),
        ("junction", "jct"),
        ("terminal", "term"),
        ("center", "ctr"),
        ("heights", "hts"),
        ("beach", "bch"),
    ]

    for full, abbrev in replacements:
        name = name.replace(full, abbrev)

    # Normalize hyphens and extra spaces
    name = name.replace("-", " ")
    name = " ".join(name.split())

    return name


def extract_core_name(name: str) -> str:
    """Extract the core name by removing street type suffixes."""
    name = normalize_station_name(name)
    words = name.split()

    # Remove trailing street type words
    while words and words[-1] in STREET_TYPES:
        words.pop()

    # Also remove leading street types (less common but possible)
    while words and words[0] in STREET_TYPES:
        words.pop(0)

    return " ".join(words) if words else name


def find_matching_stations(query: str, stop_names: list[str]) -> list[str]:
    """Find station names that match the query, with fuzzy matching."""
    query_norm = normalize_station_name(query)
    query_core = extract_core_name(query)

    matches = []

    for stop_name in stop_names:
        stop_norm = normalize_station_name(stop_name)
        stop_core = extract_core_name(stop_name)

        # Exact normalized match
        if query_norm in stop_norm or stop_norm in query_norm:
            matches.append(stop_name)
        # Core name match (ignores street vs avenue confusion)
        elif query_core and stop_core and (query_core in stop_core or stop_core in query_core):
            matches.append(stop_name)

    # If still no matches, try matching on numbers (e.g., "14" matches "14 St" or "14 Av")
    if not matches:
        query_numbers = re.findall(r'\d+', query)
        if query_numbers:
            for stop_name in stop_names:
                stop_numbers = re.findall(r'\d+', stop_name)
                # If the main number matches
                if query_numbers and stop_numbers and query_numbers[0] == stop_numbers[0]:
                    matches.append(stop_name)

    # Dedupe while preserving order
    seen = set()
    unique_matches = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            unique_matches.append(m)

    return unique_matches


# ============================================================================
# Tools
# ============================================================================

@tool
def get_subway_arrivals(line: str, limit: int = 10) -> str:
    """Get real-time NYC subway train arrivals and status.

    Args:
        line: Subway line letter/number (e.g. "G", "A", "1", "L")
        limit: Maximum number of trains to show (default 10)
    """
    from nyct_gtfs import NYCTFeed

    line_upper = line.upper()
    if line_upper not in VALID_LINES:
        return f"Unknown line '{line}'. Valid lines: {', '.join(VALID_LINES)}"

    try:
        feed = NYCTFeed(line_upper)
        trains = feed.filter_trips(line_id=[line_upper], underway=True)

        if not trains:
            return f"No {line_upper} trains currently running."

        line_name = LINE_NAMES.get(line_upper, line_upper)
        output = [f"🚇 {line_upper} Train — {line_name}\n"]

        for train in trains[:limit]:
            # Each train has a nice __str__ representation
            output.append(f"  • {train}")

        if len(trains) > limit:
            output.append(f"\n  ... and {len(trains) - limit} more trains")

        output.append(f"\n📊 Total active: {len(trains)} trains")

        return "\n".join(output)

    except Exception as e:
        return f"Error fetching subway data: {str(e)}"


@tool
def get_train_arrivals_at_station(line: str, station: str, limit: int = 5) -> str:
    """Get upcoming train arrivals at a specific station.

    Args:
        line: Subway line letter/number (e.g. "G", "A", "1")
        station: Station name to search for (e.g. "Times Sq", "14 St", "Bedford", "Fulton Street")
        limit: Maximum arrivals to show (default 5)
    """
    from nyct_gtfs import NYCTFeed
    import datetime

    line_upper = line.upper()
    if line_upper not in VALID_LINES:
        return f"Unknown line '{line}'. Valid lines: {', '.join(VALID_LINES)}"

    try:
        feed = NYCTFeed(line_upper)
        trains = feed.filter_trips(line_id=[line_upper], underway=True)

        if not trains:
            return f"No {line_upper} trains currently running."

        # Collect all unique station names from the feed
        all_stop_names = set()
        for train in trains:
            for stop in train.stop_time_updates:
                all_stop_names.add(stop.stop_name)

        # Find matching stations using normalized + fuzzy search
        matching_stations = find_matching_stations(station, list(all_stop_names))

        if not matching_stations:
            # Suggest similar stations based on first few characters
            query_start = station.lower()[:3]
            suggestions = sorted([s for s in all_stop_names if query_start in s.lower()])[:5]
            if suggestions:
                return f"No stations matching '{station}'. Did you mean: {', '.join(suggestions)}?"
            return f"No stations matching '{station}' found on the {line_upper} line."

        arrivals = []

        for train in trains:
            for stop in train.stop_time_updates:
                if stop.stop_name in matching_stations:
                    arrivals.append({
                        "train": train,
                        "stop": stop,
                        "arrival": stop.arrival,
                    })

        if not arrivals:
            return f"No upcoming {line_upper} trains found for '{station}'."

        # Sort by arrival time
        arrivals.sort(key=lambda x: x["arrival"] if x["arrival"] else float("inf"))

        # Get unique matched station names for the header
        matched_names = list(dict.fromkeys(a["stop"].stop_name for a in arrivals[:limit]))
        output = [f"🚇 {line_upper} arrivals at {', '.join(matched_names)}:\n"]

        now = datetime.datetime.now()

        for arr in arrivals[:limit]:
            stop = arr["stop"]
            train = arr["train"]
            arrival_time = arr["arrival"]

            if arrival_time:
                mins = int((arrival_time - now).total_seconds() / 60)
                if mins < 1:
                    time_str = "arriving now"
                elif mins == 1:
                    time_str = "1 min"
                else:
                    time_str = f"{mins} mins"
            else:
                time_str = "time unknown"

            direction = "Uptown" if train.direction == "N" else "Downtown"
            output.append(f"  • {stop.stop_name} ({direction}): {time_str}")

        return "\n".join(output)

    except Exception as e:
        return f"Error: {str(e)}"


@tool
def get_nearby_subway_stations(
    location: str,
    num_stations: int = 5,
    user_lat: float | None = None,
    user_lon: float | None = None,
) -> str:
    """Find subway stations near a location.

    Args:
        location: Address, neighborhood, or landmark (e.g. "Williamsburg Brooklyn", "Empire State Building", "14th and 6th ave", or "near me")
        num_stations: Number of nearby stations to return (default 5)
        user_lat: User's latitude (auto-injected for "near me" queries)
        user_lon: User's longitude (auto-injected for "near me" queries)
    """
    if not STATION_COORDS:
        return "Error: Station coordinate data not available. Ensure data/stops.txt exists."

    # Use injected coordinates if available (for "near me" queries)
    if user_lat is not None and user_lon is not None:
        lat, lon = user_lat, user_lon
        display_name = "your location"
    else:
        geo = geocode_location(location)
        if not geo:
            return f"Could not find location: {location}"
        lat, lon, display_name = geo

    nearby = find_nearest_stations(lat, lon, num_stations)

    output = [f"📍 Subway stations near {display_name}:\n"]

    for station in nearby:
        output.append(f"  • {station['name']} — {station['distance_mi']} mi ({station['distance_km']} km)")

    output.append("\n💡 Use get_train_arrivals_at_station(line, station) for arrival times")

    return "\n".join(output)


@tool
def get_nearby_subway_arrivals(
    location: str,
    line: str = "",
    limit: int = 8,
    user_lat: float | None = None,
    user_lon: float | None = None,
) -> str:
    """Get subway arrivals at stations near a location.

    Args:
        location: Address, neighborhood, or landmark (e.g. "Williamsburg", "Times Square", "14th and 8th", or "near me")
        line: Optional - filter to specific line (e.g. "G", "L", "A"). Leave empty for all nearby lines.
        limit: Maximum arrivals to show (default 8)
        user_lat: User's latitude (auto-injected for "near me" queries)
        user_lon: User's longitude (auto-injected for "near me" queries)
    """
    from nyct_gtfs import NYCTFeed
    import datetime

    if not STATION_COORDS:
        return "Error: Station coordinate data not available."

    # Use injected coordinates if available (for "near me" queries)
    if user_lat is not None and user_lon is not None:
        lat, lon = user_lat, user_lon
        display_name = "your location"
    else:
        geo = geocode_location(location)
        if not geo:
            return f"Could not find location: {location}"
        lat, lon, display_name = geo

    nearby_stations = find_nearest_stations(lat, lon, n=5)  # Check 5 nearest stations

    if not nearby_stations:
        return "No nearby stations found."

    nearby_station_names = [s["name"] for s in nearby_stations]

    # Determine which lines to check
    if line:
        lines_to_check = [line.upper()]
    else:
        # Check common lines (skip shuttles for speed)
        lines_to_check = ["1", "2", "3", "4", "5", "6", "7", "A", "C", "E", "B", "D", "F", "M", "G", "J", "Z", "L", "N", "Q", "R", "W"]

    all_arrivals = []
    checked_lines = set()

    for check_line in lines_to_check:
        if check_line not in VALID_LINES or check_line in checked_lines:
            continue

        try:
            feed = NYCTFeed(check_line)
            # Mark all lines in this feed as checked (feeds contain multiple lines)
            for trip_line in feed.trip_replacement_periods.keys():
                checked_lines.add(trip_line)

            trains = feed.filter_trips(underway=True)

            for train in trains:
                train_line = train.route_id
                # Skip if we're filtering by line and this isn't it
                if line and train_line.upper() != line.upper():
                    continue

                for stop in train.stop_time_updates:
                    # Check if this stop matches any nearby station
                    stop_norm = normalize_station_name(stop.stop_name)
                    for nearby_name in nearby_station_names:
                        nearby_norm = normalize_station_name(nearby_name)
                        if nearby_norm in stop_norm or stop_norm in nearby_norm:
                            all_arrivals.append({
                                "line": train_line,
                                "train": train,
                                "stop": stop,
                                "arrival": stop.arrival,
                                "station_name": stop.stop_name,
                            })
                            break
        except Exception:
            continue  # Skip lines/feeds with errors

    if not all_arrivals:
        station_list = ", ".join(nearby_station_names[:3])
        if line:
            return f"No upcoming {line.upper()} trains found near {display_name} ({station_list})."
        return f"No upcoming trains found near {display_name} ({station_list})."

    # Sort by arrival time
    all_arrivals.sort(key=lambda x: x["arrival"] if x["arrival"] else float("inf"))

    # Dedupe by line+direction+station (keep earliest arrival)
    seen = set()
    unique_arrivals = []
    for arr in all_arrivals:
        key = (arr["line"], arr["train"].direction, arr["station_name"])
        if key not in seen:
            seen.add(key)
            unique_arrivals.append(arr)

    output = [f"🚇 Subway arrivals near {display_name}:\n"]

    now = datetime.datetime.now()

    for arr in unique_arrivals[:limit]:
        arrival_time = arr["arrival"]
        if arrival_time:
            mins = int((arrival_time - now).total_seconds() / 60)
            if mins < 1:
                time_str = "now"
            elif mins == 1:
                time_str = "1 min"
            else:
                time_str = f"{mins} mins"
        else:
            time_str = "?"

        direction = "↑" if arr["train"].direction == "N" else "↓"
        output.append(f"  • {arr['line']} {direction} at {arr['station_name']}: {time_str}")

    return "\n".join(output)
