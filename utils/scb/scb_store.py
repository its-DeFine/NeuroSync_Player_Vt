import os
import json
import time
import threading
from collections import deque
from typing import List, Dict

import redis  # type: ignore

# Local ColorText helper for nicer logs (optional)
from utils.scb.color_text import ColorText

# ---------------------------------------------------------------------------
# Environment-driven defaults (mirrors values in original SCB code)
# ---------------------------------------------------------------------------
DEFAULT_USE_REDIS = os.getenv("USE_REDIS_SCB", "False").lower() == "true"
DEFAULT_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_SCB_MAX_LINES = int(os.getenv("SCB_MAX_LINES", "1000"))
DEFAULT_SCB_SUMMARY_KEY = os.getenv("SCB_SUMMARY_KEY", "scs:summary")
DEFAULT_SCB_LOG_KEY = os.getenv("SCB_LOG_KEY", "scs:log")
DEFAULT_SCB_DEBUG = os.getenv("SCB_DEBUG", "False").lower() == "true"

print(f"[SCBStore INITIALIZING] SCB_DEBUG from env: {os.getenv('SCB_DEBUG')}, Parsed as: {DEFAULT_SCB_DEBUG}")


class SCBStore:
    """Shared Cognitive Blackboard store – Redis-backed with in-memory fallback."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        use_redis: bool = DEFAULT_USE_REDIS,
        redis_url: str = DEFAULT_REDIS_URL,
        max_lines: int = DEFAULT_SCB_MAX_LINES,
        log_key: str = DEFAULT_SCB_LOG_KEY,
        summary_key: str = DEFAULT_SCB_SUMMARY_KEY,
        debug: bool = DEFAULT_SCB_DEBUG,
    ):
        if self._initialized:
            return

        # Thread-safe double-checked init
        with self._lock:
            if self._initialized:
                return

            self.use_redis = use_redis
            self.redis_url = redis_url
            self.max_lines = max_lines
            self.log_key = log_key
            self.summary_key = summary_key
            self.debug = debug

            self._redis_client = None  # lazy connect
            self._memory_log = deque(maxlen=max_lines)
            self._memory_summary = ""
            self._init_lock = threading.Lock()

            if self.use_redis:
                self._initialize_redis()
            else:
                if self.debug:
                    print(f"{ColorText.YELLOW}[SCBStore] Using in-memory deque (Redis disabled){ColorText.END}")

            self._initialized = True

    # ---------------------------------------------------------------------
    # Redis helpers
    # ---------------------------------------------------------------------
    def _initialize_redis(self):
        if self._redis_client is None:
            with self._init_lock:
                if self._redis_client is None:
                    try:
                        self._redis_client = redis.from_url(self.redis_url, decode_responses=True)
                        self._redis_client.ping()
                        if self.debug:
                            print(f"{ColorText.GREEN}[SCBStore] Connected to Redis at {self.redis_url}{ColorText.END}")
                    except redis.exceptions.ConnectionError as e:
                        print(f"{ColorText.RED}[SCBStore] Redis connection failed: {e}{ColorText.END}")
                        print(f"{ColorText.YELLOW}[SCBStore] Falling back to in-memory store.{ColorText.END}")
                        self.use_redis = False
                        self._redis_client = None
                    except Exception as e:
                        print(f"{ColorText.RED}[SCBStore] Unexpected Redis error: {e}{ColorText.END}")
                        self.use_redis = False
                        self._redis_client = None

    def _get_redis_client(self):
        if self.use_redis and self._redis_client is None:
            self._initialize_redis()
        return self._redis_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def append(self, entry: dict):
        """Append a new entry to the SCB log."""
        if not all(k in entry for k in ("type", "actor", "text")):
            print(f"{ColorText.RED}[SCBStore] Invalid entry (missing fields): {entry}{ColorText.END}")
            return

        if "t" not in entry:
            entry["t"] = int(time.time())

        entry_json = json.dumps(entry)
        if self.debug:
            trunc = (entry["text"][:100] + "…") if len(entry["text"]) > 100 else entry["text"]
            print(f"{ColorText.CYAN}[SCBStore] Append: {entry['type']} | {entry['actor']} | '{trunc}'{ColorText.END}")

        client = self._get_redis_client()
        if self.use_redis and client:
            try:
                pipe = client.pipeline()
                pipe.lpush(self.log_key, entry_json)
                pipe.ltrim(self.log_key, 0, self.max_lines - 1)
                pipe.execute()
            except redis.exceptions.ConnectionError as e:
                print(f"{ColorText.RED}[SCBStore] Redis connection error: {e}{ColorText.END}")
                self.use_redis = False
                self._redis_client = None
                # fallback to memory below
            except Exception as e:
                print(f"{ColorText.RED}[SCBStore] Redis append error: {e}{ColorText.END}")
        if not self.use_redis:
            self._memory_log.appendleft(entry)

    # Convenience wrappers
    def append_chat(self, text: str, actor: str = "user", salience: float = 0.3):
        self.append({"type": "event", "actor": actor, "text": text, "salience": salience})

    def append_directive(self, text: str, actor: str = "planner", ttl: int = 15):
        self.append({"type": "directive", "actor": actor, "text": text, "ttl": ttl})

    # Retrieval helpers
    def _get_log_from_memory(self, count):
        return list(self._memory_log)[:count]

    def get_log_entries(self, count: int) -> List[Dict]:
        if count <= 0:
            return []
        client = self._get_redis_client()
        if self.use_redis and client:
            try:
                raw = client.lrange(self.log_key, 0, count - 1)
                return [json.loads(r) for r in raw]
            except redis.exceptions.ConnectionError as e:
                print(f"{ColorText.RED}[SCBStore] Redis read error: {e}{ColorText.END}")
                self.use_redis = False
                self._redis_client = None
            except Exception as e:
                print(f"{ColorText.RED}[SCBStore] Redis other error: {e}{ColorText.END}")
        return self._get_log_from_memory(count)

    def get_recent_chat(self, count: int = 3) -> str:
        entries = self.get_log_entries(self.max_lines)
        chat_lines = []
        for entry in reversed(entries):
            if entry.get("type") == "event" and entry.get("actor") == "user":
                chat_lines.append(f"User: {entry.get('text')}")
            elif entry.get("type") == "speech" and entry.get("actor") == "vtuber":
                chat_lines.append(f"AI: {entry.get('text')}")
            if len(chat_lines) >= count:
                break
        return "\n".join(chat_lines)

    # Summary helpers
    def get_summary(self) -> str:
        client = self._get_redis_client()
        if self.use_redis and client:
            try:
                s = client.get(self.summary_key)
                return s if s else ""
            except redis.exceptions.ConnectionError:
                self.use_redis = False
                self._redis_client = None
        return self._memory_summary

    def set_summary(self, summary_text: str):
        client = self._get_redis_client()
        if self.use_redis and client:
            try:
                client.set(self.summary_key, summary_text)
                return
            except redis.exceptions.ConnectionError:
                self.use_redis = False
                self._redis_client = None
        self._memory_summary = summary_text

    # Slices / full exports – simplified
    def get_full(self) -> dict:
        summary = self.get_summary()
        window = list(reversed(self.get_log_entries(self.max_lines)))
        return {"summary": summary, "window": window}


# Export singleton
scb_store = SCBStore() 