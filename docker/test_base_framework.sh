#!/bin/bash
# Test script for base framework that copies the senders package
# Usage: ./test_base_framework.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_NAME="ecs152a-simulator"

echo "[INFO] Copying senders package into container..."
docker cp "$SCRIPT_DIR/../senders" "$CONTAINER_NAME:/app/senders"
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to copy senders package"
    exit 1
fi
echo "[SUCCESS] Senders package copied"

echo "[INFO] Running base framework test..."
"$SCRIPT_DIR/test_sender.sh" "../senders/base_sender_test.py"

