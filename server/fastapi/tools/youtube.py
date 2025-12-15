"""
YouTube Song Search Tool

Searches YouTube for songs and returns video links.
"""

import os
import httpx
from langchain_core.tools import tool

http_client = httpx.Client(timeout=10.0)


@tool
def search_youtube_song(
    query: str,
    max_results: int = 3,
) -> str:
    """Search for a song on YouTube and return video links.
    
    Use this tool when a user wants to find music, songs, or music videos on YouTube.
    
    Args:
        query: The song name and/or artist to search for, e.g. "Bohemian Rhapsody Queen"
        max_results: Number of results to return (default 3, max 5)
    """
    try:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            return "Error: YouTube API key not configured"
        
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
            return f"Error searching YouTube: {error_detail}"
        
        data = response.json()
        items = data.get("items", [])
        
        if not items:
            return f"No songs found for: {query}"
        
        lines = [f"🎵 YouTube results for \"{query}\":\n"]
        
        for i, item in enumerate(items, 1):
            video_id = item["id"]["videoId"]
            title = item["snippet"]["title"]
            channel = item["snippet"]["channelTitle"]
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            lines.append(f"{i}. **[{title}]({url})**")
            lines.append(f"   Channel: {channel}\n")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error searching YouTube: {str(e)}"

