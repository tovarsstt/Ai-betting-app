import requests
import os
import sys
import json
from dotenv import load_dotenv

# Load the vault
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

# Category color map for Discord embed
CATEGORY_COLORS = {
    "Finance":       0x00B09B,   # Teal — institutional
    "Geopolitics":   0xFF4500,   # Red — high stakes
    "Economics":     0x1E90FF,   # Blue — macro
    "Elections":     0x9B59B6,   # Purple — political
    "Politics":      0x9B59B6,
    "Crypto":        0xF39C12,   # Gold — volatile
    "Sports":        0x2ECC71,   # Green — action
    "Entertainment": 0x95A5A6,   # Grey — low priority
    "General":       0x95A5A6,
}

MACRO_CATEGORIES = {"Finance", "Geopolitics", "Economics"}

def send_trade_notification(category, title, side, ev, dissonance, rationale,
                             strike_type="GRINDER_YIELD_HUNTER", macro_sentiment=None):
    """
    Sends a rich Discord embed notification for Grinder Protocol strikes.
    Finance/Geopolitics trades include a [Macro Sentiment] field.
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("⚠️  NOTIFICATION SKIPPED: DISCORD_WEBHOOK_URL NOT FOUND")
        return

    embed_color = CATEGORY_COLORS.get(category, 0x5814783)
    strike_label = strike_type.replace('_', ' ')

    # Base fields
    fields = [
        {"name": "🌐 Domain",          "value": category,          "inline": True},
        {"name": "⚡ Vector",           "value": side.upper(),      "inline": True},
        {"name": "📈 Alpha Edge",       "value": f"+{ev}%",         "inline": True},
        {"name": "🧠 Dissonance",       "value": f"{dissonance}/10","inline": True},
        {"name": "🎯 Target",           "value": title,             "inline": False},
        {"name": "🔬 Why We Trade",     "value": rationale[:1020],  "inline": False},
    ]

    # Macro Sentiment field: only for Finance / Geopolitics / Economics
    if category in MACRO_CATEGORIES and macro_sentiment:
        fields.insert(-1, {
            "name": "🌍 [Macro Sentiment]",
            "value": macro_sentiment[:1020],
            "inline": False
        })

    payload = {
        "embeds": [{
            "title":       f"🦅 GOD-ENGINE: {strike_label}",
            "description": f"Omniscient Oracle has identified a mispriced reality.",
            "color":       embed_color,
            "fields":      fields,
            "footer":      {"text": f"Apex v18.2 | {category} | Certainty Gate: 90%+ ONLY"}
        }]
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ UNIVERSAL NOTIFICATION SENT.")
    except Exception as e:
        print(f"❌ NOTIFICATION FAILED: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            data = json.loads(sys.argv[1])
            send_trade_notification(
                category=data.get("category", "General"),
                title=data.get("title", "Unknown Market"),
                side=data.get("side", "N/A"),
                ev=data.get("ev", 0),
                dissonance=data.get("dissonance", 0),
                rationale=data.get("rationale", "No rationale provided."),
                strike_type=data.get("strike_type", "GRINDER_YIELD_HUNTER"),
                macro_sentiment=data.get("macro_sentiment")
            )
        except Exception as e:
            print(f"❌ NOTIFIER CLI ERROR: {str(e)}")
    else:
        # Confirmation test
        send_trade_notification(
            "Finance",
            "Fed Rate Decision — March 2026",
            "NO CHANGE",
            "4.0",
            "9.8",
            "Fed dot-plot and Powell's last statement confirm no rate movement. Market at $0.96 represents a mathematical free edge.",
            strike_type="GRINDER_YIELD_HUNTER",
            macro_sentiment="PCE inflation at 2.4% — below Fed threshold. Job market cooling but not collapsing. All macro signals point to Federal Reserve holding rates steady through at least May 2026."
        )
