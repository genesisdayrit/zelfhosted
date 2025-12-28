"""
Exa Search Tool

Web search powered by Exa's AI-native search engine.
Docs: https://docs.exa.ai/reference/getting-started
"""

import os
import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()

EXA_API_KEY = os.getenv("EXA_API_KEY")
EXA_BASE_URL = "https://api.exa.ai"

http_client = httpx.Client(timeout=30.0)


def _exa_request(endpoint: str, payload: dict) -> dict:
    """Make authenticated request to Exa API."""
    api_key = EXA_API_KEY or os.getenv("EXA_API_KEY")
    if not api_key:
        raise ValueError("EXA_API_KEY environment variable not set")
    
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }
    response = http_client.post(
        f"{EXA_BASE_URL}{endpoint}",
        json=payload,
        headers=headers,
    )
    response.raise_for_status()
    return response.json()


@tool
def exa_search(
    query: str,
    num_results: int = 5,
    search_type: str = "auto",
    include_text: bool = True,
    include_highlights: bool = True,
) -> str:
    """Search the web using Exa's AI-powered search engine.
    
    Best for finding recent articles, research, news, and web content.
    Works well with natural language queries and questions.
    
    Args:
        query: The search query. Works best as a natural language question or statement.
        num_results: Number of results to return (default 5, max 10).
        search_type: Search type - "auto" (default), "neural", "keyword".
        include_text: Whether to include page text content (default True).
        include_highlights: Whether to include relevant text highlights (default True).
    """
    try:
        payload = {
            "query": query,
            "numResults": min(num_results, 10),
            "type": search_type,
            "contents": {
                "text": include_text,
                "highlights": include_highlights,
            },
        }
        
        data = _exa_request("/search", payload)
        results = data.get("results", [])
        
        if not results:
            return f"No results found for: {query}"
        
        lines = [f"🔍 Exa Search: {query}\n"]
        
        for i, result in enumerate(results, 1):
            title = result.get("title", "Untitled")
            url = result.get("url", "")
            
            lines.append(f"{i}. **{title}**")
            lines.append(f"   {url}")
            
            # Add highlights if available
            highlights = result.get("highlights", [])
            if highlights:
                highlight_text = highlights[0][:250] + "..." if len(highlights[0]) > 250 else highlights[0]
                lines.append(f"   → {highlight_text}")
            
            lines.append("")
        
        return "\n".join(lines)
        
    except httpx.HTTPStatusError as e:
        return f"Exa API error: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error searching Exa: {str(e)}"


@tool  
def exa_find_similar(
    url: str,
    num_results: int = 5,
) -> str:
    """Find webpages similar to a given URL using Exa.
    
    Great for discovering related content, competitors, or similar articles.
    
    Args:
        url: The URL to find similar pages for.
        num_results: Number of similar results to return (default 5).
    """
    try:
        payload = {
            "url": url,
            "numResults": min(num_results, 10),
            "contents": {
                "text": True,
                "highlights": True,
            },
        }
        
        data = _exa_request("/findSimilar", payload)
        results = data.get("results", [])
        
        if not results:
            return f"No similar pages found for: {url}"
        
        lines = [f"🔗 Similar to: {url}\n"]
        
        for i, result in enumerate(results, 1):
            title = result.get("title", "Untitled")
            result_url = result.get("url", "")
            
            lines.append(f"{i}. **{title}**")
            lines.append(f"   {result_url}")
            
            highlights = result.get("highlights", [])
            if highlights:
                highlight_text = highlights[0][:200] + "..." if len(highlights[0]) > 200 else highlights[0]
                lines.append(f"   → {highlight_text}")
            
            lines.append("")
        
        return "\n".join(lines)
        
    except httpx.HTTPStatusError as e:
        return f"Exa API error: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error finding similar pages: {str(e)}"


@tool
def exa_answer(
    question: str,
) -> str:
    """Get a direct answer to a question using Exa's Answer API.
    
    This searches the web and synthesizes an answer with citations.
    Best for factual questions that need up-to-date information.
    
    Args:
        question: The question to answer.
    """
    try:
        payload = {
            "query": question,
        }
        
        data = _exa_request("/answer", payload)
        
        answer = data.get("answer", "")
        citations = data.get("citations", [])
        
        if not answer:
            return f"Could not find an answer for: {question}"
        
        lines = [f"❓ {question}\n"]
        lines.append(f"💡 {answer}\n")
        
        if citations:
            lines.append("📚 Sources:")
            for citation in citations[:5]:
                title = citation.get("title", "")
                url = citation.get("url", "")
                if title and url:
                    lines.append(f"   • [{title}]({url})")
        
        return "\n".join(lines)
        
    except httpx.HTTPStatusError as e:
        return f"Exa API error: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error getting answer: {str(e)}"

