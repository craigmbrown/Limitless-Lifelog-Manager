# Limitless Lifelog - Architecture Specification

## Overview

Limitless Lifelog is a CLI agent that connects Limitless Voice API and Notion to automate the process of extracting actionable items from voice logs, organizing them, and tracking them in Notion databases.

## Core Components

### 1. Main Module (`__main__.py`)

The entry point for the application that:
- Parses command-line arguments
- Initializes logging
- Orchestrates the workflow between components
- Handles errors gracefully

### 2. Configuration (`utils/config.py`)

Manages settings from multiple sources:
- Environment variables
- Configuration files
- Command-line arguments

Key settings include API keys, database IDs, and LLM preferences.

### 3. State Manager (`utils/state_manager.py`)

Maintains state between runs:
- Tracks last execution time
- Records processed transcript IDs to prevent duplication
- Maintains mappings between transcript items and Notion entries
- Collects statistics for reporting

### 4. Limitless API Client (`limitless/api_client.py`)

Handles interaction with the Limitless Voice API:
- Authenticates using API keys
- Fetches transcripts with pagination
- Manages rate limits
- Handles API errors

### 5. Transcript Processor (`transcripts/processor.py`)

Processes raw transcripts:
- Filters out irrelevant content
- Generates summaries
- Loads transcripts from files
- Manages transcript archives

### 6. Item Extractor (`transcripts/extractor.py`)

Extracts structured data from transcripts:
- Uses LLM APIs to identify tasks, meetings, and projects
- Extracts dates, priorities, and relationships
- Converts relative dates to absolute dates
- Gives each item a unique ID for tracking

### 7. Data Transformer (`transcripts/transformer.py`)

Transforms extracted items to Notion-compatible format:
- Maps extracted fields to Notion properties
- Formats data according to Notion's API requirements
- Creates appropriate relationships between items
- Prepares data for multiple databases

### 8. Notion Client (`notion/client.py`)

Handles interaction with Notion API:
- Creates new database entries
- Updates existing entries
- Adds comments with contextual information
- Manages rate limits and errors

## Data Flow

1. **Fetch** - Limitless API client retrieves transcripts
2. **Process** - Transcript processor filters and summarizes content
3. **Extract** - Item extractor identifies actionable items
4. **Transform** - Data transformer converts to Notion format
5. **Update** - Notion client creates or updates database entries
6. **Record** - State manager records what was processed

## Error Handling Strategy

- **API Failures**: Exponential backoff for retries
- **Rate Limiting**: Respect API rate limits with appropriate waits
- **Processing Errors**: Continue with other transcripts if one fails
- **State Preservation**: Save state after each major step

## Configuration Details

### Environment Variables

```
# API Keys
LIMITLESS_API_KEY=your_limitless_api_key
NOTION_API_KEY=your_notion_api_key

# LLM Configuration
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
DEFAULT_LLM_PROVIDER=openai
DEFAULT_LLM_MODEL=gpt-4

# Notion Database IDs
NOTION_TASKS_DB_ID=your_notion_tasks_database_id
NOTION_PROJECTS_DB_ID=your_notion_projects_database_id
NOTION_TODO_DB_ID=your_notion_todo_database_id
NOTION_LIFELOG_DB_ID=your_notion_lifelog_database_id
```

### Command-Line Arguments

```
--fetch-only       Download transcripts without Notion updates
--process-only     Process existing transcripts without fetching new ones
--days N           Process logs from the past N days (default: since last run)
--config FILE      Specify configuration file path
--verbose          Enable detailed logging
--dry-run          Show what would be done without making changes
--transcripts-path Process transcripts from a specific file or directory
--llm-provider     Specify which LLM provider to use (openai or anthropic)
```

## External Dependencies

- **OpenAI/Anthropic API**: For NLP processing and extraction
- **Notion API**: For database operations
- **Limitless API**: For retrieving voice transcripts
- **Python Libraries**:
  - `requests`: HTTP requests
  - `python-dotenv`: Environment variable management
  - `pydantic`: Data validation
  - `loguru`: Advanced logging
  - `notion-client`: Notion API client

## Execution Flow

1. Load configuration from environment and/or config file
2. Determine processing timeframe (since last run or N days)
3. Fetch transcripts from Limitless API or from files
4. Filter and process transcripts
5. Extract actionable items using LLM
6. Transform to Notion format
7. Update Notion databases
8. Update state with current timestamp and processed IDs
9. Generate execution summary

## Testing Strategy

- **Unit Tests**: Test individual components with mocked dependencies
- **Integration Tests**: Test component interactions with test fixtures
- **End-to-End Tests**: Test full workflow with test APIs
- **Mock Data**: Use mock data for testing extraction and transformation

## Future Enhancements

1. **Web Interface**: Add a web dashboard for monitoring and configuration
2. **Scheduled Execution**: Add support for automatic scheduled runs
3. **Deduplication Improvements**: Smarter detection of duplicate items
4. **Custom Extractors**: Allow user-defined extraction patterns
5. **Two-way Sync**: Update Limitless based on changes in Notion