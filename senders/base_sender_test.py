#!/usr/bin/env python3
"""
Minimal test to verify base framework works.

Sends one packet, waits for ACK, sends EOF, handles FIN.
This verifies packet utils, RTT tracking, and basic send/receive work.
"""

import sys
import os

# ensure /app is in path so we can import senders package
# (needed when running in Docker container)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from senders.base_sender import BaseSender
from senders.packet_utils import MSS
import socket


class BaseFrameworkTest(BaseSender):
    """Test sender - just sends one packet to verify framework."""
    
    def send_packets(self) -> None:
        # send one packet
        seq_id = 0
        payload = self.payload_data[:MSS] if self.payload_data else b"test"
        send_time = self.send_packet(seq_id, payload)
        print(f"Sent packet: seq={seq_id}, bytes={len(payload)}")
        
        try:
            # wait for ACK
            ack_id, msg, ack_time = self.receive_ack()
            print(f"Received {msg} for ack_id={ack_id}")
            
            # update RTT (this tests RTT tracking)
            self.update_rtt(send_time, ack_time)
            srtt = self.rtt_tracker.get_srtt()
            rto = self.rtt_tracker.get_rto()
            print(f"RTT sample: {ack_time - send_time:.3f}s, SRTT: {srtt:.3f}s, RTO: {rto:.3f}s")
            
            # send EOF marker
            eof_seq = len(payload)
            self.send_packet(eof_seq, b"")
            print(f"Sent EOF marker: seq={eof_seq}")
            
            # wait for FIN
            ack_id, msg, _ = self.receive_ack()
            if msg.startswith("fin"):
                print(f"Received FIN, sending FIN/ACK")
                self.handle_fin(ack_id)
        except socket.timeout:
            print("Timeout waiting for ACK", file=sys.stderr)
            raise


if __name__ == "__main__":
    sender = BaseFrameworkTest()
    sender.run()

