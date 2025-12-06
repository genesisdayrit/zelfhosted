"""
Twitter/X Posting Tool

Posts tweets using the X API v2 with OAuth 1.0a authentication.
Requires environment variables: X_API_KEY, X_API_SECRET, X_API_AUTH_ACCESS_TOKEN, X_API_AUTH_ACCESS_SECRET
"""

import os
import requests
from requests_oauthlib import OAuth1
from langchain_core.tools import tool

# API endpoint for posting tweets
TWITTER_API_URL = "https://api.twitter.com/2/tweets"


def _get_twitter_auth() -> OAuth1:
    """Create OAuth1 authentication object from environment variables."""
    return OAuth1(
        os.environ.get("X_API_KEY"),
        os.environ.get("X_API_SECRET"),
        os.environ.get("X_API_AUTH_ACCESS_TOKEN"),
        os.environ.get("X_API_AUTH_ACCESS_SECRET"),
    )


@tool
def post_tweet(text: str) -> str:
    """Post a tweet to Twitter/X.
    
    Args:
        text: The tweet content (max 280 characters)
    """
    # Validate tweet length
    if len(text) > 280:
        return f"Error: Tweet exceeds 280 character limit ({len(text)} characters provided)"
    
    # Check for credentials
    required_vars = ["X_API_KEY", "X_API_SECRET", "X_API_AUTH_ACCESS_TOKEN", "X_API_AUTH_ACCESS_SECRET"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        return f"Error: Missing required environment variables: {', '.join(missing)}"
    
    try:
        auth = _get_twitter_auth()
        
        response = requests.post(
            TWITTER_API_URL,
            auth=auth,
            json={"text": text},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        
        if response.status_code == 201:
            data = response.json()
            tweet_id = data["data"]["id"]
            return f"Tweet posted successfully!\nTweet ID: {tweet_id}\nURL: https://twitter.com/i/web/status/{tweet_id}"
        else:
            return f"Error posting tweet: {response.status_code} - {response.text}"
            
    except requests.RequestException as e:
        return f"Error connecting to Twitter API: {str(e)}"

