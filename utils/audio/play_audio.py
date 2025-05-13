"""
play_audio.py
-----------------
This module provides functions to play audio using Pygame. It includes
helper functions for initializing the mixer and unified playback loops.
It also supports audio conversion on the fly (e.g. raw PCM to WAV) where needed.
"""

import io
import time
import os
import logging
import pygame
from utils.audio.convert_audio import convert_to_wav
from utils.audio.gst_stream import stream_wav_to_rtmp

# Configure module-level logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# --- Helper Functions ---

def init_pygame_mixer():
    """
    Initialize the Pygame mixer only once.
    """
    if not pygame.mixer.get_init():
        pygame.mixer.init()


def sync_playback_loop():
    """
    A playback loop that synchronizes elapsed time with the music position.
    """
    start_time = time.perf_counter()
    clock = pygame.time.Clock()
    while pygame.mixer.music.get_busy():
        elapsed_time = time.perf_counter() - start_time
        current_pos = pygame.mixer.music.get_pos() / 1000.0  # convert ms to sec

        # If behind, sleep briefly; if ahead, let it catch up.
        if elapsed_time > current_pos:
            time.sleep(0.01)
        elif elapsed_time < current_pos:
            continue
        clock.tick(10)


def simple_playback_loop():
    """
    A simple playback loop that just ticks the clock until playback finishes.
    """
    clock = pygame.time.Clock()
    while pygame.mixer.music.get_busy():
        clock.tick(10)


# --- Configuration Helpers -------------------------------------------------

def _audio_mode() -> str:
    """Return the requested audio mode.

    • "rtmp"  → stream with GStreamer (default)
    • "pygame" → local playback via SDL/ALSA
    """
    return os.getenv("AUDIO_MODE", "rtmp").lower()


def _rtmp_url() -> str:
    """Return the RTMP url to push to.

    Prioritizes Twitch if TWITCH_STREAM_KEY is set, otherwise defaults to local RTMP server.
    """
    twitch_stream_key = os.getenv("TWITCH_STREAM_KEY")
    obs_host_ip = os.getenv("OBS_HOST_IP", "172.22.80.1") # WSL Host IP for local Docker

    if twitch_stream_key:
        twitch_broadcast_mode = os.getenv("TWITCH_BROADCAST_MODE", "test").lower()
        logger.info("Twitch stream key found. Target: Twitch.")
        # NOTE: Do NOT log the stream_key itself for security!
        if twitch_broadcast_mode == "live":
            logger.info("TWITCH_BROADCAST_MODE=live. Streaming to Twitch for public broadcast.")
            return f"rtmp://live.twitch.tv/app/{twitch_stream_key}"
        else:
            logger.info("TWITCH_BROADCAST_MODE=test (or not set). Streaming to Twitch in bandwidth test mode.")
            return f"rtmp://live.twitch.tv/app/{twitch_stream_key}?bandwidthtest=true"
    else:
        logger.info(f"No Twitch key found. Target: Local RTMP server at {obs_host_ip}:1935/live/mystream")
        return f"rtmp://{obs_host_ip}/live/mystream"


# --- Playback Functions ---

def play_audio_bytes(audio_bytes, start_event, sync=True):
    """
    Play audio from raw bytes.
    
    Parameters:
      - audio_bytes: audio data as bytes.
      - start_event: threading.Event to wait for before starting playback.
      - sync: if True, uses time-syncing playback loop.
    """
    try:
        init_pygame_mixer()
        audio_file = io.BytesIO(audio_bytes)
        pygame.mixer.music.load(audio_file)
        start_event.wait()  # Wait for the signal to start
        pygame.mixer.music.play()
        if sync:
            sync_playback_loop()
        else:
            simple_playback_loop()
    except pygame.error as e:
        print(f"Error in play_audio_bytes: {e}")


def play_audio_from_memory(audio_data, start_event, sync=False):
    """
    Play audio from memory (assumes valid WAV bytes).
    Uses a simple playback loop.
    """
    try:
        init_pygame_mixer()
        audio_file = io.BytesIO(audio_data)
        pygame.mixer.music.load(audio_file)
        start_event.wait()
        pygame.mixer.music.play()
        simple_playback_loop()
    except pygame.error as e:
        if "Unknown WAVE format" in str(e):
            print("Unknown WAVE format encountered. Skipping to the next item in the queue.")
        else:
            print(f"Error in play_audio_from_memory: {e}")
    except Exception as e:
        print(f"Error in play_audio_from_memory: {e}")


def play_audio_from_path(audio_path, start_event, sync=True):
    """
    Play audio from a file path. If the format is unsupported,
    automatically convert it to WAV.
    """
    mode = _audio_mode()

    # -------------------------------------------------------------
    # Primary path: GStreamer streaming (default)
    # -------------------------------------------------------------
    if mode != "pygame":
        rtmp_url = _rtmp_url()
        logger.info(f"[Audio] Streaming {audio_path} to {rtmp_url} (mode={mode})")
        start_event.wait()
        try:
            stream_wav_to_rtmp(audio_path, rtmp_url, blocking=True)
        except Exception as stream_error:
            logger.error(f"[Audio] GStreamer streaming failed: {stream_error}")
        return

    # -------------------------------------------------------------
    # Secondary path: local playback via pygame
    # -------------------------------------------------------------
    try:
        logger.info(f"[Audio] Attempting pygame playback: {audio_path}")
        init_pygame_mixer()
        try:
            pygame.mixer.music.load(audio_path)
        except pygame.error:
            logger.info(f"Unsupported format for {audio_path}. Converting to WAV.")
            audio_path = convert_to_wav(audio_path)
            pygame.mixer.music.load(audio_path)

        start_event.wait()
        pygame.mixer.music.play()
        logger.info("Playback via pygame started successfully.")
        if sync:
            sync_playback_loop()
        else:
            simple_playback_loop()
    except pygame.error as e:
        logger.error("Pygame playback failed (%s) and AUDIO_MODE=pygame. No fallback executed.", e)


def read_audio_file_as_bytes(file_path):
    """
    Read a WAV audio file from disk as bytes.
    Only WAV files are supported.
    """
    if not file_path.lower().endswith('.wav'):
        print(f"Unsupported file format: {file_path}. Only WAV files are supported.")
        return None
    try:
        with open(file_path, 'rb') as f:
            return f.read()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None
    except Exception as e:
        print(f"Error reading audio file: {e}")
        return None
