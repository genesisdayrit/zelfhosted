"""
YouTube Song Search Tool

Searches YouTube for songs and returns video links with structured data for embedding.
"""

import os
import json
import httpx
from langchain_core.tools import tool

http_client = httpx.Client(timeout=10.0)


@tool
def search_youtube_song(
    query: str,
    max_results: int = 3,
) -> str:
    """Search for a song on YouTube and return video results.
    
    Use this tool when a user wants to find music, songs, or music videos on YouTube.
    Returns structured JSON with video details. The videos will be embedded automatically
    in the UI - just summarize what was found for the user.
    
    Args:
        query: The song name and/or artist to search for, e.g. "Bohemian Rhapsody Queen"
        max_results: Number of results to return (default 3, max 5)
    """
    try:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            return json.dumps({"error": "YouTube API key not configured", "videos": []})
        
        max_results = min(max_results, 5)  # Cap at 5
        
        response = http_client.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": f"{query} music",  # Append "music" to bias toward songs
                "type": "video",
                "videoCategoryId": "10",  # Music category
                "maxResults": max_results,
                "key": api_key,
            },
        )
        
        if response.status_code != 200:
            error_detail = response.json().get("error", {}).get("message", "Unknown error")
            return json.dumps({"error": f"YouTube API error: {error_detail}", "videos": []})
        
        data = response.json()
        items = data.get("items", [])
        
        if not items:
            return json.dumps({"error": f"No songs found for: {query}", "videos": []})
        
        videos = []
        for item in items:
            videos.append({
                "id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
            })
        
        # Return structured JSON
        result = {
            "query": query,
            "videos": videos,
            "text": f"Found {len(videos)} result(s) for '{query}': " + ", ".join(v["title"] for v in videos),
        }
        
        return json.dumps(result)
        
    except Exception as e:
        return json.dumps({"error": str(e), "videos": []})
