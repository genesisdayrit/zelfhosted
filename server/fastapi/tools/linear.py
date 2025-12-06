"""
Linear Issues Tool

Fetches recently updated issues from Linear.
Requires environment variable: LINEAR_API_KEY
"""

import os
import httpx
from langchain_core.tools import tool

LINEAR_API_URL = "https://api.linear.app/graphql"

ISSUES_QUERY = """
query RecentlyUpdatedIssues($first: Int!) {
  issues(
    orderBy: updatedAt
    first: $first
  ) {
    nodes {
      identifier
      title
      state { name }
      assignee { name }
      updatedAt
      url
      team { name }
      project { name }
    }
  }
}
"""

http_client = httpx.Client(timeout=30.0)


@tool
def get_linear_issues(num_issues: int = 3) -> str:
    """Get recently updated issues from Linear across the entire org.

    Args:
        num_issues: Number of issues to fetch (default 3, max 50)
    """
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        return "Error: Missing LINEAR_API_KEY environment variable"

    num_issues = min(num_issues, 50)

    try:
        response = http_client.post(
            LINEAR_API_URL,
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
            json={
                "query": ISSUES_QUERY,
                "variables": {"first": num_issues},
            },
        )

        if response.status_code != 200:
            return f"Error from Linear API: {response.status_code} - {response.text}"

        data = response.json()

        if "errors" in data:
            return f"GraphQL Error: {data['errors']}"

        issues = data.get("data", {}).get("issues", {}).get("nodes", [])

        if not issues:
            return "No issues found."

        lines = [f"📋 {len(issues)} recently updated issues:\n"]

        for issue in issues:
            identifier = issue.get("identifier", "?")
            title = issue.get("title", "Untitled")
            state = issue.get("state", {}).get("name", "Unknown")
            assignee = issue.get("assignee")
            assignee_name = assignee.get("name") if assignee else "Unassigned"
            team = issue.get("team", {}).get("name", "")
            project = issue.get("project")
            project_name = project.get("name") if project else ""
            url = issue.get("url", "")

            lines.append(f"• [{identifier}] {title}")
            lines.append(f"  Status: {state} | Assignee: {assignee_name}")
            if team:
                lines.append(f"  Team: {team}" + (f" | Project: {project_name}" if project_name else ""))
            lines.append(f"  {url}\n")

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching Linear issues: {str(e)}"

