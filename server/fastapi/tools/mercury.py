"""
Mercury Account Balance Tool

Fetches account balance from Mercury banking API.
Requires environment variables: MERCURY_TOKEN, MERCURY_SAVINGS_ACCOUNT_UUID
"""

import os
import httpx
from langchain_core.tools import tool

MERCURY_API_URL = "https://api.mercury.com/api/v1"

http_client = httpx.Client(timeout=30.0)


@tool
def get_mercury_balance() -> str:
    """Get the current balance of the Mercury savings account.
    
    Returns the current balance, available balance, and account status.
    """
    api_token = os.environ.get("MERCURY_TOKEN")
    account_id = os.environ.get("MERCURY_SAVINGS_ACCOUNT_UUID")
    
    if not api_token:
        return "Error: Missing MERCURY_TOKEN environment variable"
    if not account_id:
        return "Error: Missing MERCURY_SAVINGS_ACCOUNT_UUID environment variable"
    
    try:
        response = http_client.get(
            f"{MERCURY_API_URL}/account/{account_id}",
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
        )
        
        if response.status_code != 200:
            return f"Error from Mercury API: {response.status_code} - {response.text}"
        
        account = response.json()
        
        name = account.get("name", "Unknown Account")
        current_balance = account.get("currentBalance", 0)
        available_balance = account.get("availableBalance", 0)
        currency = account.get("currency", "USD")
        status = account.get("status", "unknown")
        
        # Calculate pending amount
        pending = current_balance - available_balance
        
        lines = [
            f"💰 Mercury Savings Account: {name}",
            f"",
            f"Current Balance: ${current_balance:,.2f} {currency}",
            f"Available Balance: ${available_balance:,.2f} {currency}",
        ]
        
        if pending != 0:
            lines.append(f"Pending: ${pending:,.2f} {currency}")
        
        lines.append(f"Status: {status}")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error fetching Mercury balance: {str(e)}"

