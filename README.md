# Limitless Lifelog

A CLI agent for processing Limitless Voice API life logs, extracting actionable items, and integrating with Notion.

## Features

- Connects to Limitless Voice API to fetch life log transcripts
- Processes and summarizes transcripts
- Extracts actionable items (tasks, meetings, projects)
- Integrates with Notion for organized tracking
- Maintains state between runs for efficient processing

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/limitless-lifelog.git
cd limitless-lifelog

# Install the package
pip install -e .
```

## Configuration

Create a `.env` file in the project root with the following variables:

```
# API Keys
LIMITLESS_API_KEY=your_limitless_api_key
NOTION_API_KEY=your_notion_api_key

# LLM Configuration
OPENAI_API_KEY=your_openai_api_key  # Optional, for using OpenAI
ANTHROPIC_API_KEY=your_anthropic_api_key  # Optional, for using Claude

# Default LLM Settings
DEFAULT_LLM_PROVIDER=openai  # options: openai, anthropic
DEFAULT_LLM_MODEL=gpt-4

# Notion Database IDs
NOTION_TASKS_DB_ID=your_notion_tasks_database_id
NOTION_PROJECTS_DB_ID=your_notion_projects_database_id
NOTION_TODO_DB_ID=your_notion_todo_database_id
NOTION_LIFELOG_DB_ID=your_notion_lifelog_database_id
```

## Usage

```bash
# Basic usage - process since last run
lifelog

# Process only without fetching new transcripts
lifelog --process-only

# Fetch only without updating Notion
lifelog --fetch-only

# Process logs from the past N days
lifelog --days 7

# Use specific configuration file
lifelog --config /path/to/config.ini

# Enable verbose logging
lifelog --verbose

# Dry run (show actions without making changes)
lifelog --dry-run
```

## Development

```bash
# Install development dependencies
pip install -e ".[test]"

# Run tests
pytest
```

## License

MIT