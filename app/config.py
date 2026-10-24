"""Central config. All keys come from environment variables (see .env.example)."""
import os

from dotenv import load_dotenv

load_dotenv()

QLOO_API_KEY = os.getenv("QLOO_API_KEY", "")
# Hackathon keys usually use a dedicated host. Confirm in the Qloo developer guide.
QLOO_BASE_URL = os.getenv("QLOO_BASE_URL", "https://hackathon.api.qloo.com")

SETLISTFM_API_KEY = os.getenv("SETLISTFM_API_KEY", "")
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY", "")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")

# How far (km) a tour stop can be from the venue and still count as "routable".
ROUTING_RADIUS_KM = float(os.getenv("ROUTING_RADIUS_KM", "450"))
CACHE_DIR = os.getenv("CACHE_DIR", ".cache")
