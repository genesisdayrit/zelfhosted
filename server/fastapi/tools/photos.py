from langchain_core.tools import tool

# Sample photo URLs (replace with real API calls later)
SAMPLE_PHOTOS = [
    {
        "id": "1",
        "url": "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800",
        "title": "Mountain Landscape",
        "timestamp": "2025-12-06T10:30:00Z",
    },
    {
        "id": "2",
        "url": "https://images.unsplash.com/photo-1469474968028-56623f02e42e?w=800",
        "title": "Forest Trail",
        "timestamp": "2025-12-06T09:15:00Z",
    },
    {
        "id": "3",
        "url": "https://images.unsplash.com/photo-1447752875215-b2761acb3c5d?w=800",
        "title": "Lake Reflection",
        "timestamp": "2025-12-05T18:45:00Z",
    },
    {
        "id": "4",
        "url": "https://images.unsplash.com/photo-1433086966358-54859d0ed716?w=800",
        "title": "Waterfall",
        "timestamp": "2025-12-05T14:20:00Z",
    },
]


@tool
def get_latest_photos(count: int = 4) -> str:
    """Get the latest photos from the photo library.

    Args:
        count: Number of photos to return (default: 4, max: 10)
    """
    count = min(max(1, count), 10)
    photos = SAMPLE_PHOTOS[:count]

    # Return as markdown images for the LLM to present
    result_lines = [f"Here are the {len(photos)} latest photos:\n"]

    for photo in photos:
        result_lines.append(f"![{photo['title']}]({photo['url']})")

    return "\n".join(result_lines)

