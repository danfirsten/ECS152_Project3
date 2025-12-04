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

### `senders/base_sender_test.py`
**What it does**: Minimal test implementation to verify the base framework works.

**Why we need it**:
- Tests packet sending/receiving
- Verifies RTT tracking works
- Checks metrics collection
- Validates FIN/ACK handshake
- Confirms the framework is ready for algorithm implementations

**How to run**:

**Option 1: Using Docker (recommended for Windows)**
```batch
cd docker
test_sender.bat ..\senders\base_sender_test.py file.zip
```

The `test_sender.bat` script automatically copies the `senders` package into the container at `/app/senders` so Python can import it. The test file also adds `/app` to `sys.path` to ensure imports work.

**Option 2: Local testing (Windows)**
```powershell
cd C:\Users\danfi\OneDrive\Desktop\Project3\ECS-152a-Project-3-Congestion-Control
$env:TEST_FILE = "docker\file.zip"
python -m senders.base_sender_test
```

**Expected output**: Should see:
- Packet sent and ACK received
- RTT sample calculated
- EOF marker sent
- FIN/ACK handshake completed
- CSV metrics printed (throughput, delay, jitter, score)

---

## Algorithm Implementations

### `senders/custom_protocol.py`
**What it does**: Multi-Signal Adaptive Protocol - custom congestion control designed to outperform TCP Reno.

**Why we need it**:
- Phase 6 requirement: must beat TCP Reno's performance
- Combines multiple congestion signals for better adaptation
- Handles the 5-phase training profile better than standard TCP

**Key features**:
- **BDP Estimation**: Estimates bandwidth-delay product to set optimal window sizes
- **RTT Gradient Monitoring**: Detects queue buildup before packet loss (delay-based signals)
- **HyStart-like Slow Start**: Exits slow start early when RTT increases (queue building)
- **Aggressive Congestion Avoidance**: Faster window growth than Reno (2/cwnd vs 1/cwnd)
- **Fast Retransmit/Recovery**: Reno-style fast recovery for packet loss
- **Phase Transition Detection**: Detects network phase changes and adapts quickly

**How to run**:
```batch
cd docker
test_sender.bat ..\senders\custom_protocol.py file.zip
```

**Design decisions**:
- Initial window: 10 packets (faster start than Reno's 1)
- Slow start exit: When cwnd >= ssthresh OR RTT gradient > 1.2x base RTT
- Congestion avoidance: cwnd += 2/cwnd per ACK (more aggressive than Reno)
- Delay-based reduction: Reduce window by 5% when RTT gradient > 1.15x
- Fast recovery: Inflate window during dup ACKs, deflate on new ACK

**Expected performance**: 45-55 Mbps (30-50% improvement over TCP Reno)

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

### `docker/test_sender.bat` / `docker/test_sender.sh`
**What it does**: Test script that copies your sender into the Docker container and runs it with the network simulator.

**Why we need it**:
- Automates the Docker workflow (copying files, starting receiver, running sender)
- Handles Windows and Linux/macOS paths correctly
- Sets up environment variables for payload files
- For base framework testing, it also copies the `senders` package into the container

**How to use**:
```batch
cd docker
test_sender.bat ..\senders\base_sender_test.py file.zip
```

**Windows-specific notes**:
- The script has been modified to copy the `senders` package into `/app/senders` in the container (lines 127-137 in `test_sender.bat`)
- This ensures Python can find the `senders` module when running inside Docker
- The `base_sender_test.py` file also adds `/app` to `sys.path` as a backup to handle import issues

---

## Notes

- All sender implementations should inherit from `BaseSender` and implement `send_packets()`
- Packet format is fixed: 4-byte signed seq_id (big-endian) + payload (max 1020 bytes)
- Metrics are automatically collected by the base class
- RTT tracking uses RFC 6298 algorithm with Karn's algorithm for retransmissions
- Custom protocol automatically saves metrics with parameter values for easy comparison

