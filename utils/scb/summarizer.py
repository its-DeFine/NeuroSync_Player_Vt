import threading
import time
import os

from utils.scb.scb_store import scb_store
from utils.scb.color_text import ColorText

# Interval and behaviour controlled by env vars (same defaults as original)
DEFAULT_SUMMARIZER_INTERVAL = float(os.getenv("SUMMARIZER_INTERVAL_SECONDS", "3.0"))
DEFAULT_SUMMARIZER_TOKEN_BUDGET = int(os.getenv("SUMMARIZER_TOKEN_BUDGET", "200"))
DEFAULT_SUMMARY_SOURCE_LINES = int(os.getenv("SUMMARY_SOURCE_LINES", "50"))
DEFAULT_SUMMARY_MIN_SALIENCE = float(os.getenv("SUMMARY_MIN_SALIENCE", "0.4"))
DEFAULT_SUMMARY_KEEP_LAST_N = int(os.getenv("SUMMARY_KEEP_LAST_N", "15"))
DEFAULT_SUMMARIZER_DEBUG = os.getenv("SUMMARIZER_DEBUG", "False").lower() == "true"

print(f"[SummarizerThread INITIALIZING] SUMMARIZER_DEBUG from env: {os.getenv('SUMMARIZER_DEBUG')}, Parsed as: {DEFAULT_SUMMARIZER_DEBUG}")


class SummarizerThread(threading.Thread):
    """Background thread that periodically summarizes the SCB log."""

    def __init__(
        self,
        interval: float = DEFAULT_SUMMARIZER_INTERVAL,
        token_budget: int = DEFAULT_SUMMARIZER_TOKEN_BUDGET,
        source_lines: int = DEFAULT_SUMMARY_SOURCE_LINES,
        min_salience: float = DEFAULT_SUMMARY_MIN_SALIENCE,
        keep_last_n: int = DEFAULT_SUMMARY_KEEP_LAST_N,
        debug: bool = DEFAULT_SUMMARIZER_DEBUG,
        stop_event: threading.Event | None = None,
    ):
        super().__init__(daemon=True)
        self.interval = interval
        self.token_budget = token_budget
        self.source_lines = source_lines
        self.min_salience = min_salience
        self.keep_last_n = keep_last_n
        self.debug = debug
        self._stop_event = stop_event or threading.Event()
        self.name = "SummarizerThread"

    # ------------------------------------------------------------------
    def run(self):
        if self.debug:
            print(
                f"{ColorText.BLUE}[{self.name}] Started. Interval={self.interval}s, Budget={self.token_budget} tokens.{ColorText.END}"
            )
        while not self._stop_event.is_set():
            start = time.monotonic()
            try:
                self.summarize()
            except Exception as e:
                print(f"{ColorText.RED}[{self.name}] Error: {e}{ColorText.END}")
            elapsed = time.monotonic() - start
            sleep_time = max(0, self.interval - elapsed)
            self._stop_event.wait(sleep_time)
        if self.debug:
            print(f"{ColorText.BLUE}[{self.name}] Stopped.{ColorText.END}")

    # ------------------------------------------------------------------
    def summarize(self):
        if self.debug:
            print(f"{ColorText.BLUE}[{self.name}] Summarizing...{ColorText.END}")
        entries = scb_store.get_log_entries(self.source_lines)
        if not entries:
            return

        salient: list[dict] = []
        recent_idx = set(range(min(len(entries), self.keep_last_n)))
        for idx, entry in enumerate(entries):
            if entry.get("salience", 0.0) >= self.min_salience:
                salient.append(entry)
            elif idx in recent_idx and entry not in salient:
                salient.append(entry)
        if not salient:
            scb_store.set_summary("")
            return

        summary_lines: list[str] = []
        tokens_used = 0
        for e in reversed(salient):  # chronological order
            prefix = "User: " if e.get("actor") == "user" else "AI: " if e.get("actor") == "vtuber" else f"[{e.get('actor')}] "
            if e.get("type") == "directive":
                prefix = f"[Directive from {e.get('actor', 'planner')}] "
            line = prefix + e.get("text", "")
            line_tokens = len(line.split())
            if tokens_used + line_tokens <= self.token_budget:
                summary_lines.append(line)
                tokens_used += line_tokens
            else:
                break
        final_summary = "\n".join(summary_lines)
        scb_store.set_summary(final_summary)
        if self.debug:
            print(f"{ColorText.BLUE}[{self.name}] Summary updated – {tokens_used} tokens.{ColorText.END}")

    # ------------------------------------------------------------------
    def stop(self):
        self._stop_event.set() 