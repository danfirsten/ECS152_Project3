#!/usr/bin/env python3
"""
Minimal test to verify the base framework works.

Sends one packet, waits for ACK, sends EOF, handles FIN.
This verifies packet utils, RTT tracking, and basic send/receive.
"""

import sys
import os
import socket

# --- Make sure Python can see the `senders` package -------------------------

# Case 1: running inside Docker, code is in /app and senders is /app/senders
app_dir = "/app"
if os.path.isdir(app_dir) and app_dir not in sys.path:
    sys.path.insert(0, app_dir)

# Case 2: running locally from the repo (this file is in <repo>/senders/)
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from senders.base_sender import BaseSender
from senders.packet_utils import MSS


class BaseFrameworkTest(BaseSender):
    """Test sender – just sends one packet and completes the handshake."""

    def send_packets(self) -> None:
        # Send a single data packet
        seq_id = 0
        payload = self.payload_data[:MSS] if getattr(self, "payload_data", None) else b"test"
        send_time = self.send_packet(seq_id, payload)

        try:
            # Wait for ACK
            ack_id, msg, ack_time = self.receive_ack()
            print(f"Received {msg} for ack_id={ack_id}")
            self.update_rtt(send_time, ack_time)

            # Send EOF (empty payload at end-of-file seq number)
            eof_seq = len(payload)
            self.send_packet(eof_seq, b"")

            # Wait for FIN from receiver and respond
            ack_id, msg, _ = self.receive_ack()
            if msg.startswith("fin"):
                print("Received FIN, sending FIN/ACK")
                self.handle_fin(ack_id)

        except socket.timeout:
            print("Timeout waiting for ACK", file=sys.stderr)
            raise


if __name__ == "__main__":
    sender = BaseFrameworkTest()
    sender.run()
