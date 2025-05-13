# Notion Agent CLI

A powerful CLI tool for managing Notion databases directly from your terminal.

## Features

- Create and update projects, tasks, and todo items in Notion databases
- Query databases with filtering and sorting
- Search for pages by title and status
- Track project progress and update statuses
- Perform batch operations on database records
- Manage properties using convenient JSON files
- Direct API integration with proper Notion data formats

## Setup and Installation

### Prerequisites

- Python 3.9+
- Notion API access (Internal Integration token)
- Node.js (for the Notion MCP server)
- Required Python packages: openai, openai-agents, pydantic, rich, python-dotenv

### Installation Steps

1. Install dependencies:
   ```bash
   pip install openai openai-agents pydantic rich python-dotenv
   npm install -g @notionhq/notion-mcp-server
   ```

2. Configure Notion API access:
   
   a. Create a Notion integration:
   - Go to https://www.notion.so/my-integrations
   - Click "Create new integration"
   - Name your integration (e.g., "Notion CLI Agent")
   - Select the required capabilities (Read content, Update content, Insert content)
   - Submit to create your integration
   - Copy the "Internal Integration Secret"
   
   b. Add your integration to Notion pages/databases:
   - Open the Notion page or database you want to access
   - Click the "..." menu in the top right
   - Select "Add connections"
   - Find your integration and add it

3. Create a `.env` file with your Notion token:
   ```bash
   echo 'NOTION_INTERNAL_INTEGRATION_SECRET=your_secret_here' > .env
   ```

## CLI Usage

### Command Structure

```bash
uv run starter_notion_agent.py <command> [arguments] [options]
```

### Basic Commands

#### Creating Projects (Easy Method)

The easiest way to create a project is using the `add-project` command with properties in a JSON file:

1. First, prepare your project_props.json file:
   ```json
   {
     "Summary": {"rich_text": [{"text": {"content": "Project description"}}]},
     "Status": {"select": {"name": "Planning"}},
     "Priority": {"select": {"name": "High"}},
     "Dates": {"date": {"start": "2023-10-01", "end": "2023-12-31"}}
   }
   ```

2. Create your project:
   ```bash
   uv run starter_notion_agent.py add-project "Your Project Title"
   ```

#### Creating Todo Items (Easy Method)

Similar to projects, use the `add-todo` command with a JSON file:

1. First, prepare your todo_props.json file:
   ```json
   {
     "Status": {"select": {"name": "Not started"}},
     "Priority": {"select": {"name": "High"}},
     "Due date": {"date": {"start": "2023-10-20"}},
     "Multi-select": {"multi_select": [{"name": "Personal"}, {"name": "Important"}]}
   }
   ```

2. Create your todo:
   ```bash
   uv run starter_notion_agent.py add-todo "Your Todo Title"
   ```

#### Searching Pages

```bash
uv run starter_notion_agent.py search "Search Term" [--status "Status"]
```

Example:
```bash
uv run starter_notion_agent.py search "Project" --status "In Progress"
```

#### Getting Database Information

```bash
uv run starter_notion_agent.py database <database_id>
```

Example:
```bash
uv run starter_notion_agent.py database 1e9e13474afd81c1bfa1c84f8b31297f
```

#### Querying a Database

```bash
uv run starter_notion_agent.py query <database_id> [--filter <filter_json>] [--sort <property>]
```

Example with filtering:
```bash
uv run starter_notion_agent.py query 1e9e13474afd81c1bfa1c84f8b31297f --filter '{"property":"Status","select":{"equals":"In Progress"}}'
```

#### Updating Task Status

```bash
uv run starter_notion_agent.py update-task-status <task_id> <status>
```

Example:
```bash
uv run starter_notion_agent.py update-task-status abc123def456 "In Progress"
```

#### Completing Todo Items

```bash
uv run starter_notion_agent.py complete-todo <todo_id>
```

### Advanced Commands

#### Batch Operations Using JSON Files

For more complex operations, the batch command with JSON files is recommended:

1. Create a JSON file for your batch operations:
   ```json
   [
     {
       "properties": {
         "Title": {"title": [{"text": {"content": "Task 1"}}]},
         "Status": {"select": {"name": "Not started"}}
       }
     },
     {
       "properties": {
         "Title": {"title": [{"text": {"content": "Task 2"}}]},
         "Status": {"select": {"name": "Not started"}}
       }
     }
   ]
   ```

2. Run the batch command:
   ```bash
   uv run starter_notion_agent.py batch 1e9e13474afd81f5badfce2bc7cc7455 "$(cat batch_operations.json)" --type create
   ```

#### Creating a Database

```bash
uv run starter_notion_agent.py create-db <parent_id> <title> <schema_json>
```

Example:
```bash
uv run starter_notion_agent.py create-db page_id "Task Tracker" '{"Name":{"title":{}},"Status":{"select":{"options":[{"name":"Not Started"},{"name":"In Progress"},{"name":"Done"}]}},"Priority":{"select":{"options":[{"name":"Low"},{"name":"Medium"},{"name":"High"}]}}}'
```

## Database Reference

The CLI works with three main databases in the TheBaby system:

### Projects Database (ID: 1e9e13474afd81c1bfa1c84f8b31297f)

Fields:
- Title (title): The project name
- Summary (rich_text): Project description
- Status (select): Planning, In Progress, Completed, etc.
- Priority (select): Low, Medium, High
- Dates (date): start and end dates

Example JSON for creating a project:
```json
{
  "Title": {"title": [{"text": {"content": "New Project"}}]},
  "Summary": {"rich_text": [{"text": {"content": "Project description"}}]},
  "Status": {"select": {"name": "Planning"}},
  "Priority": {"select": {"name": "High"}},
  "Dates": {"date": {"start": "2023-10-01", "end": "2023-12-31"}}
}
```

### Tasks Database (ID: 1e9e13474afd81f5badfce2bc7cc7455)

Fields:
- Title (title): The task name
- Project (relation): Link to a project
- Status (select): Not started, In progress, Done
- Priority (select): Low, Medium, High
- Due date (date): When the task is due
- Tags (multi_select): Categories like "Development", "Frontend", etc.

Example JSON for creating a task:
```json
{
  "Title": {"title": [{"text": {"content": "Implementation Task"}}]},
  "Project": {"relation": [{"id": "project_id_here"}]},
  "Status": {"select": {"name": "Not started"}},
  "Priority": {"select": {"name": "Medium"}},
  "Due date": {"date": {"start": "2023-11-15"}},
  "Tags": {"multi_select": [{"name": "Development"}, {"name": "Frontend"}]}
}
```

### ToDo Database (ID: 1e9e13474afd8115ac29c6fcbd9a16e2)

Fields:
- Name (title): The todo item's name
- Status (select): Not started, In progress, Done
- Priority (select): Low, Medium, High
- Due date (date): When the todo is due
- Multi-select (multi_select): Categories like "Personal", "Work", etc.

Example JSON for creating a todo:
```json
{
  "Name": {"title": [{"text": {"content": "Buy groceries"}}]},
  "Status": {"select": {"name": "Not started"}},
  "Priority": {"select": {"name": "High"}},
  "Due date": {"date": {"start": "2023-10-20"}},
  "Multi-select": {"multi_select": [{"name": "Personal"}, {"name": "Important"}]}
}
```

## Notion API Property Format Reference

Each database field type requires specific JSON formatting:

### Title Fields
```json
"Title": {
  "title": [
    {
      "text": {
        "content": "Your Title Here"
      }
    }
  ]
}
```

### Rich Text Fields
```json
"Description": {
  "rich_text": [
    {
      "text": {
        "content": "Your text content here"
      }
    }
  ]
}
```

### Select Fields
```json
"Status": {
  "select": {
    "name": "In Progress"
  }
}
```

### Multi-Select Fields
```json
"Tags": {
  "multi_select": [
    {"name": "Tag1"},
    {"name": "Tag2"}
  ]
}
```

### Date Fields
```json
"Due date": {
  "date": {
    "start": "2023-11-15"
  }
}
```

### Relation Fields
```json
"Project": {
  "relation": [
    {"id": "related_page_id"}
  ]
}
```

## Troubleshooting

### Common Errors

1. **"Name is not a property that exists" / "Status is expected to be status"**
   - Cause: Incorrect property names or formats for the database
   - Solution: Use `database` command to check the exact field names and formats

2. **"Error setting up Notion MCP server"**
   - Cause: Issues with Notion API token or MCP server
   - Solution: Verify NOTION_INTERNAL_INTEGRATION_SECRET in .env file

3. **Command line JSON parsing issues**
   - Cause: Shell breaking up JSON arguments
   - Solution: Use the JSON file methods (add-project, add-todo, or batch with file input)

### Tips for Success

- Always use the correct title field name for each database (Title for Projects/Tasks, Name for ToDo)
- Fields are case-sensitive in Notion API (Status, not status)
- When in doubt, use the JSON file approach rather than command-line JSON
- For complex property structures, create a JSON file and load it with `"$(cat file.json)"`

## Complete Command Reference

```
• search <query> [--status <status>] - Search for pages
• database <database_id> - Get database info
• query <database_id> [--filter <filter_json>] [--sort <property>] - Query database
• create-page <parent_id> <title> [--properties <json>] [--content <text>] - Create page
• create-db <parent_id> <title> <schema_json> - Create database
• batch <database_id> <operations_json> [--type create|update|archive] - Batch operations
• duplicate <page_ids_json> <new_title> [--schema <json>] - Duplicate & consolidate
• todo <page_name> - Manage todos on a page
• create-project <title> [summary] [status] [priority] [start_date] [end_date] - Create project
• create-task <title> [project_id] [status] [priority] [due_date] [tags] - Create task
• create-todo <title> [status] [priority] [due_date] [tags] - Create todo item
• update-task-status <task_id> <status> - Update task status
• complete-todo <todo_id> - Mark todo item as complete
• thebaby-todo - Create 10 new TheBaby todo items (5 MCP, 5 life related)
• add-project <title> - Create project using properties in project_props.json
• add-todo <title> - Create todo using properties in todo_props.json
```