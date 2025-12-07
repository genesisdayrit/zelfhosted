"""
NYC Subway Real-time Tool

Fetches real-time subway arrivals using the official MTA GTFS-RT feeds
via the nyct-gtfs library. No API key required!

https://github.com/Andrew-Dickinson/nyct-gtfs
"""

import re
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
