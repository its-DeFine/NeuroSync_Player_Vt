# This software is licensed under a **dual-license model**
# For individuals and businesses earning **under $1M per year**, this software is licensed under the **MIT License**
# Businesses or organizations with **annual revenue of $1,000,000 or more** must obtain permission to use this software commercially.

# llm_to_face.py
import pygame
import keyboard  
import time      
import sys
import os
from datetime import datetime
from livelink.animations.default_animation import  stop_default_animation
from utils.stt.transcribe_whisper import transcribe_audio
from utils.audio.record_audio import record_audio_until_release
from utils.vector_db.vector_db import vector_db
from utils.llm.turn_processing import process_turn
from utils.llm.llm_initialiser import initialize_system
from config import BASE_SYSTEM_MESSAGE, get_llm_config, setup_warnings

setup_warnings()
llm_config = get_llm_config(system_message=BASE_SYSTEM_MESSAGE)

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

def main():
    # --- Setup logging to file ---
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file_path = os.path.join(logs_dir, f"player_log_{timestamp}.txt")

    original_stdout = sys.stdout
    log_file = open(log_file_path, 'w', encoding='utf-8')
    sys.stdout = Tee(original_stdout, log_file)

    print(f"--- NeuroSync Player Log Initialized: {timestamp} ---")
    print(f"Logging to: {os.path.abspath(log_file_path)}\n")
    # --- End logging setup ---

    system_objects = initialize_system()
    socket_connection = system_objects['socket_connection']
    full_history = system_objects['full_history']
    chat_history = system_objects['chat_history']
    chunk_queue = system_objects['chunk_queue']
    audio_queue = system_objects['audio_queue']
    tts_worker_thread = system_objects['tts_worker_thread']
    audio_worker_thread = system_objects['audio_worker_thread']
    default_animation_thread = system_objects['default_animation_thread']
    
    mode = ""
    while mode not in ['t', 'r']:
        mode = input("Choose input mode: 't' for text, 'r' for push-to-talk, 'q' to quit: ").strip().lower()
        if mode == 'q':
            return
    try:
        while True:
            if mode == 'r':
                print("\n\nPush-to-talk mode: press/hold Right Ctrl to record, release to finish.")
                while not keyboard.is_pressed('right ctrl'):
                    if keyboard.is_pressed('q'):
                        print("Recording cancelled. Exiting push-to-talk mode.")
                        return
                    time.sleep(0.01)
                audio_bytes = record_audio_until_release()
                transcription, _ = transcribe_audio(audio_bytes)
                if transcription:
                    user_input = transcription
                else:
                    print("Transcription failed. Make sure you have a stt api and it's correctly set in utils > stt > transcribe_whisper.py. Please try again.")
                    continue
            else:
                user_input = input("\n\nEnter text (or 'q' to quit): ").strip()
                if user_input.lower() == 'q':
                    break

            chat_history = process_turn(user_input, chat_history, full_history, llm_config, chunk_queue, audio_queue, vector_db, base_system_message=BASE_SYSTEM_MESSAGE)

    finally:
        chunk_queue.join()
        chunk_queue.put(None)
        tts_worker_thread.join()
        audio_queue.join()
        audio_queue.put(None)
        audio_worker_thread.join()
        stop_default_animation.set()
        default_animation_thread.join()
        pygame.quit()
        socket_connection.close()
        
        # --- Close log file and restore stdout ---
        print(f"\n--- NeuroSync Player Log Ended: {datetime.now().strftime('%Y-%m-%d_%H-%M-%S')} ---")
        if log_file:
            log_file.close()
        sys.stdout = original_stdout
        # --- End log file cleanup ---

if __name__ == "__main__":
    main()
