#!/usr/bin/env python3
"""
Base class for congestion control senders.

Handles socket setup, file loading, metrics - algorithms just implement send_packets().
"""

from __future__ import annotations

import os
import socket
import sys
import time
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from senders.metrics import RTTTracker, TransferMetrics
from senders.packet_utils import MSS, PACKET_SIZE, make_packet, parse_ack


class BaseSender(ABC):
    """
    Base class for all congestion control algorithms.
    
    Lets algorithms focus on congestion control logic.
    """
    
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        """Initialize base sender. Defaults to env vars or localhost:5001."""
        self.host = host or os.environ.get("RECEIVER_HOST", "127.0.0.1")
        self.port = port or int(os.environ.get("RECEIVER_PORT", "5001"))
        
        self.rtt_tracker = RTTTracker()
        self.metrics = TransferMetrics()
        
        self.sock: Optional[socket.socket] = None
        self.addr: Optional[Tuple[str, int]] = None
        self.payload_data: Optional[bytes] = None
        self.total_bytes = 0
    
    def load_payload(self) -> bytes:
        """
        Load payload file - checks TEST_FILE, PAYLOAD_FILE, /hdd/file.zip, file.zip.
        """
        candidates = [
            os.environ.get("TEST_FILE"),
            os.environ.get("PAYLOAD_FILE"),
            "/hdd/file.zip",
            "file.zip",
        ]
        
        for path in candidates:
            if not path:
                continue
            
            expanded = os.path.expanduser(path)
            if os.path.exists(expanded):
                with open(expanded, "rb") as f:
                    data = f.read()
                    self.total_bytes = len(data)
                    print(f"Loaded payload: {expanded} ({self.total_bytes:,} bytes)")
                    return data
        
        raise FileNotFoundError(
            "Could not find payload file (tried TEST_FILE, PAYLOAD_FILE, /hdd/file.zip, file.zip)"
        )
    
    def connect(self) -> None:
        """Create UDP socket and set initial timeout."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)  # will be updated by RTO as we get samples
        self.addr = (self.host, self.port)
        print(f"Connecting to receiver at {self.host}:{self.port}")
    
    def close(self) -> None:
        """Close socket."""
        if self.sock:
            self.sock.close()
            self.sock = None
    
    def send_packet(self, seq_id: int, payload: bytes) -> float:
        """Send a packet and return send timestamp."""
        if not self.sock:
            raise RuntimeError("Socket not connected - call connect() first")
        
        pkt = make_packet(seq_id, payload)
        send_time = time.time()
        self.sock.sendto(pkt, self.addr)
        self.metrics.record_packet_sent(len(payload), send_time)
        return send_time
    
    def receive_ack(self, timeout: Optional[float] = None) -> Tuple[int, str, float]:
        """Wait for ACK and return (ack_id, message, recv_time)."""
        if not self.sock:
            raise RuntimeError("Socket not connected - call connect() first")
        
        # use provided timeout or socket's current timeout
        if timeout is not None:
            old_timeout = self.sock.gettimeout()
            self.sock.settimeout(timeout)
        
        try:
            ack_pkt, _ = self.sock.recvfrom(PACKET_SIZE)
            recv_time = time.time()
            ack_id, msg = parse_ack(ack_pkt)
            return ack_id, msg, recv_time
        finally:
            if timeout is not None:
                self.sock.settimeout(old_timeout)
    
    def update_rtt(self, send_time: float, ack_time: float, is_retransmission: bool = False) -> None:
        """Update RTT tracker and metrics, then update socket timeout to new RTO."""
        sample_rtt = ack_time - send_time
        self.rtt_tracker.update(sample_rtt, is_retransmission)
        self.metrics.record_packet_acked(send_time, ack_time)
        
        if self.sock:
            rto = self.rtt_tracker.get_rto()
            self.sock.settimeout(rto)
    
    def handle_fin(self, ack_id: int) -> None:
        """Send FIN/ACK in response to receiver's FIN."""
        if not self.sock:
            return
        
        fin_ack = make_packet(ack_id, b"FIN/ACK")
        self.sock.sendto(fin_ack, self.addr)
        print("Sent FIN/ACK to receiver")
    
    def print_metrics(self) -> None:
        """Print metrics in format expected by test scripts."""
        duration = self.metrics.get_duration()
        throughput = self.metrics.get_throughput()
        avg_delay = self.metrics.get_avg_delay()
        avg_jitter = self.metrics.get_avg_jitter()
        score = self.metrics.get_score()
        
        print("\nTransfer complete!")
        print(f"duration={duration:.3f}s throughput={throughput:.2f} bytes/sec")
        print(f"avg_delay={avg_delay:.6f}s avg_jitter={avg_jitter:.6f}s")
        print(self.metrics.format_csv())
    
    @abstractmethod
    def send_packets(self) -> None:
        """
        Main packet sending loop - implement this in subclasses.
        
        Should handle: sending packets, ACKs, timeouts, retransmissions,
        EOF marker, and FIN/ACK handshake.
        """
        pass
    
    def run(self) -> None:
        """Main entry point - runs the full transfer."""
        try:
            self.payload_data = self.load_payload()
            self.connect()
            self.metrics.start_transfer()
            
            # run algorithm
            self.send_packets()
            
            self.metrics.end_transfer()
            self.print_metrics()
        except Exception as exc:
            print(f"Sender error: {exc}", file=sys.stderr)
            raise
        finally:
            self.close()


# minimal test to verify base class works
if __name__ == "__main__":
    class TestSender(BaseSender):
        """Test sender - just sends one packet."""
        
        def send_packets(self) -> None:
            seq_id = 0
            payload = self.payload_data[:MSS] if self.payload_data else b"test"
            send_time = self.send_packet(seq_id, payload)
            
            try:
                ack_id, msg, ack_time = self.receive_ack()
                print(f"Received {msg} for ack_id={ack_id}")
                self.update_rtt(send_time, ack_time)
                
                # send EOF
                eof_seq = len(payload)
                self.send_packet(eof_seq, b"")
                
                ack_id, msg, _ = self.receive_ack()
                if msg.startswith("fin"):
                    self.handle_fin(ack_id)
            except socket.timeout:
                print("Timeout waiting for ACK", file=sys.stderr)
                raise
    
    sender = TestSender()
    sender.run()

