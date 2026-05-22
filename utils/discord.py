import requests


def send_notification(webhook_url, site, detected_at, diff_snippet):
    timestamp = detected_at.strftime("%Y-%m-%d %H:%M:%S UTC")

    embed = {
        "title": f"Change detected: {site.name}",
        "url": site.url,
        "color": 0xE03131,
        "fields": [
            {"name": "URL", "value": site.url, "inline": False},
            {"name": "Detected at", "value": timestamp, "inline": True},
        ],
        "footer": {"text": "Watchtower"},
        "timestamp": detected_at.isoformat(),
    }

    if diff_snippet:
        snippet = diff_snippet[:900]
        embed["fields"].append({
            "name": "Changes",
            "value": f"```diff\n{snippet}\n```",
            "inline": False,
        })

    try:
        requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
    except Exception as e:
        print(f"Discord notification failed: {e}")
