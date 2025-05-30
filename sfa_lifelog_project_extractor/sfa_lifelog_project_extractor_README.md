# SFA Lifelog Project Extractor - Updated Documentation

## Overview
This script extracts lifelogs from the Limitless API, processes them to identify projects/tasks/todos, and uploads them to Notion databases.

## Recent Updates

### 1. Fixed Date Range Logic
- **Default behavior changed**: Now defaults to processing **yesterday's** logs instead of today's
- **Rationale**: This ensures you get a complete day's worth of logs (yesterday is complete, today is still in progress)
- **New flag added**: Use `--today` to process today's logs instead

### 2. Implemented New Limitless API v1 Endpoints
- **List Lifelogs**: Uses `/v1/lifelogs` endpoint with proper date filtering
- **Get Specific Lifelog**: Uses `/v1/lifelogs/{id}` endpoint for fetching individual logs
- **Pagination support**: Properly handles cursor-based pagination to get ALL logs for a date
- **Better error handling**: Handles API errors gracefully with proper logging

### 3. Improved Data Extraction
- Directly uses the date parameter from the API (no more local filtering needed)
- Properly extracts markdown content from the new API response format
- Handles timestamps correctly from the new API format

### 4. Output Path Verification
- Confirmed output path is correctly set to `/home/craigmbrown/Project/Limitless-Lifelog-Manager/output`
- Creates date-based subdirectories for organized storage

## Usage Examples

### Process yesterday's logs (default):
```bash
python sfa_lifelog_project_extractor.py
```

### Process today's logs:
```bash
python sfa_lifelog_project_extractor.py --today
```

### Process a specific date range:
```bash
python sfa_lifelog_project_extractor.py --start_date 2025-01-01 --end_date 2025-01-07
```

### Process without keyword filtering (get ALL transcripts):
```bash
python sfa_lifelog_project_extractor.py --no-keyword-filter
```

### Use custom models for analysis:
```bash
python sfa_lifelog_project_extractor.py --models "openai:gpt-4" "anthropic:claude-3-opus"
```

## New API Methods

### fetch_lifelogs_for_date(date)
- Fetches all lifelogs for a specific date
- Handles pagination automatically
- Returns list of lifelog dictionaries

### get_lifelog(lifelog_id)
- Fetches a specific lifelog by ID
- Returns lifelog dictionary or None if not found

## Output Structure
```
/home/craigmbrown/Project/Limitless-Lifelog-Manager/output/
├── 2025-01-28/
│   ├── transcripts/
│   │   ├── transcript-123456Z-abc123.md
│   │   └── ...
│   ├── logs/
│   │   ├── extraction_123456.log
│   │   └── whatsapp_notifications_123456.log
│   ├── load/
│   │   └── project-task-todo-20250128_123456.json
│   ├── summary-20250128_123456-openai_o3-mini.md
│   ├── summary-20250128_123456-anthropic_claude-3-7-sonnet-20250219.md
│   ├── summary-20250128_123456-gemini_gemini-2.5-pro-exp-03-25.md
│   └── summary-20250128_123456-consolidated.md
└── ...
```

## Environment Variables Required
- `LIMITLESS_API_KEY`: Your Limitless API key
- `OPENAI_API_KEY`: For OpenAI model summaries
- `ANTHROPIC_API_KEY`: For Anthropic model summaries  
- `GEMINI_API_KEY` or `GOOGLE_API_KEY`: For Gemini model summaries

## Troubleshooting

### No logs found
- **Run the test script first**: `python test_limitless_api.py` to verify API connectivity
- **Check your Limitless account**: Log into limitless.ai and verify you have recorded lifelogs
- **Verify API key**: Ensure your LIMITLESS_API_KEY environment variable is set correctly
- **Check the date range**: The API might not have logs for the requested dates
- **Use `--no-keyword-filter`**: This ensures you see all logs without TB keyword filtering

### API returns 0 lifelogs
If the API connects successfully but returns 0 lifelogs:
1. Log into your Limitless account at https://limitless.ai
2. Check if you have any recordings/lifelogs in your account
3. Verify the API key belongs to the same account with the lifelogs
4. Try different date ranges - older dates might have more logs
5. Check if lifelogs are being created with your Limitless device/app

### API errors
- **404 errors**: The v1/lifelogs endpoint is correct; v1/transcripts is deprecated
- **401/403 errors**: Your API key is invalid or lacks permissions
- **Check logs**: Review detailed logs in `output/{date}/logs/` directory
- **Network issues**: Verify internet connectivity and firewall settings

### Notion upload failures
- Verify Notion API key is correct
- Check database IDs match your Notion workspace
- Review error logs for specific issues
- Ensure Notion integration has access to the databases

### Debug mode
To see more detailed information:
```bash
# Set debug logging
export LOG_LEVEL=DEBUG
python sfa_lifelog_project_extractor.py --no-keyword-filter

# Or check the detailed logs
tail -f /home/craigmbrown/Project/Limitless-Lifelog-Manager/output/*/logs/extraction_*.log
```