#!/usr/bin/env python3
"""
Packet utilities - handles all the byte packing/unpacking stuff.
"""

from __future__ import annotations

from typing import Tuple

# packet format: 4-byte signed seq_id (big-endian) + payload
PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MSS = PACKET_SIZE - SEQ_ID_SIZE  # max segment size (payload only)


def make_packet(seq_id: int, payload: bytes) -> bytes:
    """Build a packet: seq_id + payload."""
    # truncate if too big (shouldn't happen but be safe)
    if len(payload) > MSS:
        payload = payload[:MSS]
    
    seq_bytes = int.to_bytes(seq_id, SEQ_ID_SIZE, byteorder="big", signed=True)
    return seq_bytes + payload


def parse_ack(packet: bytes) -> Tuple[int, str]:
    """Parse ACK packet from receiver. Returns (ack_id, message)."""
    if len(packet) < SEQ_ID_SIZE:
        raise ValueError(f"Packet too short: {len(packet)} bytes")
    
    ack_id = int.from_bytes(packet[:SEQ_ID_SIZE], byteorder="big", signed=True)
    # ignore decode errors in case of weird bytes
    msg = packet[SEQ_ID_SIZE:].decode(errors="ignore").strip()
    
    return ack_id, msg


def validate_packet(packet: bytes) -> bool:
    """Check if packet format looks valid."""
    if len(packet) < SEQ_ID_SIZE:
        return False
    if len(packet) > PACKET_SIZE:
        return False
    return True

