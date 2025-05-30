#!/usr/bin/env python3
"""
Send WhatsApp notifications from the log file
This script reads the notifications log and sends them via WhatsApp MCP
"""

import sys
from pathlib import Path
from datetime import datetime

# Read the notifications log
log_file = Path("/home/craigmbrown/Project/Limitless-Lifelog-Manager/output/whatsapp_notifications.log")

if not log_file.exists():
    print("No notifications log found")
    sys.exit(0)

# Read all notifications
with open(log_file, 'r') as f:
    lines = f.readlines()

# Find notifications that haven't been sent
# For now, just print the last notification
if lines:
    # Extract the message (skip the timestamp)
    last_notification = ""
    for line in lines:
        if " - " in line:
            timestamp, message = line.split(" - ", 1)
            last_notification = message.strip()
    
    if last_notification:
        print(f"Latest notification to send:\n{last_notification}")
        # In Claude environment, this would use mcp__whatsapp__send_message
        # For testing, just print it