#!/usr/bin/env python3
"""
Metrics tracking - RTT estimation and transfer stats.
"""

from __future__ import annotations

import time
from typing import List, Optional


class RTTTracker:
    """
    Tracks RTT samples and calculates timeouts (RFC 6298).
    
    Uses exponential weighted moving average for smoothed RTT and variance.
    """
    
    def __init__(self, alpha: float = 0.125, beta: float = 0.25, min_rto: float = 0.2):
        """Initialize RTT tracker. Defaults from RFC 6298."""
        self.alpha = alpha
        self.beta = beta
        self.min_rto = min_rto
        
        self.srtt: Optional[float] = None  # smoothed RTT
        self.rttvar: Optional[float] = None  # RTT variance
        self.rtt_samples: List[float] = []
    
    def update(self, sample_rtt: float, is_retransmission: bool = False) -> None:
        """
        Update RTT estimates with a new sample.
        
        Uses Karn's algorithm: skip retransmissions because we can't tell
        if the ACK is for the original or retransmission.

        for reference:
        https://www.geeksforgeeks.org/computer-networks/karns-algorithm-for-optimizing-tcp/
        """
        # skip retransmissions (Karn's algorithm)
        if is_retransmission:
            return
        
        self.rtt_samples.append(sample_rtt)
        
        # initialize on first sample
        if self.srtt is None:
            self.srtt = sample_rtt
            self.rttvar = sample_rtt / 2.0
        else:
            # update using EWMA: SRTT = (1-α) * SRTT + α * sample
            self.rttvar = (1 - self.beta) * self.rttvar + self.beta * abs(self.srtt - sample_rtt)
            self.srtt = (1 - self.alpha) * self.srtt + self.alpha * sample_rtt
    
    def get_rto(self) -> float:
        """Get retransmission timeout: RTO = SRTT + 4 * RTTVAR."""
        if self.srtt is None or self.rttvar is None:
            return 1.0  # no samples yet, use conservative default
        
        rto = self.srtt + 4.0 * self.rttvar
        return max(rto, self.min_rto)
    
    def get_srtt(self) -> Optional[float]:
        """Get current smoothed RTT."""
        return self.srtt
    
    def get_rttvar(self) -> Optional[float]:
        """Get current RTT variance."""
        return self.rttvar


class TransferMetrics:
    """Tracks transfer stats: throughput, delay, jitter, score."""
    
    def __init__(self):
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.packet_delays: List[float] = []  # send to ACK time
        self.inter_packet_times: List[float] = []  # for jitter calc
        self.last_packet_time: Optional[float] = None
        self.total_bytes = 0
    
    def start_transfer(self) -> None:
        """Mark transfer start."""
        self.start_time = time.time()
    
    def end_transfer(self) -> None:
        """Mark transfer end."""
        self.end_time = time.time()
    
    def record_packet_sent(self, bytes_sent: int, send_time: float) -> None:
        """Record packet send for throughput/jitter tracking."""
        self.total_bytes += bytes_sent
        
        if self.last_packet_time is not None:
            inter_time = send_time - self.last_packet_time
            self.inter_packet_times.append(inter_time)
        self.last_packet_time = send_time
    
    def record_packet_acked(self, send_time: float, ack_time: float) -> None:
        """Record packet ACK for delay calculation."""
        delay = ack_time - send_time
        self.packet_delays.append(delay)
    
    def get_duration(self) -> float:
        """Get total transfer duration."""
        if self.start_time is None or self.end_time is None:
            return 0.0
        return max(self.end_time - self.start_time, 1e-6)  # avoid div by zero
    
    def get_throughput(self) -> float:
        """Calculate throughput in bytes/sec."""
        duration = self.get_duration()
        if duration == 0:
            return 0.0
        return self.total_bytes / duration
    
    def get_avg_delay(self) -> float:
        """Average delay from send to ACK."""
        if not self.packet_delays:
            return 0.0
        return sum(self.packet_delays) / len(self.packet_delays)
    
    def get_avg_jitter(self) -> float:
        """Jitter = std dev of inter-packet times."""
        if len(self.inter_packet_times) < 2:
            return 0.0
        
        mean = sum(self.inter_packet_times) / len(self.inter_packet_times)
        variance = sum((x - mean) ** 2 for x in self.inter_packet_times) / len(self.inter_packet_times)
        return variance ** 0.5
    
    def get_score(self) -> float:
        """
        Calculate performance metric from project spec.
        
        Metric = (Throughput / 2000) + (15 / Average Jitter) + (35 / Average delay per packet)
        """
        throughput = self.get_throughput()
        avg_delay = self.get_avg_delay()
        avg_jitter = self.get_avg_jitter()
        
        # Metric = (Throughput / 2000) + (15 / Jitter) + (35 / Delay)
        metric = (throughput / 2000.0)
        
        # add jitter component (avoid division by zero)
        if avg_jitter > 0:
            metric += 15.0 / avg_jitter
        
        # add delay component (avoid division by zero)
        if avg_delay > 0:
            metric += 35.0 / avg_delay
        
        return metric
    
    def format_csv(self) -> str:
        """Format as CSV: throughput,avg_delay,avg_jitter,score"""
        throughput = self.get_throughput()
        avg_delay = self.get_avg_delay()
        avg_jitter = self.get_avg_jitter()
        score = self.get_score()
        
        return f"{throughput:.7f},{avg_delay:.7f},{avg_jitter:.7f},{score:.7f}"

