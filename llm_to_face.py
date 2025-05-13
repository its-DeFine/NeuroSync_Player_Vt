# This software is licensed under a **dual-license model**
# For individuals and businesses earning **under $1M per year**, this software is licensed under the **MIT License**
# Businesses or organizations with **annual revenue of $1,000,000 or more** must obtain permission to use this software commercially.

# llm_to_face.py
import pygame
# import keyboard # No longer needed for main text interaction
import time      
import sys
import os
from datetime import datetime
from flask import Flask, request, jsonify # Added Flask imports
from flask_cors import CORS # Added CORS for broader compatibility if accessed from different origins

from livelink.animations.default_animation import  stop_default_animation
# from utils.stt.transcribe_whisper import transcribe_audio # Part of push-to-talk, will be addressed if that mode is reimplemented
# from utils.audio.record_audio import record_audio_until_release # Part of push-to-talk
from utils.vector_db.vector_db import vector_db
from utils.llm.turn_processing import process_turn
from utils.llm.llm_initialiser import initialize_system
from config import BASE_SYSTEM_MESSAGE, get_llm_config, setup_warnings

# --- Global Variables for Flask App ---
app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# System objects - to be initialized once
system_objects = None
llm_config_global = None
chat_history_global = None # Manage chat history globally for the session
full_history_global = None   # Manage full history globally

# --- End Global Variables ---

setup_warnings()
# llm_config = get_llm_config(system_message=BASE_SYSTEM_MESSAGE) # Moved to main_setup

# --- Class to Tee stdout to a file and original stdout ---
class Tee(object):
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()  # If you want the output to be visible immediately
    def flush(self):
        for f in self.files:
            f.flush()

def setup_logging_and_tee():
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file_path = os.path.join(logs_dir, f"player_log_{timestamp}.txt")
    original_stdout = sys.stdout
    log_file = open(log_file_path, 'w', encoding='utf-8')
    sys.stdout = Tee(original_stdout, log_file)
    print(f"--- NeuroSync Player Log Initialized: {timestamp} ---")
    print(f"Logging to: {os.path.abspath(log_file_path)}\\n")
    return log_file, original_stdout


def main_setup():
    global system_objects, llm_config_global, chat_history_global, full_history_global

    llm_config_global = get_llm_config(system_message=BASE_SYSTEM_MESSAGE)
    system_objects = initialize_system()
    # Initialize global histories from system_objects
    chat_history_global = system_objects['chat_history']
    full_history_global = system_objects['full_history']
    
    print("NeuroSync Player System Initialized for HTTP interaction.")


@app.route("/process_text", methods=['POST'])
def handle_process_text():
    global chat_history_global, full_history_global # Use global histories

    if not request.json or 'text' not in request.json:
        return jsonify({"error": "Missing 'text' in JSON payload"}), 400
    
    user_input = request.json['text']
    if not user_input:
        return jsonify({"error": "Input text cannot be empty"}), 400

    print(f"Received text input: {user_input}")

    # Access necessary components from system_objects
    chunk_queue = system_objects['chunk_queue']
    audio_queue = system_objects['audio_queue']
    
    # process_turn updates chat_history internally, but we should ensure it uses the global one
    # and that its return value (the updated history) is reassigned globally if necessary.
    # For simplicity, let's assume process_turn modifies chat_history_global in place or we reassign.
    updated_chat_history = process_turn(
        user_input, 
        chat_history_global, 
        full_history_global, 
        llm_config_global, 
        chunk_queue, 
        audio_queue, 
        vector_db, 
        base_system_message=BASE_SYSTEM_MESSAGE
    )
    chat_history_global = updated_chat_history # Ensure global history is updated

    # The actual response from process_turn isn't directly sent back here.
    # The function queues data for TTS and animation.
    # We can return a simple success message.
    return jsonify({"status": "processing", "message": "Input processed."}), 200

def cleanup_resources():
    global system_objects
    if system_objects:
        print("Cleaning up resources...")
        system_objects['chunk_queue'].join()
        system_objects['chunk_queue'].put(None)
        system_objects['tts_worker_thread'].join()
        system_objects['audio_queue'].join()
        system_objects['audio_queue'].put(None)
        system_objects['audio_worker_thread'].join()
        stop_default_animation.set()
        system_objects['default_animation_thread'].join()
        pygame.quit()
        if system_objects.get('socket_connection'):
            system_objects['socket_connection'].close()
        print("Resources cleaned up.")

# Original main() is effectively replaced by Flask server startup
# if __name__ == "__main__":
#    main()

if __name__ == "__main__":
    log_file, original_stdout = setup_logging_and_tee()
    main_setup()
    
    flask_port = int(os.getenv("PLAYER_PORT", "5001")) # Make port configurable
    print(f"Starting NeuroSync Player HTTP server on port {flask_port}...")
    
    try:
        app.run(host='0.0.0.0', port=flask_port, debug=False) # debug=False for production/container
    except KeyboardInterrupt:
        print("Flask server shutting down...")
    finally:
        cleanup_resources()
        if log_file:
            print(f"\\n--- NeuroSync Player Log Ended: {datetime.now().strftime('%Y-%m-%d_%H-%M-%S')} ---")
            log_file.close()
        sys.stdout = original_stdout
        print("NeuroSync Player server stopped.")

# Removed old main function and its try/finally block for interactive input.
# The cleanup logic is now in cleanup_resources() and called in the new __main__ block.
