# This software is licensed under a **dual-license model**
# For individuals and businesses earning **under $1M per year**, this software is licensed under the **MIT License**
# Businesses or organizations with **annual revenue of $1,000,000 or more** must obtain a to use this software commercially.

# # livelink_init.py

import socket
import logging
from livelink.connect.pylivelinkface import PyLiveLinkFace, FaceBlendShape

logging.basicConfig(level=logging.INFO)


UDP_IP = "172.22.80.1" # Updated for WSL host connection
UDP_PORT = 11111

def create_socket_connection():
    logging.info(f"Attempting to connect to UDP server at {UDP_IP}:{UDP_PORT}")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((UDP_IP, UDP_PORT))
        logging.info(f"Successfully connected socket to {UDP_IP}:{UDP_PORT}")
    except socket.error as e:
        logging.error(f"Failed to connect socket to {UDP_IP}:{UDP_PORT}: {e}")
        raise # Re-raise the exception after logging
    return s

def initialize_py_face():
    py_face = PyLiveLinkFace()
    initial_blendshapes = [0.0] * 61
    for i, value in enumerate(initial_blendshapes):
        py_face.set_blendshape(FaceBlendShape(i), float(value))
    logging.info("Initialized PyLiveLinkFace with default blendshapes.")
    return py_face
