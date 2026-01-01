"""
Spotify Search Tool

Searches Spotify for tracks, artists, albums, and playlists using the Web API.
Returns structured JSON with embed data for UI rendering.
"""

import os
import json
import base64
import time
import httpx
from langchain_core.tools import tool

http_client = httpx.Client(timeout=30.0)

# Token cache
_token_cache = {
    "access_token": None,
    "expires_at": 0,
}

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1"


def _get_access_token() -> str | None:
    """Get a valid Spotify access token, refreshing if needed."""
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    # Check if cached token is still valid (with 5 min buffer)
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 300:
        return _token_cache["access_token"]

    # Get new token using Client Credentials flow
    auth_string = f"{client_id}:{client_secret}"
    auth_bytes = base64.b64encode(auth_string.encode()).decode()

    try:
        response = http_client.post(
            SPOTIFY_TOKEN_URL,
            headers={
                "Authorization": f"Basic {auth_bytes}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        )
        response.raise_for_status()
        data = response.json()

        _token_cache["access_token"] = data["access_token"]
        _token_cache["expires_at"] = time.time() + data["expires_in"]

        return _token_cache["access_token"]
    except Exception:
        return None


def _format_track(track: dict) -> dict:
    """Format a track object for the response."""
    artists = ", ".join(a["name"] for a in track.get("artists", []))
    return {
        "type": "track",
        "id": track["id"],
        "name": track["name"],
        "artist": artists,
        "album": track.get("album", {}).get("name", ""),
        "url": track["external_urls"].get("spotify", ""),
    }


def _format_artist(artist: dict) -> dict:
    """Format an artist object for the response."""
    return {
        "type": "artist",
        "id": artist["id"],
        "name": artist["name"],
        "genres": ", ".join(artist.get("genres", [])[:3]),
        "followers": artist.get("followers", {}).get("total", 0),
        "url": artist["external_urls"].get("spotify", ""),
    }


def _format_album(album: dict) -> dict:
    """Format an album object for the response."""
    artists = ", ".join(a["name"] for a in album.get("artists", []))
    return {
        "type": "album",
        "id": album["id"],
        "name": album["name"],
        "artist": artists,
        "release_date": album.get("release_date", ""),
        "total_tracks": album.get("total_tracks", 0),
        "url": album["external_urls"].get("spotify", ""),
    }


def _format_playlist(playlist: dict) -> dict:
    """Format a playlist object for the response."""
    owner = playlist.get("owner", {}).get("display_name", "Unknown")
    return {
        "type": "playlist",
        "id": playlist["id"],
        "name": playlist["name"],
        "owner": owner,
        "total_tracks": playlist.get("tracks", {}).get("total", 0),
        "url": playlist["external_urls"].get("spotify", ""),
    }


@tool
def search_spotify(
    query: str,
    search_type: str = "track",
    limit: int = 5,
) -> str:
    """Search Spotify for music content.

    Use this tool when a user wants to find songs, artists, albums, or playlists on Spotify.
    Returns structured JSON with content details. The content will be embedded automatically
    in the UI - just summarize what was found for the user.

    Args:
        query: The search query (song name, artist, album title, or playlist name)
        search_type: Type of content to search for. Options: "track", "artist", "album", "playlist", or "all" (searches all types)
        limit: Number of results to return per type (default 5, max 10)
    """
    try:
        token = _get_access_token()
        if not token:
            return json.dumps({
                "error": "Spotify API credentials not configured",
                "results": [],
            })

        limit = min(max(1, limit), 10)

        # Determine which types to search
        if search_type == "all":
            types = "track,artist,album,playlist"
        elif search_type in ("track", "artist", "album", "playlist"):
            types = search_type
        else:
            types = "track"  # Default to track

        response = http_client.get(
            f"{SPOTIFY_API_URL}/search",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "q": query,
                "type": types,
                "limit": limit,
            },
        )

        if response.status_code != 200:
            error_msg = response.json().get("error", {}).get("message", "Unknown error")
            return json.dumps({
                "error": f"Spotify API error: {error_msg}",
                "results": [],
            })

        data = response.json()
        results = []
        text_parts = []

        # Process tracks
        if "tracks" in data:
            tracks = data["tracks"].get("items", [])
            for track in tracks:
                results.append(_format_track(track))
            if tracks:
                track_list = ", ".join(f"'{t['name']}' by {', '.join(a['name'] for a in t['artists'])}" for t in tracks[:3])
                text_parts.append(f"Tracks: {track_list}")

        # Process artists
        if "artists" in data:
            artists = data["artists"].get("items", [])
            for artist in artists:
                results.append(_format_artist(artist))
            if artists:
                artist_list = ", ".join(a["name"] for a in artists[:3])
                text_parts.append(f"Artists: {artist_list}")

        # Process albums
        if "albums" in data:
            albums = data["albums"].get("items", [])
            for album in albums:
                results.append(_format_album(album))
            if albums:
                album_list = ", ".join(f"'{a['name']}' by {', '.join(ar['name'] for ar in a['artists'])}" for a in albums[:3])
                text_parts.append(f"Albums: {album_list}")

        # Process playlists
        if "playlists" in data:
            playlists = data["playlists"].get("items", [])
            for playlist in playlists:
                if playlist:  # Can be null
                    results.append(_format_playlist(playlist))
            if playlists:
                playlist_list = ", ".join(p["name"] for p in playlists[:3] if p)
                text_parts.append(f"Playlists: {playlist_list}")

        if not results:
            return json.dumps({
                "error": f"No results found for: {query}",
                "results": [],
            })

        text = f"Found {len(results)} result(s) for '{query}'. " + "; ".join(text_parts)

        return json.dumps({
            "query": query,
            "results": results,
            "text": text,
        })

    except Exception as e:
        return json.dumps({
            "error": str(e),
            "results": [],
        })
