#!/bin/bash
# Run the lifelog extractor and send WhatsApp notifications

# Set up environment
export PYTHONPATH="/home/craigmbrown/Project/Limitless-Lifelog-Manager/src:/home/craigmbrown/Project/Notion-Database-Manager:$PYTHONPATH"

# Source the .env file if it exists
if [ -f /home/craigmbrown/Project/sfa_lifelog_project_extractor/.env ]; then
    export $(cat /home/craigmbrown/Project/sfa_lifelog_project_extractor/.env | grep -v '^#' | xargs)
fi

echo "Starting Lifelog Extractor with WhatsApp notifications..."

# Run the main script
python /home/craigmbrown/Project/sfa_lifelog_project_extractor/sfa_lifelog_project_extractor.py "$@"

# Check if whatsapp_notifications.log was updated
LOG_FILE="/home/craigmbrown/Project/Limitless-Lifelog-Manager/output/whatsapp_notifications.log"

if [ -f "$LOG_FILE" ]; then
    echo ""
    echo "=== WhatsApp Notifications Log ==="
    tail -20 "$LOG_FILE"
    echo ""
    echo "Note: To send these messages to WhatsApp, run this script through Claude Code"
    echo "or use the WhatsApp MCP server directly."
fi