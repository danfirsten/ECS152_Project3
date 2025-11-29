# Project Structure Documentation

This file tracks the structure of the ECS 152A congestion control project and explains what each file does and why we need it.

---

## Core Framework (Phase 1)

### `senders/packet_utils.py`
**What it does**: Handles all the low-level packet formatting and parsing.

**Why we need it**: 
- Centralizes packet format logic so algorithms don't have to worry about byte packing/unpacking
- Ensures consistency across all implementations (4-byte signed seq_id + payload)
- Makes it easy to change packet format later if needed
- Provides validation to catch malformed packets early

**Key functions**:
- `make_packet()` - Builds packets with seq_id and payload
- `parse_ack()` - Extracts ack_id and message from receiver packets
- `validate_packet()` - Checks packet format validity

---

### `senders/metrics.py`
**What it does**: Tracks RTT samples, calculates timeouts, and collects transfer statistics.

**Why we need it**:
- RTT tracking is critical for adaptive timeout calculation (RFC 6298)
- All algorithms need the same RTT estimation logic
- Centralized metrics collection means consistent reporting across algorithms
- Handles the math for smoothed RTT, variance, and RTO calculation

**Key classes**:
- `RTTTracker` - Tracks RTT samples, calculates SRTT/RTTVAR/RTO using exponential weighted moving averages
- `TransferMetrics` - Collects throughput, delay, jitter stats and formats CSV output

---

### `senders/base_sender.py`
**What it does**: Abstract base class that provides common functionality for all congestion control algorithms.

**Why we need it**:
- Eliminates code duplication - socket setup, file loading, metrics tracking are the same for all algorithms
- Algorithms only need to implement the interesting part: `send_packets()` method
- Ensures consistent behavior (FIN/ACK handshake, metrics output, error handling)
- Makes it easy to add new algorithms - just inherit and implement the congestion control logic

**Key features**:
- Socket management and configuration
- Payload file loading from environment variables
- RTT tracking integration
- Metrics collection and CSV output
- FIN/ACK handshake handling
- Abstract `send_packets()` method for algorithms to implement

---

### `senders/__init__.py`
**What it does**: Makes `senders` a Python package and exports commonly used items.

**Why we need it**:
- Allows clean imports like `from senders import BaseSender`
- Exposes the public API of the senders package
- Makes it easier to use the framework in algorithm implementations

---

## Algorithm Implementations

*(Will be added as we implement each algorithm)*

---

## Documentation

### `docs/implementation_plan.md`
**What it does**: Comprehensive step-by-step plan for implementing all five congestion control algorithms.

**Why we need it**: 
- Provides roadmap and timeline for the project
- Documents design decisions and strategies
- Includes testing plans and success criteria
- Reference for understanding the overall project structure

---

### `docs/commenting_guide.md`
**What it does**: Documents the coding style and commenting conventions for this project.

**Why we need it**:
- Ensures consistent code style across the project
- Makes code easier to read and maintain
- Documents preferences for casual, clear comments

---

## Docker & Testing Infrastructure

*(Will document test scripts and Docker setup as needed)*

---

## Notes

- All sender implementations should inherit from `BaseSender` and implement `send_packets()`
- Packet format is fixed: 4-byte signed seq_id (big-endian) + payload (max 1020 bytes)
- Metrics are automatically collected by the base class
- RTT tracking uses RFC 6298 algorithm with Karn's algorithm for retransmissions

