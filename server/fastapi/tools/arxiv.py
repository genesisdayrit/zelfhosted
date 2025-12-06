"""
arXiv Random Articles Tool

Fetches random research articles from arXiv in specified categories.
"""

import random
import feedparser
from langchain_core.tools import tool

ARXIV_CATEGORIES = {
    # Computer Science (most relevant)
    "cs.AI": "Artificial Intelligence",
    "cs.LG": "Machine Learning",
    "cs.CL": "Computation and Language (NLP)",
    "cs.CV": "Computer Vision",
    "cs.CR": "Cryptography and Security",
    "cs.DS": "Data Structures and Algorithms",
    "cs.DC": "Distributed Computing",
    "cs.NE": "Neural and Evolutionary Computing",
    "cs.RO": "Robotics",
    "cs.SE": "Software Engineering",
    "cs.PL": "Programming Languages",
    "cs.DB": "Databases",
    "cs.IR": "Information Retrieval",
    "cs.HC": "Human-Computer Interaction",
    # Statistics / ML
    "stat.ML": "Machine Learning (Statistics)",
    "stat.TH": "Statistics Theory",
    "stat.ME": "Methodology",
    # Physics
    "quant-ph": "Quantum Physics",
    "hep-th": "High Energy Physics - Theory",
    "gr-qc": "General Relativity",
    "cond-mat": "Condensed Matter",
    # Math
    "math.CO": "Combinatorics",
    "math.PR": "Probability",
    "math.OC": "Optimization and Control",
    "math.NT": "Number Theory",
    # Quantitative Finance
    "q-fin.ST": "Statistical Finance",
    "q-fin.TR": "Trading and Market Microstructure",
    "q-fin.PM": "Portfolio Management",
    # Economics
    "econ.TH": "Theoretical Economics",
    "econ.EM": "Econometrics",
}


def fetch_arxiv_articles(category: str, max_results: int = 5, total_fetch: int = 50) -> list[tuple[str, str, str]]:
    """Fetch articles from arXiv API and return random selection.
    
    Returns list of (title, url, summary) tuples.
    """
    base_url = "http://export.arxiv.org/api/query?"
    query = f"search_query=cat:{category}&max_results={total_fetch}&sortBy=lastUpdatedDate&sortOrder=descending"
    
    feed = feedparser.parse(base_url + query)
    
    entries = []
    for entry in feed.entries:
        title = entry.title.replace("\n", " ").strip()
        url = entry.link
        # Get first ~200 chars of summary
        summary = entry.summary.replace("\n", " ").strip()[:200] + "..."
        entries.append((title, url, summary))
    
    if not entries:
        return []
    
    return random.sample(entries, min(max_results, len(entries)))


@tool
def get_arxiv_articles(
    category: str = "",
    num_articles: int = 5,
    num_categories: int = 1,
) -> str:
    """Fetch random research articles from arXiv.
    
    Can fetch from a specific category or random categories.
    
    Args:
        category: arXiv category code (e.g. 'cs.AI', 'cs.LG', 'stat.ML', 'quant-ph'). 
                  Leave empty for random categories.
        num_articles: Number of articles to fetch per category (default 5)
        num_categories: Number of random categories to sample if category is empty (default 1)
    """
    try:
        lines = []
        
        if category:
            # Specific category requested
            categories_to_fetch = [category]
        else:
            # Random categories
            categories_to_fetch = random.sample(
                list(ARXIV_CATEGORIES.keys()), 
                min(num_categories, len(ARXIV_CATEGORIES))
            )
        
        for cat in categories_to_fetch:
            cat_name = ARXIV_CATEGORIES.get(cat, cat)
            articles = fetch_arxiv_articles(cat, num_articles)
            
            if not articles:
                lines.append(f"📚 {cat_name} ({cat}): No articles found\n")
                continue
            
            lines.append(f"📚 {cat_name} ({cat}):\n")
            
            for i, (title, url, summary) in enumerate(articles, 1):
                lines.append(f"{i}. {title}")
                lines.append(f"   {url}")
                lines.append(f"   {summary}\n")
            
            lines.append("")
        
        if not lines:
            return "No articles found. Try a different category."
        
        # Add available categories hint
        lines.append("---")
        lines.append("💡 Popular categories: cs.AI, cs.LG, cs.CL, cs.CV, stat.ML, quant-ph, q-fin.ST")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error fetching arXiv articles: {str(e)}"

