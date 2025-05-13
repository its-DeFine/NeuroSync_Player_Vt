import os
import threading
import time

from utils.scb.scb_store import scb_store
from utils.scb.color_text import ColorText

# ---------------------------------------------------------------------------
# Environment variables controlling behaviour (mirrors original names)
# ---------------------------------------------------------------------------
ENABLE_SYSTEM2_BRIDGE = os.getenv("ENABLE_SYSTEM2_BRIDGE", "False").lower() == "true"
BRIDGE_FILE_PATH = os.getenv("BRIDGE_FILE_PATH", "bridge_player.txt")
MOCK_SYSTEM2 = os.getenv("MOCK_SYSTEM2", "False").lower() == "true"
BRIDGE_DEBUG = os.getenv("BRIDGE_DEBUG", "False").lower() == "true"

# Determine Redis usage through SCB env – we reuse the flag in scb_store.
DEFAULT_USE_REDIS = os.getenv("USE_REDIS_SCB", "False").lower() == "true"


class BridgeCache:
    """Read-only cache that exposes System-2 insights to the LLM prompt."""

    _text: str = ""
    _mtime: float = 0.0
    _lock = threading.Lock()

    @classmethod
    def read(cls) -> str:
        if not ENABLE_SYSTEM2_BRIDGE:
            return ""

        use_scb = DEFAULT_USE_REDIS
        content = ""
        needs_update = False

        if use_scb:
            # Pull from SCB summary
            try:
                summary = scb_store.get_summary()
                if summary != cls._text:
                    content = summary
                    needs_update = True
                    cls._mtime = time.time()
                else:
                    content = cls._text
            except Exception as e:
                print(f"{ColorText.RED}[BridgeCache] SCB error: {e}{ColorText.END}")
                content = cls._text
        else:
            # Fallback to file-based bridge
            try:
                mtime = os.path.getmtime(BRIDGE_FILE_PATH)
                if mtime != cls._mtime:
                    with open(BRIDGE_FILE_PATH, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    needs_update = True
                    cls._mtime = mtime
                else:
                    content = cls._text
            except FileNotFoundError:
                content = ""
            except Exception as e:
                print(f"{ColorText.RED}[BridgeCache] File error: {e}{ColorText.END}")
                content = cls._text

        if needs_update:
            with cls._lock:
                cls._text = content
                if BRIDGE_DEBUG:
                    src = "SCB" if use_scb else "File"
                    print(f"{ColorText.YELLOW}[BridgeCache] Updated from {src}.{ColorText.END}")
        return content

# ---------------------------------------------------------------------------
# Optional mock writer for quick testing
# ---------------------------------------------------------------------------

def _mock_writer():
    counter = 0
    while True:
        if not DEFAULT_USE_REDIS and ENABLE_SYSTEM2_BRIDGE and MOCK_SYSTEM2:
            line = f"[MOCK SYSTEM2] insight #{counter}"
            try:
                with open(BRIDGE_FILE_PATH, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                if BRIDGE_DEBUG:
                    print(f"{ColorText.BLUE}[BridgeCache] Mock write: {line}{ColorText.END}")
            except Exception as e:
                print(f"{ColorText.RED}[BridgeCache] Mock writer error: {e}{ColorText.END}")
            counter += 1
        time.sleep(10)

if ENABLE_SYSTEM2_BRIDGE and MOCK_SYSTEM2:
    t = threading.Thread(target=_mock_writer, daemon=True)
    t.start() 