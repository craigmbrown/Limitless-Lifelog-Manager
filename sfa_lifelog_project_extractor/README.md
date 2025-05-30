# SFA Lifelog Project Extractor

An automated system that extracts lifelog data from Limitless API, processes it using multiple AI models, and creates structured projects, tasks, and todos in Notion databases.

## Key Features

### Primary Keyword Filtering
- **Default behavior**: Only processes transcripts containing the primary keyword "TB" (case-insensitive)
- Extracts context (50 words before and after) around each keyword occurrence
- Uses context to understand instructions and generate relevant items
- Can be disabled with `--no-keyword-filter` flag

### Multi-Model AI Analysis
- OpenAI o3-mini (no temperature parameter)
- Anthropic Claude 3.7 Sonnet
- Google Gemini 2.5 Pro
- Generates consolidated summaries from all models

### Comprehensive Project Generation
- Creates projects with full business cases, rationales, and value propositions
- Links tasks as children of projects
- Generates actionable todos with context
- Populates all Notion fields (dates, status, priority, tags)

### Smart Features
- Timestamp-based file versioning (no overwrites)
- WhatsApp notifications with metrics
- Configurable keyword system
- Error handling and retries

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up environment variables in `.env`:
   ```
   LIMITLESS_API_KEY=your_key
   OPENAI_API_KEY=your_key
   ANTHROPIC_API_KEY=your_key
   GEMINI_API_KEY=your_key
   NOTION_INTERNAL_INTEGRATION_SECRET=your_key
   ```

## Usage

### Basic Usage

```bash
# Process yesterday's data (default) - requires "TB" keyword
python sfa_lifelog_project_extractor.py

# Process without keyword filtering (all transcripts)
python sfa_lifelog_project_extractor.py --no-keyword-filter

# Process specific date range
python sfa_lifelog_project_extractor.py --start_date 2025-01-20 --end_date 2025-01-25

# Use specific models
python sfa_lifelog_project_extractor.py --models openai:o3-mini anthropic:claude-3-7-sonnet-20250219
```

### Keyword Configuration

Edit `keywords_config.json` to customize:
- `primary_keywords`: Keywords that must be present (default: ["TB", "TheBaby", "the baby"])
- `context_window_words`: Words to extract around keywords (default: 50)
- `project_keywords`: Keywords to identify projects
- `task_keywords`: Keywords to identify tasks
- `todo_keywords`: Keywords to identify todos

### Output Structure

```
output/
├── 2025-01-26/
│   ├── transcripts/
│   │   └── transcript-*.md (with keyword contexts)
│   ├── summary-*.md (per model and consolidated)
│   └── load/
│       └── project-task-todo-*.json
└── whatsapp_notifications.log
```

## Workflow

1. **Extract**: Fetches transcripts from Limitless API
2. **Filter**: Checks for primary keywords (if enabled)
3. **Analyze**: Sends to multiple AI models for analysis
4. **Generate**: Creates projects, tasks, and todos
5. **Upload**: Sends to Notion databases
6. **Notify**: Logs WhatsApp notifications

## Primary Keyword System

When keyword filtering is enabled (default):
- Only transcripts containing "TB" are processed
- Context extraction helps understand user intent
- Example transcript snippet:
  ```
  "...need to create a project TB for developing the new mobile app with tasks for UI design and backend API..."
  ```
  Would extract:
  - Before: "need to create a project"
  - Keyword: "TB"
  - After: "for developing the new mobile app with tasks for UI design and backend API"

## Automation

Set up a cron job for daily processing:
```bash
0 6 * * * cd /path/to/project && python sfa_lifelog_project_extractor.py >> logs/daily.log 2>&1
```

## Troubleshooting

- **No transcripts found**: Check date range and Limitless API data
- **Keyword filtering too strict**: Use `--no-keyword-filter` or add more primary keywords
- **API errors**: Verify API keys in `.env` file
- **Notion upload fails**: Check Notion integration permissions

## Notes

- WhatsApp notifications currently log to file only (MCP tool integration required for actual sending)
- Gemini API may have quota limits
- Default date range is yesterday (not 2 days ago)