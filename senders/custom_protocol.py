#!/usr/bin/env python3
"""
Custom congestion control protocol - Multi-Signal Adaptive Protocol.

Combines BDP estimation, delay signals, loss signals, and phase detection
to beat TCP Reno in the 5-phase training profile.
"""

from __future__ import annotations

import socket
import sys
import time
from collections import deque
from typing import Dict, Optional, Tuple

from senders.base_sender import BaseSender
from senders.packet_utils import MSS, make_packet


class CustomProtocol(BaseSender):
    """
    Multi-Signal Adaptive Protocol - beats Reno by using multiple congestion signals.
    
    Uses BDP estimation, RTT gradients, fast slow start, aggressive CA,
    and phase detection to adapt better than standard TCP.
    """
    
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        """Initialize with tuned parameters."""
        super().__init__(host, port)
        
        # congestion control state
        self.cwnd = 10.0  # start with 10 packets (faster than Reno's 1)
        self.ssthresh = 32.0
        self.in_slow_start = True
        self.in_fast_recovery = False
        self.recovery_point = 0  # highest seq before fast retransmit
        
        # BDP estimation
        self.estimated_bdp = 32.0  # initial guess
        self.bdp_multiplier = 1.0
        
        # RTT tracking for delay signals
        self.base_rtt: Optional[float] = None  # minimum RTT (propagation only)
        self.current_rtt: Optional[float] = None
        self.rtt_history: deque = deque(maxlen=10)
        self.rtt_gradient = 0.0  # how much RTT increased above base
        
        # phase detection
        self.throughput_history: deque = deque(maxlen=5)
        self.last_phase_change = time.time()
        
        # packet tracking
        self.in_flight: Dict[int, Tuple[float, bytes, int]] = {}  # seq -> (send_time, payload, retrans_count)
        self.next_seq = 0
        self.highest_acked = -1
        self.dup_ack_count = 0
        self.last_ack_id = -1
        
        # tuning parameters
        self.rtt_gradient_threshold = 1.2  # exit slow start if RTT > 1.2x base
        self.ca_increment = 2.0  # congestion avoidance increment
        self.delay_reduction_factor = 0.95  # reduce window on RTT increase
        self.initial_window = 10
    
    def estimate_bdp(self) -> float:
        """
        Estimate bandwidth-delay product from throughput and RTT.
        
        BDP tells us how many packets we can have in flight to fill the pipe
        without causing queue buildup.
        """
        if self.current_rtt is None or self.current_rtt == 0:
            return self.estimated_bdp
        
        # estimate bandwidth from recent throughput
        if len(self.throughput_history) > 0:
            avg_throughput = sum(self.throughput_history) / len(self.throughput_history)
            # throughput is in bytes/sec, convert to packets/sec
            packets_per_sec = avg_throughput / MSS
            # BDP = packets_in_flight = rate * RTT
            bdp = packets_per_sec * self.current_rtt
            # smooth the estimate
            self.estimated_bdp = 0.8 * self.estimated_bdp + 0.2 * bdp
        
        return max(self.estimated_bdp * self.bdp_multiplier, 10.0)
    
    def update_rtt_signals(self, sample_rtt: float) -> None:
        """Update RTT tracking for delay-based signals."""
        self.current_rtt = sample_rtt
        self.rtt_history.append(sample_rtt)
        
        # track base RTT (minimum = propagation delay, no queue)
        if self.base_rtt is None or sample_rtt < self.base_rtt:
            self.base_rtt = sample_rtt
        
        # calculate RTT gradient (how much above base = queue buildup)
        if len(self.rtt_history) >= 2 and self.base_rtt is not None:
            recent_avg = sum(list(self.rtt_history)[-3:]) / min(3, len(self.rtt_history))
            if self.base_rtt > 0:
                self.rtt_gradient = recent_avg / self.base_rtt  # 1.0 = no queue, >1.0 = queue building
    
    def detect_phase_transition(self) -> bool:
        """
        Detect sudden changes in RTT or throughput (phase transitions).
        
        When network switches phases, RTT or throughput changes suddenly.
        We detect this to reset our estimates and adapt faster.
        """
        if len(self.rtt_history) < 3 or len(self.throughput_history) < 3:
            return False
        
        # check for sudden RTT change (>30% = probably phase transition)
        recent_rtt = sum(list(self.rtt_history)[-3:]) / 3
        older_rtt = sum(list(self.rtt_history)[:-3]) / max(1, len(self.rtt_history) - 3)
        if older_rtt > 0 and abs(recent_rtt - older_rtt) / older_rtt > 0.3:
            return True
        
        # check for sudden throughput change (>40%)
        if len(self.throughput_history) >= 3:
            recent_tput = sum(list(self.throughput_history)[-2:]) / 2
            older_tput = self.throughput_history[0] if len(self.throughput_history) > 2 else recent_tput
            if older_tput > 0 and abs(recent_tput - older_tput) / older_tput > 0.4:
                return True
        
        return False
    
    def update_window_on_ack(self, ack_id: int) -> None:
        """Update congestion window when we get an ACK."""
        # update throughput estimate for BDP calculation
        if self.metrics.get_duration() > 0:
            tput = self.metrics.get_throughput()
            self.throughput_history.append(tput)
        
        # check for phase transition
        if self.detect_phase_transition():
            # network changed, reset our estimates
            self.estimated_bdp = self.estimate_bdp()
            self.ssthresh = max(self.estimated_bdp, 16.0)
            # re-enter slow start if we're below new threshold
            if self.cwnd < self.ssthresh:
                self.in_slow_start = True
        
        # slow start
        if self.in_slow_start:
            # grow faster when we're far from BDP, slower when close
            increment = min(2.0, max(1.0, self.estimated_bdp / max(self.cwnd, 1.0)))
            self.cwnd += increment
            
            # exit slow start if we hit threshold OR RTT gradient shows queue building
            if self.cwnd >= self.ssthresh:
                self.in_slow_start = False
            elif self.rtt_gradient > self.rtt_gradient_threshold and self.base_rtt is not None:
                # HyStart: exit early when RTT increases (queue is building, slow down)
                self.ssthresh = max(self.cwnd, self.ssthresh)
                self.in_slow_start = False
        
        # congestion avoidance
        else:
            # grow faster than Reno (2/cwnd vs 1/cwnd) because we're more aggressive
            self.cwnd += self.ca_increment / self.cwnd
        
        # delay-based proactive reduction
        if self.rtt_gradient > 1.15 and not self.in_slow_start:
            # RTT is increasing, reduce window slightly to avoid congestion
            self.cwnd *= self.delay_reduction_factor
            self.cwnd = max(self.cwnd, 1.0)
    
    def handle_loss(self, is_timeout: bool) -> None:
        """Handle packet loss (timeout or 3 dup ACKs)."""
        if is_timeout:
            # timeout: less aggressive than resetting to 1
            # use ssthresh instead of going all the way back to initial_window
            self.ssthresh = max(self.cwnd / 2.0, 2.0)
            self.cwnd = max(self.ssthresh, float(self.initial_window))  # don't go below ssthresh
            self.in_slow_start = False  # stay in CA, don't go back to slow start
            self.in_fast_recovery = False
        else:
            # 3 dup ACKs: fast retransmit
            self.ssthresh = max(self.cwnd / 2.0, 2.0)
            self.cwnd = self.ssthresh + 3.0  # inflate for dup ACKs
            self.in_fast_recovery = True
            self.recovery_point = max(seq for seq in self.in_flight.keys()) if self.in_flight else self.next_seq
    
    def send_packets(self) -> None:
        """Main packet sending loop."""
        if not self.payload_data:
            return
        
        # chunk payload into MSS-sized packets
        chunks = []
        for i in range(0, len(self.payload_data), MSS):
            chunks.append(self.payload_data[i:i + MSS])
        
        total_packets = len(chunks)
        packets_sent = 0
        packets_acked = 0
        
        print(f"Starting transfer: {len(self.payload_data):,} bytes, {total_packets} packets")
        print(f"Initial cwnd={self.cwnd:.1f}, ssthresh={self.ssthresh:.1f}")
        
        while packets_acked < total_packets:
            # send packets up to window size
            while len(self.in_flight) < int(self.cwnd) and packets_sent < total_packets:
                seq_id = packets_sent * MSS
                payload = chunks[packets_sent]
                
                send_time = self.send_packet(seq_id, payload)
                self.in_flight[seq_id] = (send_time, payload, 0)
                packets_sent += 1
            
            if not self.in_flight:
                break
            
            # wait for ACK
            try:
                ack_id, msg, ack_time = self.receive_ack()
                
                if msg.startswith("fin"):
                    self.handle_fin(ack_id)
                    break
                
                # check for duplicate ACK
                if ack_id == self.last_ack_id:
                    self.dup_ack_count += 1
                    if self.dup_ack_count == 3 and not self.in_fast_recovery:
                        # fast retransmit
                        oldest_seq = min(self.in_flight.keys())
                        if oldest_seq in self.in_flight:
                            send_time, payload, retrans_count = self.in_flight[oldest_seq]
                            self.send_packet(oldest_seq, payload)
                            self.in_flight[oldest_seq] = (time.time(), payload, retrans_count + 1)
                            self.handle_loss(is_timeout=False)
                            print(f"Fast retransmit: seq={oldest_seq}, cwnd={self.cwnd:.1f}")
                    elif self.in_fast_recovery:
                        # inflate window in fast recovery
                        self.cwnd += 1.0
                else:
                    # new ACK
                    self.dup_ack_count = 0
                    self.last_ack_id = ack_id
                    
                    # check if this ACK covers any packets we think are in flight
                    # (receiver uses cumulative ACKs, so ack_id covers all packets up to that point)
                    if ack_id > self.highest_acked:
                        self.highest_acked = ack_id
                        
                        # remove ACKed packets from in-flight (cumulative ACK covers all previous packets)
                        to_remove = [seq for seq in self.in_flight.keys() if seq + len(self.in_flight[seq][1]) <= ack_id]
                        for seq in to_remove:
                            send_time, _, retrans_count = self.in_flight.pop(seq)
                            
                            # update RTT (skip if retransmitted - Karn's algorithm)
                            is_retrans = retrans_count > 0
                            sample_rtt = ack_time - send_time
                            self.update_rtt(send_time, ack_time, is_retransmission=is_retrans)
                            if not is_retrans:
                                self.update_rtt_signals(sample_rtt)
                            
                            packets_acked += 1
                        
                        # update window
                        self.update_window_on_ack(ack_id)
                        
                        # exit fast recovery if we got ACK above recovery point
                        if self.in_fast_recovery and ack_id >= self.recovery_point:
                            self.cwnd = self.ssthresh
                            self.in_fast_recovery = False
                            print(f"Exited fast recovery: cwnd={self.cwnd:.1f}")
                    else:
                        # ACK is <= highest_acked, but might still cover packets we think are in flight
                        # (could be a delayed ACK or we missed updating highest_acked)
                        to_remove = [seq for seq in self.in_flight.keys() if seq + len(self.in_flight[seq][1]) <= ack_id]
                        for seq in to_remove:
                            if seq in self.in_flight:
                                send_time, _, retrans_count = self.in_flight.pop(seq)
                                packets_acked += 1
            
            except socket.timeout:
                # timeout: retransmit oldest unACKed packet
                if self.in_flight:
                    oldest_seq = min(self.in_flight.keys())
                    send_time, payload, retrans_count = self.in_flight[oldest_seq]
                    
                    # check if we've retransmitted this too many times
                    if retrans_count >= 5:
                        # might be stuck - check if receiver already ACKed it
                        # (receiver uses cumulative ACKs, so if highest_acked > oldest_seq, it's already ACKed)
                        if self.highest_acked >= oldest_seq + len(payload):
                            # receiver already ACKed this, remove it
                            self.in_flight.pop(oldest_seq)
                            print(f"Removed seq={oldest_seq} - already ACKed (highest_acked={self.highest_acked})")
                            continue
                    
                    self.send_packet(oldest_seq, payload)
                    self.in_flight[oldest_seq] = (time.time(), payload, retrans_count + 1)
                    self.handle_loss(is_timeout=True)
                    print(f"Timeout: retransmit seq={oldest_seq} (retry {retrans_count + 1}), cwnd={self.cwnd:.1f}")
                else:
                    # no packets in flight - might be done or stuck
                    if packets_acked >= total_packets:
                        break
                    print("Timeout with no packets in flight - waiting for final ACKs", file=sys.stderr)
        
        # send EOF marker
        eof_seq = total_packets * MSS
        self.send_packet(eof_seq, b"")
        print(f"Sent EOF marker: seq={eof_seq}")
        
        # wait for FIN
        try:
            ack_id, msg, _ = self.receive_ack(timeout=5.0)
            if msg.startswith("fin"):
                self.handle_fin(ack_id)
        except socket.timeout:
            print("Timeout waiting for FIN", file=sys.stderr)


if __name__ == "__main__":
    # ensure /app is in path for Docker
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
    
    sender = CustomProtocol()
    sender.run()

