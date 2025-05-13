#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "openai",
#   "openai-agents",
#   "pydantic",
#   "rich",
#   "python-dotenv",
#   "psutil"
# ]
# ///

import os
import sys
import asyncio
import json
import signal
import io  # For redirecting stdout
from typing import Any, List, Dict, Optional, Union
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import print as rprint
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Import the agents module first before any monkey patching
from agents import Agent, Runner, function_tool
from agents.mcp.server import MCPServerStdio

# Initialize rich console
console = Console()

# Constants
MODEL = "o4-mini"  # OpenAI model to use for all agents (adjust as needed)

# Import the original Runner module - do this before patching
from agents import Runner as OriginalRunner

# Create a silent version of the Runner.run method
_original_run = OriginalRunner.run

# Patch the Runner.run method to be silent
async def silent_run(*args, **kwargs):
    # Save original stdout and stderr
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    # Create dummy buffers
    dummy_out = io.StringIO()
    dummy_err = io.StringIO()
    
    # Redirect output
    sys.stdout = dummy_out
    sys.stderr = dummy_err
    
    try:
        # Run the original method
        return await _original_run(*args, **kwargs)
    finally:
        # Always restore output
        sys.stdout = original_stdout
        sys.stderr = original_stderr

# Replace the Runner.run method with our silent version
OriginalRunner.run = silent_run

# Improved utility class to silence output when needed
class SilenceOutput:
    def __enter__(self):
        # Save the original stdout and stderr
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        
        # Replace them with string buffers
        self._stdout_stringio = io.StringIO()
        self._stderr_stringio = io.StringIO()
        sys.stdout = self._stdout_stringio
        sys.stderr = self._stderr_stringio
        
        # Also monkey patch print to catch direct prints
        self._original_print = __builtins__.get('print')
        __builtins__['print'] = lambda *args, **kwargs: None
        
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore stdout, stderr, and print
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        __builtins__['print'] = self._original_print
        
        # Filter out API calls from the captured output
        contents = self._stdout_stringio.getvalue()
        if contents and not 'calling tool' in contents:
            # Print non-API call output back out, if desired
            # self._original_print(contents)
            pass

# Notion database IDs
PROJECTS_DATABASE_ID = "1e9e13474afd81c1bfa1c84f8b31297f"  # TheBaby Projects database
TODO_DATABASE_ID = "1e9e13474afd8115ac29c6fcbd9a16e2"      # TheBaby ToDo database
TASKS_DATABASE_ID = "1e9e13474afd81f5badfce2bc7cc7455"     # TheBaby Tasks database

# Load environment variables
load_dotenv()
NOTION_API_SECRET = os.getenv("NOTION_INTERNAL_INTEGRATION_SECRET")
if not NOTION_API_SECRET:
    console.print(
        "[bold red]ERROR: NOTION_INTERNAL_INTEGRATION_SECRET not found in environment variables.[/bold red]"
    )
    console.print(
        "\n[yellow]Please follow these steps to configure your environment:[/yellow]"
    )
    console.print(
        "1. Create a .env file: [bold]touch .env[/bold]"
    )
    console.print(
        "2. Add your Notion Internal Integration secret to the .env file: [bold]echo 'NOTION_INTERNAL_INTEGRATION_SECRET=your_secret_here' >> .env[/bold]"
    )
    console.print(
        "\n[blue]→ You can create a Notion integration at: https://www.notion.so/my-integrations[/blue]"
    )
    sys.exit(1)

# Global variable to store the singleton Notion MCP server instance
_notion_mcp_server = None

# Define our MCP server for Notion API with singleton pattern
async def get_notion_mcp_server():
    global _notion_mcp_server

    # If server is already created, return the existing instance
    if _notion_mcp_server is not None:
        return _notion_mcp_server

    # Otherwise, create a new server instance
    console.print(
        "[bold blue]📡 Setting up Notion MCP server...[/bold blue]"
    )

    # Configure headers with the Notion API token and version
    headers_json = f'{{"Authorization": "Bearer {NOTION_API_SECRET}", "Notion-Version": "2022-06-28"}}'

    try:
        # Create and store the Notion MCP server with logging completely disabled
        # and API call details suppressed
        _notion_mcp_server = MCPServerStdio(
            name="Notion API Server",
            params={
                "command": "npx",
                "args": ["-y", "--quiet", "--silent", "@notionhq/notion-mcp-server"], # Add all quiet flags
                "env": {
                    "OPENAPI_MCP_HEADERS": headers_json,
                    "OPENAPI_MCP_LOG_LEVEL": "none",              # Disable all logging
                    "OPENAPI_MCP_DISABLE_LOGGING": "1",           # Additional setting to disable logging
                    "OPENAPI_MCP_SILENT": "1",                    # Silent mode for MCP
                    "OPENAPI_MCP_HIDE_API_CALLS": "1",            # Hide API call details
                    "NODE_QUIET": "1",                            # Quiet mode for Node
                    "NODE_ENV": "production",                     # Production mode has less logging
                    "npm_config_loglevel": "silent",              # NPM silent logging
                    "NO_UPDATE_NOTIFIER": "1",                    # Disable update notifications
                    "NO_COLOR": "1",                              # Disable colorized output
                },
                "stderr": asyncio.subprocess.DEVNULL,             # Redirect stderr to /dev/null
                "stdout": asyncio.subprocess.DEVNULL,             # Redirect stdout to /dev/null
            }
        )

        await _notion_mcp_server.connect()
        console.print("[green]Notion MCP server connected successfully[/green]")
        
        return _notion_mcp_server
    except Exception as e:
        console.print(f"[bold red]ERROR setting up Notion MCP server: {str(e)}[/bold red]")
        raise

# Define the data classes for our agents
class TodoItem(BaseModel):
    id: str
    content: str
    is_completed: bool

class NotionPageContent(BaseModel):
    """Content of a Notion page, including raw content and todo items"""
    raw_content: str
    todo_items: List[TodoItem]

    def __str__(self) -> str:
        """String representation of the content"""
        todos_str = "\n".join(
            [
                f"- {'[x]' if item.is_completed else '[ ]'} {item.content} (ID: {item.id})"
                for item in self.todo_items
            ]
        )
        return f"Page Content:\n{self.raw_content}\n\nTodo Items ({len(self.todo_items)}):\n{todos_str}"

class TodoUpdateResult(BaseModel):
    """Result of updating a todo item"""
    success: bool
    message: str
    todo_id: str

class NotionPage(BaseModel):
    """Basic information about a Notion page"""
    id: str
    title: str
    url: Optional[str] = None
    database_id: Optional[str] = None
    
    def __str__(self) -> str:
        """String representation of the page"""
        return f"{self.title} (ID: {self.id})"

class NotionSearchResult(BaseModel):
    """Results from a Notion search operation"""
    pages: List[NotionPage]
    
    def __str__(self) -> str:
        """String representation of the search results"""
        if not self.pages:
            return "No pages found."
        return "\n".join([str(page) for page in self.pages])

class NotionDatabaseItem(BaseModel):
    """A record in a Notion database"""
    id: str
    title: str
    properties: Dict[str, Any]
    
    def __str__(self) -> str:
        """String representation of the database item"""
        return f"{self.title} (ID: {self.id})"

class NotionDatabase(BaseModel):
    """Information about a Notion database"""
    id: str
    title: str
    url: Optional[str] = None
    schema: Dict[str, Any] = Field(default_factory=dict)
    
    def __str__(self) -> str:
        """String representation of the database"""
        return f"{self.title} Database (ID: {self.id})"

class NotionBatchOperationResult(BaseModel):
    """Results of a batch operation on Notion records"""
    success_count: int
    failure_count: int
    messages: List[str]
    
    def __str__(self) -> str:
        """String representation of the operation result"""
        status = "✅ Success" if self.failure_count == 0 else "⚠️ Partial Success" if self.success_count > 0 else "❌ Failed"
        return f"{status}: {self.success_count} succeeded, {self.failure_count} failed\n" + "\n".join(self.messages)

# Tool implementations
@function_tool
async def search_notion_pages(query: str, filter_status: Optional[str] = None) -> str:
    """
    Search for Notion pages by name and optionally filter by status.

    Args:
        query: The search query to find matching pages
        filter_status: Optional status to filter pages by (e.g. "In Review", "Complete")

    Returns:
        JSON string of matching pages with their IDs, titles, and URLs
    """
    console.print(
        f"[bold cyan]🔍 Searching for Notion pages with query: {query}{' with status: ' + filter_status if filter_status else ''}[/bold cyan]"
    )

    try:
        # Create a sub-agent with access to the Notion MCP server
        notion_search_agent = Agent(
            name="Notion Page Searcher",
            model=MODEL,
            instructions="""
            You are a specialized agent for finding Notion pages.
            Your task is to search for pages matching a query and optionally filter by status.
            
            Follow these steps:
            1. Use the Notion API search endpoint to find pages matching the query
            2. For each matching page, extract its ID, title, and URL
            3. If a status filter is provided, check if each page has that status and only include matching pages
            4. Return the results as a NotionSearchResult object
            
            Be thorough in your search and make sure to check the status properly if requested.
            """,
            output_type=NotionSearchResult,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to find matching pages
        console.print("Searching for pages...", style="bold cyan")
        # Comment out Runner.run to prevent logging to stdout
        # result = await Runner.run(
        #     notion_search_agent, 
        #     f"Find Notion pages matching the query: {query}" + 
        #     (f" and having status: {filter_status}" if filter_status else "")
        # )
        
        # Run with patched silent Runner
        result = await Runner.run(
            notion_search_agent, 
            f"Find Notion pages matching the query: {query}" + 
            (f" and having status: {filter_status}" if filter_status else "")
        )
        console.print("Search complete", style="bold green")

        # Clean up any API call output that might have leaked through
        # by setting up stdout filter to suppress API call details
        class CallFilter:
            def __init__(self, original_stdout):
                self.original_stdout = original_stdout
                self.buffer = ""
            
            def write(self, text):
                # Skip anything that looks like an API call
                if "calling tool" in text or "API-" in text:
                    return
                # Pass through other text
                self.original_stdout.write(text)
            
            def flush(self):
                self.original_stdout.flush()
        
        # Apply the filter
        sys.stdout = CallFilter(sys.__stdout__)
        
        # Get the structured result - with error handling
        try:
            search_results = result.final_output_as(NotionSearchResult)
            
            # Create a table to display the results
            table = Table(title=f"Found {len(search_results.pages)} Matching Pages")
            table.add_column("Title", style="cyan")
            table.add_column("ID", style="green")
            table.add_column("URL", style="blue")
            
            for page in search_results.pages:
                table.add_row(
                    page.title,
                    page.id,
                    page.url or "N/A"
                )
            
            # Always show the results table
            console.print(table)
        except Exception as e:
            # If we can't parse as NotionSearchResult, try direct JSON parsing
            try:
                # Try to parse as plain JSON
                search_data = json.loads(result.final_output)
                
                if isinstance(search_data, list):
                    # Create a table for JSON list result
                    table = Table(title=f"Found {len(search_data)} Matching Pages")
                    table.add_column("Title", style="cyan")
                    table.add_column("ID", style="green")
                    table.add_column("URL", style="blue")
                    
                    for page in search_data:
                        if isinstance(page, dict):
                            table.add_row(
                                page.get("title", "No title"),
                                page.get("id", "No ID"),
                                page.get("url", "N/A")
                            )
                    
                    console.print(table)
                else:
                    # Display the raw output formatted in a panel
                    console.print(Panel.fit(
                        result.final_output,
                        title="Search Results",
                        border_style="cyan"
                    ))
            except:
                # Last resort - just show the raw output
                console.print(Panel.fit(
                    result.final_output,
                    title="Search Results",
                    border_style="cyan"
                ))
        
        # Return the results as JSON (either from structured result or direct JSON)
        try:
            # Try to return from structured result first
            if 'search_results' in locals() and hasattr(search_results, 'pages'):
                return json.dumps([{
                    "id": page.id,
                    "title": page.title,
                    "url": page.url,
                    "database_id": page.database_id
                } for page in search_results.pages])
            # Otherwise, if we parsed JSON directly, return that
            elif 'search_data' in locals() and isinstance(search_data, list):
                return json.dumps(search_data)
            else:
                # Last resort - return the raw output if nothing else worked
                return result.final_output
        except Exception:
            # If all else fails, return an empty result
            return json.dumps({"error": "Could not parse search results"})
        finally:
            # Always restore stdout to its original state
            sys.stdout = sys.__stdout__

    except Exception as e:
        error_message = f"ERROR finding Notion pages: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return json.dumps({"error": error_message})

@function_tool
async def find_notion_page(page_name: str) -> str:
    """
    Find a Notion page ID based on its name.

    Args:
        page_name: The name of the Notion page to find

    Returns:
        The page ID if found, or an error message
    """
    console.print(
        f"[bold cyan]🔍 Searching for Notion page: {page_name}[/bold cyan]"
    )

    try:
        # Create a sub-agent with access to the Notion MCP server
        notion_search_agent = Agent(
            name="Notion Page Finder",
            model=MODEL,
            instructions="""
            You are a specialized agent for finding Notion pages.
            Your task is to search for a specific page by name and return its ID.
            Use the Notion API tools provided to you to search for the page.
            If multiple pages match, return the most relevant one.
            If no pages match, return a clear error message.
            
            IMPORTANT: Return ONLY the page ID as a string without any additional text or formatting.
            For example, if you find a page with ID "1e0fc382-ac73-806e-a28d-cc99f7d75096", just return that ID.
            """,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to find the page - using SilenceOutput to hide API calls
        console.print("Searching for page...", style="bold cyan")
        with SilenceOutput():
            result = await Runner.run(
                notion_search_agent, f"Find the Notion page with the name: {page_name}"
            )
        
        # Extract the page ID from the result
        page_id = result.final_output.strip()
        console.print(f"[green]✓ Found page with ID: {page_id}[/green]")
        return page_id

    except Exception as e:
        # Capture and format the error
        error_message = f"ERROR finding Notion page: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return f"ERROR: {error_message}"

@function_tool
async def get_notion_page_content(page_id: str) -> str:
    """
    Get the content of a Notion page, specifically focusing on todo items.

    Args:
        page_id: The ID of the Notion page

    Returns:
        A string representation of the page content and todo items
    """
    console.print(
        f"[bold cyan]📄 Retrieving content for page ID: {page_id}[/bold cyan]"
    )

    # Create a sub-agent with access to the Notion MCP server
    notion_content_agent = Agent(
        name="Notion Content Retriever",
        model=MODEL,
        instructions="""
        You are a specialized agent for retrieving Notion page content.
        Your task is to get the content of a specific page by ID and:
        1. Extract the page's raw content as text
        2. Find and extract all todo items on the page
        
        For each todo item, extract:
        - Its ID 
        - Content text
        - Completion status (true if completed, false if not)
        
        Use the Notion API to retrieve the page blocks and look for to_do blocks.
        Return this information in the structured NotionPageContent format.
        """,
        output_type=NotionPageContent,
        mcp_servers=[await get_notion_mcp_server()],
    )

    # Run the agent to get the page content - using SilenceOutput to hide API calls
    console.print("Retrieving page content...", style="bold cyan")
    with SilenceOutput():
        result = await Runner.run(
            notion_content_agent,
            f"Get the content of the Notion page with ID: {page_id}. Return both the raw page content and all todo items found."
        )

    # Get the structured result
    try:
        # The agent returns a structured NotionPageContent object
        page_content = result.final_output_as(NotionPageContent)
        # Convert to string for returning
        content_str = str(page_content)
        console.print(f"[green]✓ Retrieved {len(page_content.todo_items)} todo items[/green]")
    except Exception as e:
        console.print(f"[bold red]Error getting page content: {str(e)}[/bold red]")
        # Fallback to error message
        content_str = f"Error retrieving page content: {str(e)}"

    return content_str

@function_tool
async def get_notion_database(database_id: str) -> str:
    """
    Get information about a Notion database, including its schema.

    Args:
        database_id: The ID of the Notion database

    Returns:
        JSON string with database details including title, URL, and schema
    """
    console.print(f"[bold cyan]🗃️ Retrieving database info for ID: {database_id}[/bold cyan]")

    try:
        # Create a sub-agent with access to the Notion MCP server
        notion_db_agent = Agent(
            name="Notion Database Info Retriever",
            model=MODEL,
            instructions="""
            You are a specialized agent for retrieving Notion database information.
            Your task is to get detailed information about a specific database by ID including:
            1. The database title
            2. The database URL
            3. The full database schema/properties structure
            
            Use the Notion API to retrieve the database and extract this information.
            Return the information in the NotionDatabase format.
            """,
            output_type=NotionDatabase,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to get the database info - using SilenceOutput to hide API calls
        console.print("Retrieving database info...", style="bold cyan")
        with SilenceOutput():
            result = await Runner.run(
                notion_db_agent,
                f"Get detailed information about the Notion database with ID: {database_id}. Include the title, URL, and complete schema."
            )

        # Get the structured result
        db_info = result.final_output_as(NotionDatabase)
        
        # Display database info
        console.print(Panel.fit(
            f"[bold cyan]Database Title:[/bold cyan] {db_info.title}\n"
            f"[bold cyan]Database ID:[/bold cyan] {db_info.id}\n"
            f"[bold cyan]URL:[/bold cyan] {db_info.url or 'N/A'}\n"
            f"[bold cyan]Properties:[/bold cyan] {len(db_info.schema)} properties found",
            title="Database Information",
            border_style="green"
        ))
        
        # Return the database info as JSON
        return json.dumps({
            "id": db_info.id,
            "title": db_info.title,
            "url": db_info.url,
            "schema": db_info.schema
        })

    except Exception as e:
        error_message = f"ERROR retrieving database info: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return json.dumps({"error": error_message})

@function_tool
async def query_notion_database(database_id: str, filter_criteria: Optional[str] = None, sort_by: Optional[str] = None) -> str:
    """
    Query a Notion database and retrieve its records with optional filtering and sorting.

    Args:
        database_id: The ID of the Notion database to query
        filter_criteria: Optional JSON string with filter criteria
        sort_by: Optional property to sort results by (can include direction as "property:asc" or "property:desc")

    Returns:
        JSON string of database records
    """
    console.print(f"[bold cyan]🔍 Querying database: {database_id}[/bold cyan]")
    
    if filter_criteria:
        console.print(f"[bold cyan]Filter:[/bold cyan] {filter_criteria}")
    
    if sort_by:
        console.print(f"[bold cyan]Sort by:[/bold cyan] {sort_by}")

    try:
        # Create a sub-agent with access to the Notion MCP server
        notion_query_agent = Agent(
            name="Notion Database Query Agent",
            model=MODEL,
            instructions="""
            You are a specialized agent for querying Notion databases.
            Your task is to get records from a database with optional filtering and sorting.
            
            For each database record, extract:
            1. The record ID
            2. The record title (or primary field)
            3. All other properties in the record
            
            If filter criteria are provided, apply them to your query.
            If sort criteria are provided, sort the results accordingly.
            
            Return the records as a list of NotionDatabaseItem objects.
            """,
            output_type=List[NotionDatabaseItem],
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to query the database - using SilenceOutput to hide API calls
        console.print("Querying database...", style="bold cyan")
        
        # Prepare the prompt with filter and sort instructions if provided
        prompt = f"Query the Notion database with ID: {database_id}"
        if filter_criteria:
            prompt += f"\nApply this filter criteria: {filter_criteria}"
        if sort_by:
            prompt += f"\nSort the results by: {sort_by}"
            
        with SilenceOutput():
            result = await Runner.run(notion_query_agent, prompt)

        # Get the structured result
        items = result.final_output_as(List[NotionDatabaseItem])
        
        # Display query results
        table = Table(title=f"Query Results: {len(items)} Records")
        table.add_column("Title", style="cyan")
        table.add_column("ID", style="green")
        
        for item in items:
            table.add_row(item.title[:50] + "..." if len(item.title) > 50 else item.title, item.id)
        
        console.print(table)
        
        # Return the items as JSON
        return json.dumps([{
            "id": item.id,
            "title": item.title,
            "properties": item.properties
        } for item in items])

    except Exception as e:
        error_message = f"ERROR querying database: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return json.dumps({"error": error_message})

@function_tool
async def create_notion_page(parent_id: str, title: str, properties: Optional[str] = None, content: Optional[str] = None) -> str:
    """
    Create a new Notion page under a parent page or database.

    Args:
        parent_id: The ID of the parent page or database
        title: The title for the new page
        properties: Optional JSON string of additional properties (required if parent is a database)
        content: Optional content to add to the page (as markdown)

    Returns:
        JSON string with the new page ID and URL
    """
    console.print(f"[bold cyan]📝 Creating new page: {title}[/bold cyan]")
    console.print(f"[bold cyan]Parent ID:[/bold cyan] {parent_id}")

    try:
        # Create a sub-agent with access to the Notion MCP server
        notion_create_agent = Agent(
            name="Notion Page Creator",
            model=MODEL,
            instructions="""
            You are a specialized agent for creating Notion pages.
            Your task is to create a new page under a specified parent with:
            1. The specified title
            2. Any additional properties if specified (these are required if the parent is a database)
            3. Any content blocks if specified
            
            The parent can be either:
            - A page ID (create a sub-page)
            - A database ID (create a new database entry)
            
            Return the ID and URL of the newly created page.
            """,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to create the page - using SilenceOutput to hide API calls
        console.print("Creating page...", style="bold cyan")
        
        # Prepare the prompt
        prompt = f"Create a new Notion page with title: {title} under parent ID: {parent_id}"
        if properties:
            prompt += f"\nWith these properties: {properties}"
        if content:
            prompt += f"\nWith this content: {content}"
            
        with SilenceOutput():
            result = await Runner.run(notion_create_agent, prompt)

        # Extract the page ID and URL from the result
        response = result.final_output.strip()
        console.print(f"[green]✓ Successfully created page:[/green] {response}")
        
        # Try to parse the response as JSON
        try:
            data = json.loads(response)
            return json.dumps(data)
        except:
            # If not JSON, return a formatted response
            return json.dumps({
                "message": "Page created successfully",
                "response": response
            })

    except Exception as e:
        error_message = f"ERROR creating page: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return json.dumps({"error": error_message})

@function_tool
async def create_notion_database(parent_id: str, title: str, properties: str) -> str:
    """
    Create a new Notion database under a parent page.

    Args:
        parent_id: The ID of the parent page
        title: The title for the new database
        properties: JSON string defining the database schema

    Returns:
        JSON string with the new database ID and URL
    """
    console.print(f"[bold cyan]🗃️ Creating new database: {title}[/bold cyan]")
    console.print(f"[bold cyan]Parent ID:[/bold cyan] {parent_id}")

    try:
        # Create a sub-agent with access to the Notion MCP server
        notion_db_create_agent = Agent(
            name="Notion Database Creator",
            model=MODEL,
            instructions="""
            You are a specialized agent for creating Notion databases.
            Your task is to create a new database under a specified parent page with:
            1. The specified title
            2. The specified database schema (properties)
            
            Use the Notion API to create the database properly.
            Return the ID and URL of the newly created database.
            """,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to create the database - using SilenceOutput to hide API calls
        console.print("Creating database...", style="bold cyan")
        
        # Prepare the prompt
        prompt = f"""Create a new Notion database with title: {title} under parent page ID: {parent_id}
        With this database schema: {properties}"""
            
        with SilenceOutput():
            result = await Runner.run(notion_db_create_agent, prompt)

        # Extract the database ID and URL from the result
        response = result.final_output.strip()
        console.print(f"[green]✓ Successfully created database:[/green] {response}")
        
        # Try to parse the response as JSON
        try:
            data = json.loads(response)
            return json.dumps(data)
        except:
            # If not JSON, return a formatted response
            return json.dumps({
                "message": "Database created successfully",
                "response": response
            })

    except Exception as e:
        error_message = f"ERROR creating database: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return json.dumps({"error": error_message})

@function_tool
async def batch_update_notion_records(database_id: str, operations: str, operation_type: str) -> str:
    """
    Perform batch operations on Notion database records.

    Args:
        database_id: The ID of the Notion database to operate on
        operations: JSON string array of record operations to perform
        operation_type: The type of operation - "create", "update", or "archive"

    Returns:
        A summary of operations performed
    """
    console.print(f"[bold cyan]⚙️ Performing batch {operation_type} on database: {database_id}[/bold cyan]")

    try:
        # Parse operations to get count
        ops = json.loads(operations)
        op_count = len(ops)
        console.print(f"[bold cyan]Operations count:[/bold cyan] {op_count}")

        # Create a sub-agent with access to the Notion MCP server
        notion_batch_agent = Agent(
            name="Notion Batch Operator",
            model=MODEL,
            instructions=f"""
            You are a specialized agent for batch operations on Notion databases.
            Your task is to perform {operation_type} operations on records in a database.
            
            For "create" operations, create new records with the specified properties.
            For "update" operations, update existing records with the specified properties.
            For "archive" operations, archive existing records by marking them as archived.
            
            Keep track of successes and failures for each operation.
            Return the results as a NotionBatchOperationResult object.
            """,
            output_type=NotionBatchOperationResult,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to perform batch operations - without hiding output
        console.print(f"Performing {operation_type} operations...", style="bold cyan")
        
        # Prepare the prompt
        prompt = f"""Perform batch {operation_type} operations on database ID: {database_id}
        With these operations: {operations}
        
        Make sure to use the correct Notion API endpoint for {operation_type} operations.
        For create operations, use pages endpoint with the database as parent.
        For update operations, use pages endpoint with the page ID to update.
        For archive operations, set the archived property to true.
        """
        
        result = await Runner.run(notion_batch_agent, prompt)

        # Get the structured result
        try:
            batch_result = result.final_output_as(NotionBatchOperationResult)
            
            # Display batch results
            console.print(Panel.fit(
                f"[bold]Operation Summary:[/bold]\n"
                f"[green]Successes:[/green] {batch_result.success_count}\n"
                f"[red]Failures:[/red] {batch_result.failure_count}\n"
                f"[cyan]Success Rate:[/cyan] {batch_result.success_count/op_count*100:.1f}%",
                title=f"Batch {operation_type.capitalize()} Results",
                border_style="green" if batch_result.failure_count == 0 else "yellow"
            ))
            
            # Return detailed results
            return str(batch_result)
        except Exception as format_error:
            console.print(f"[bold yellow]Warning: Could not format result as NotionBatchOperationResult: {str(format_error)}[/bold yellow]")
            return f"Batch operation completed with result: {result.final_output}"

    except Exception as e:
        error_message = f"ERROR performing batch operation: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return f"ERROR: {error_message}"

@function_tool
async def duplicate_and_consolidate_pages(page_ids: str, new_parent_title: str, database_schema: Optional[str] = None) -> str:
    """
    Duplicate a set of Notion pages to a new parent page and optionally consolidate their databases.

    Args:
        page_ids: JSON string array of page IDs to duplicate
        new_parent_title: Title for the new parent page
        database_schema: Optional JSON string defining the schema for a consolidated database

    Returns:
        JSON string with new page IDs and URLs
    """
    console.print(f"[bold cyan]🔄 Duplicating and consolidating pages under: {new_parent_title}[/bold cyan]")

    try:
        # Parse page IDs to get count
        ids = json.loads(page_ids)
        console.print(f"[bold cyan]Pages to duplicate:[/bold cyan] {len(ids)}")

        # Create a sub-agent with access to the Notion MCP server
        notion_duplicate_agent = Agent(
            name="Notion Page Duplicator",
            model=MODEL,
            instructions=f"""
            You are a specialized agent for duplicating and consolidating Notion pages.
            Your task is to:
            
            1. Create a new parent page with the specified title
            2. For each source page ID, create a duplicate page under the new parent
            3. If a database schema is provided, create a consolidated database with that schema
            4. Link all the duplicate pages to the consolidated database
            
            Return the IDs and URLs of all created pages and databases.
            """,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to duplicate and consolidate - using SilenceOutput to hide API calls
        console.print("Duplicating and consolidating...", style="bold cyan")
        
        # Prepare the prompt
        prompt = f"""Duplicate these Notion pages: {page_ids}
        Create a new parent page titled: {new_parent_title}"""
        
        if database_schema:
            prompt += f"\nCreate a consolidated database with this schema: {database_schema}"
            
        with SilenceOutput():
            result = await Runner.run(notion_duplicate_agent, prompt)

        # Extract results
        response = result.final_output.strip()
        console.print(f"[green]✓ Successfully duplicated and consolidated pages[/green]")
        
        # Try to parse the response as JSON
        try:
            data = json.loads(response)
            return json.dumps(data)
        except:
            # If not JSON, return a formatted response
            return json.dumps({
                "message": "Pages duplicated and consolidated successfully",
                "response": response
            })

    except Exception as e:
        error_message = f"ERROR duplicating pages: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return json.dumps({"error": error_message})

@function_tool
async def get_database_structure(database_id: str) -> str:
    """
    Get detailed information about a Notion database structure including properties and schema.

    Args:
        database_id: The ID of the Notion database

    Returns:
        JSON string with database structure details
    """
    console.print(f"[bold cyan]📋 Analyzing database structure for ID: {database_id}[/bold cyan]")

    try:
        # Create a sub-agent with access to the Notion MCP server
        notion_db_structure_agent = Agent(
            name="Notion Database Structure Analyzer",
            model=MODEL,
            instructions="""
            You are a specialized agent for analyzing Notion database structures.
            Your task is to:
            
            1. Retrieve the database using its ID
            2. Extract the complete schema including all property types, options, and configurations
            3. Determine relationships between this database and other databases
            4. Create a detailed structure report that can be used for programmatically interacting with this database
            
            Return the complete structure in a well-organized JSON format.
            """,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to analyze the database structure - using SilenceOutput to hide API calls
        console.print("Analyzing database structure...", style="bold cyan")
        with SilenceOutput():
            result = await Runner.run(
                notion_db_structure_agent,
                f"Analyze the complete structure of the Notion database with ID: {database_id}. Return a detailed JSON structure that includes all properties, their types, options, and any relationships to other databases."
            )

        # Extract results
        response = result.final_output.strip()
        console.print(f"[green]✓ Database structure analysis complete[/green]")
        
        # Try to parse the response as JSON
        try:
            data = json.loads(response)
            return json.dumps(data, indent=2)
        except:
            # If not JSON, return a formatted response
            return json.dumps({
                "message": "Database structure analysis completed",
                "response": response
            })

    except Exception as e:
        error_message = f"ERROR analyzing database structure: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return json.dumps({"error": error_message})

@function_tool
async def create_project(title: str, summary: str, status: str = "Planning", priority: str = "Medium", start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """
    Create a new project in the TheBaby Projects database.

    Args:
        title: The title for the new project
        summary: A summary description of the project
        status: Project status (e.g., "Backlog", "Planning", "In Progress", "Completed")
        priority: Project priority (e.g., "Low", "Medium", "High")
        start_date: Optional start date in YYYY-MM-DD format
        end_date: Optional end date in YYYY-MM-DD format

    Returns:
        JSON string with the new project ID and URL
    """
    console.print(f"[bold cyan]🏗️ Creating new project: {title}[/bold cyan]")

    try:
        # Create a sub-agent with access to the Notion MCP server
        notion_project_agent = Agent(
            name="Notion Project Creator",
            model=MODEL,
            instructions=f"""
            You are a specialized agent for creating projects in the TheBaby Projects database.
            
            The Projects database ID is: {PROJECTS_DATABASE_ID}
            
            Your task is to:
            1. Create a new project entry with the specified title, summary, status, and other properties
            2. Make sure to use the correct property format for the Projects database
            3. Return the ID and URL of the newly created project
            
            IMPORTANT: Prevent any data deletion or modification of existing projects.
            """,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to create the project - using SilenceOutput to hide API calls
        console.print("Creating project...", style="bold cyan")
        
        # Prepare the dates object if dates are provided
        dates_prop = ""
        if start_date:
            if end_date:
                dates_prop = f', "Dates": {{"start": "{start_date}", "end": "{end_date}"}}'
            else:
                dates_prop = f', "Dates": {{"start": "{start_date}"}}'
        
        # Prepare the prompt with project properties
        prompt = f"""Create a new project in the TheBaby Projects database (ID: {PROJECTS_DATABASE_ID}) with the following properties:
        - Title: "{title}"
        - Summary: "{summary}"
        - Status: "{status}"
        - Priority: "{priority}"{dates_prop}
        
        Return the ID and URL of the newly created project.
        """
        
        with SilenceOutput():
            result = await Runner.run(notion_project_agent, prompt)

        # Extract results
        response = result.final_output.strip()
        console.print(f"[green]✓ Project created successfully[/green]")
        
        # Try to parse the response as JSON
        try:
            data = json.loads(response)
            return json.dumps(data)
        except:
            # If not JSON, return a formatted response
            return json.dumps({
                "message": "Project created successfully",
                "response": response
            })

    except Exception as e:
        error_message = f"ERROR creating project: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return json.dumps({"error": error_message})

@function_tool
async def create_task(title: str, project_id: Optional[str] = None, status: str = "Not started", priority: str = "Medium", due_date: Optional[str] = None, tags: Optional[str] = None) -> str:
    """
    Create a new task in the TheBaby Tasks database.

    Args:
        title: The title for the new task
        project_id: Optional ID of the project this task belongs to
        status: Task status (e.g., "Not started", "In progress", "Done")
        priority: Task priority (e.g., "Low", "Medium", "High")
        due_date: Optional due date in YYYY-MM-DD format
        tags: Optional comma-separated tags (e.g., "API,Research")

    Returns:
        JSON string with the new task ID and URL
    """
    console.print(f"[bold cyan]✅ Creating new task: {title}[/bold cyan]")

    try:
        # Create a sub-agent with access to the Notion MCP server
        notion_task_agent = Agent(
            name="Notion Task Creator",
            model=MODEL,
            instructions=f"""
            You are a specialized agent for creating tasks in the TheBaby Tasks database.
            
            The Tasks database ID is: {TASKS_DATABASE_ID}
            
            Your task is to:
            1. Create a new task entry with the specified title, status, priority, and other properties
            2. If a project ID is provided, link the task to that project
            3. Make sure to use the correct property format for the Tasks database
            4. Return the ID and URL of the newly created task
            
            IMPORTANT: Prevent any data deletion or modification of existing tasks.
            """,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to create the task - using SilenceOutput to hide API calls
        console.print("Creating task...", style="bold cyan")
        
        # Prepare the project relation if provided
        project_prop = ""
        if project_id:
            project_prop = f', "Project": ["{project_id}"]'
        
        # Prepare the due date if provided
        due_date_prop = ""
        if due_date:
            due_date_prop = f', "Due date": "{due_date}"'
        
        # Prepare tags if provided
        tags_prop = ""
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",")]
            tags_json = json.dumps(tag_list)
            tags_prop = f', "Tags": {tags_json}'
        
        # Prepare the prompt with task properties
        prompt = f"""Create a new task in the TheBaby Tasks database (ID: {TASKS_DATABASE_ID}) with the following properties:
        - Title: "{title}"
        - Status: "{status}"
        - Priority: "{priority}"{project_prop}{due_date_prop}{tags_prop}
        
        Return the ID and URL of the newly created task.
        """
        
        with SilenceOutput():
            result = await Runner.run(notion_task_agent, prompt)

        # Extract results
        response = result.final_output.strip()
        console.print(f"[green]✓ Task created successfully[/green]")
        
        # Try to parse the response as JSON
        try:
            data = json.loads(response)
            return json.dumps(data)
        except:
            # If not JSON, return a formatted response
            return json.dumps({
                "message": "Task created successfully",
                "response": response
            })

    except Exception as e:
        error_message = f"ERROR creating task: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return json.dumps({"error": error_message})

@function_tool
async def create_todo(title: str, status: str = "Not started", priority: str = "Medium", due_date: Optional[str] = None, tags: Optional[str] = None) -> str:
    """
    Create a new todo item in the TheBaby ToDo database.

    Args:
        title: The title for the new todo item
        status: Todo status (e.g., "Not started", "In progress", "Done")
        priority: Todo priority (e.g., "Low", "Medium", "High")
        due_date: Optional due date in YYYY-MM-DD format
        tags: Optional comma-separated tags (e.g., "Work,Family")

    Returns:
        JSON string with the new todo ID and URL
    """
    console.print(f"[bold cyan]📝 Creating new todo: {title}[/bold cyan]")

    try:
        # Create a sub-agent with access to the Notion MCP server
        notion_todo_agent = Agent(
            name="Notion Todo Creator",
            model=MODEL,
            instructions=f"""
            You are a specialized agent for creating todo items in the TheBaby ToDo database.
            
            The ToDo database ID is: {TODO_DATABASE_ID}
            
            Your task is to:
            1. Create a new todo entry with the specified title, status, priority, and other properties
            2. Make sure to use the correct property format for the ToDo database
            3. Return the ID and URL of the newly created todo item
            
            IMPORTANT: Prevent any data deletion or modification of existing todo items.
            """,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to create the todo - using SilenceOutput to hide API calls
        console.print("Creating todo item...", style="bold cyan")
        
        # Prepare the due date if provided
        due_date_prop = ""
        if due_date:
            due_date_prop = f', "Due date": "{due_date}"'
        
        # Prepare multi-select tags if provided
        tags_prop = ""
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",")]
            tags_json = json.dumps(tag_list)
            tags_prop = f', "Multi-select": {tags_json}'
        
        # Prepare the prompt with todo properties
        prompt = f"""Create a new todo item in the TheBaby ToDo database (ID: {TODO_DATABASE_ID}) with the following properties:
        - Name: "{title}"
        - Status: "{status}"
        - Priority: "{priority}"{due_date_prop}{tags_prop}
        
        Return the ID and URL of the newly created todo item.
        """
        
        with SilenceOutput():
            result = await Runner.run(notion_todo_agent, prompt)

        # Extract results
        response = result.final_output.strip()
        console.print(f"[green]✓ Todo item created successfully[/green]")
        
        # Try to parse the response as JSON
        try:
            data = json.loads(response)
            return json.dumps(data)
        except:
            # If not JSON, return a formatted response
            return json.dumps({
                "message": "Todo item created successfully",
                "response": response
            })

    except Exception as e:
        error_message = f"ERROR creating todo item: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return json.dumps({"error": error_message})

@function_tool
async def update_task_status(task_id: str, status: str) -> str:
    """
    Update the status of a task in the TheBaby Tasks database.

    Args:
        task_id: The ID of the task to update
        status: The new status for the task (e.g., "Not started", "In progress", "Done")

    Returns:
        JSON string with update result
    """
    console.print(f"[bold cyan]🔄 Updating task status to {status}: {task_id}[/bold cyan]")

    try:
        # Create a sub-agent with access to the Notion MCP server
        notion_update_agent = Agent(
            name="Notion Task Updater",
            model=MODEL,
            instructions=f"""
            You are a specialized agent for updating tasks in the TheBaby Tasks database.
            
            Your task is to:
            1. Update the status of the specified task
            2. Do not modify any other properties unless explicitly instructed
            3. Return the result of the update operation
            
            IMPORTANT: Only update the specified task. Do not delete or modify any other data.
            """,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to update the task - using SilenceOutput to hide API calls
        console.print("Updating task status...", style="bold cyan")
        
        prompt = f"""Update the status of the task with ID {task_id} to "{status}".
        Only update the status property and leave all other properties unchanged.
        """
        
        with SilenceOutput():
            result = await Runner.run(notion_update_agent, prompt)

        # Extract results
        response = result.final_output.strip()
        console.print(f"[green]✓ Task status updated successfully[/green]")
        
        # Try to parse the response as JSON
        try:
            data = json.loads(response)
            return json.dumps(data)
        except:
            # If not JSON, return a formatted response
            return json.dumps({
                "message": "Task status updated successfully",
                "response": response
            })

    except Exception as e:
        error_message = f"ERROR updating task status: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return json.dumps({"error": error_message})

@function_tool
async def link_project_to_tasks(project_id: str, task_ids: str) -> str:
    """
    Link a project to multiple tasks.

    Args:
        project_id: The ID of the project
        task_ids: JSON string array of task IDs to link to the project

    Returns:
        JSON string with linking results
    """
    console.print(f"[bold cyan]🔗 Linking project to tasks: {project_id}[/bold cyan]")

    try:
        # Parse task IDs
        ids = json.loads(task_ids)
        console.print(f"[bold cyan]Tasks to link:[/bold cyan] {len(ids)}")

        # Create a sub-agent with access to the Notion MCP server
        notion_link_agent = Agent(
            name="Notion Relationship Linker",
            model=MODEL,
            instructions=f"""
            You are a specialized agent for managing relationships between Notion database items.
            
            Your task is to:
            1. For each task ID, update the task to add the specified project to its "Project" property
            2. Do not remove any existing project links
            3. Return the results of the linking operations
            
            IMPORTANT: Only update the specified relationship. Do not delete or modify any other data.
            """,
            mcp_servers=[await get_notion_mcp_server()],
        )

        # Run the agent to link project to tasks - using SilenceOutput to hide API calls
        console.print("Linking project to tasks...", style="bold cyan")
        
        prompt = f"""Link the project with ID {project_id} to the following tasks: {task_ids}
        
        For each task:
        1. Retrieve the current task properties
        2. Update the "Project" relation property to include this project ID
        3. Make sure to preserve any existing project relations
        
        Return a summary of the linking operations.
        """
        
        with SilenceOutput():
            result = await Runner.run(notion_link_agent, prompt)

        # Extract results
        response = result.final_output.strip()
        console.print(f"[green]✓ Project linked to tasks successfully[/green]")
        
        # Try to parse the response as JSON
        try:
            data = json.loads(response)
            return json.dumps(data)
        except:
            # If not JSON, return a formatted response
            return json.dumps({
                "message": "Project linked to tasks successfully",
                "response": response
            })

    except Exception as e:
        error_message = f"ERROR linking project to tasks: {str(e)}"
        console.print(f"[bold red]{error_message}[/bold red]")
        return json.dumps({"error": error_message})

@function_tool
async def complete_todo(todo_id: str) -> str:
    """
    Mark a todo item as complete in Notion.

    Args:
        todo_id: The ID of the todo item to mark as complete

    Returns:
        A confirmation message
    """
    console.print(f"[bold cyan]✅ Marking todo {todo_id} as complete...[/bold cyan]")

    # Create a sub-agent with access to the Notion MCP server
    notion_update_agent = Agent(
        name="Notion Todo Completer",
        model=MODEL,
        instructions="""
        You are a specialized agent for updating Notion todo items.
        Your task is to mark a specific todo item as complete.
        
        Use the Notion API tools provided to you to:
        1. Update the block with the given ID
        2. Set the "checked" property of the to_do block to true
        
        Return the result of this operation in the TodoUpdateResult format.
        If there's an error, include details about what went wrong.
        """,
        output_type=TodoUpdateResult,
        mcp_servers=[await get_notion_mcp_server()],
    )

    # Run the agent to mark the todo as complete - using SilenceOutput to hide API calls
    console.print("Updating todo status...", style="bold cyan")
    with SilenceOutput():
        result = await Runner.run(
            notion_update_agent,
            f"Mark the todo item with ID {todo_id} as complete. This is a to_do block type in Notion."
        )

    # Get the structured result
    try:
        # Get the structured result from the agent
        update_result = result.final_output_as(TodoUpdateResult)
        if update_result.success:
            console.print(f"[green]✓ Successfully marked todo as complete[/green]")
            result_str = update_result.message
        else:
            console.print(f"[bold yellow]! Failed to mark todo as complete[/bold yellow]")
            result_str = f"Failed to mark todo as complete: {update_result.message}"
    except Exception as e:
        # If type conversion fails, use the raw output
        console.print(
            f"[bold yellow]Warning: Could not convert result to TodoUpdateResult: {str(e)}[/bold yellow]"
        )
        result_str = f"Todo update completed with response: {result.final_output}"

    return result_str

# Main function to run the agent
async def main():
    global _notion_mcp_server
    
    try:
        # Check command line arguments
        if len(sys.argv) < 2:
            console.print(
                Panel.fit(
                    "[bold white]Notion Database Manager[/bold white]\n\n"
                    "A powerful agent for managing Notion databases and pages.\n\n"
                    "[bold cyan]Available commands:[/bold cyan]\n"
                    "• [bold green]search[/bold green] <query> [--status <status>] - Search for pages\n"
                    "• [bold green]database[/bold green] <database_id> - Get database info\n"
                    "• [bold green]query[/bold green] <database_id> [--filter <filter_json>] [--sort <property>] - Query database\n"
                    "• [bold green]create-page[/bold green] <parent_id> <title> [--properties <json>] [--content <text>] - Create page\n"
                    "• [bold green]create-db[/bold green] <parent_id> <title> <schema_json> - Create database\n"
                    "• [bold green]batch[/bold green] <database_id> <operations_json> [--type create|update|archive] - Batch operations\n"
                    "• [bold green]duplicate[/bold green] <page_ids_json> <new_title> [--schema <json>] - Duplicate & consolidate\n"
                    "• [bold green]todo[/bold green] <page_name> - Manage todos on a page\n"
                    "• [bold green]create-project[/bold green] <title> [summary] [status] [priority] [start_date] [end_date] - Create project\n"
                    "• [bold green]create-task[/bold green] <title> [project_id] [status] [priority] [due_date] [tags] - Create task\n"
                    "• [bold green]create-todo[/bold green] <title> [status] [priority] [due_date] [tags] - Create todo item\n"
                    "• [bold green]update-task-status[/bold green] <task_id> <status> - Update task status\n"
                    "• [bold green]complete-todo[/bold green] <todo_id> - Mark todo item as complete\n"
                    "• [bold magenta]thebaby-todo[/bold magenta] - Create 10 new TheBaby todo items (5 MCP, 5 life related)\n"
                    "• [bold magenta]add-project[/bold magenta] <title> - Create project using properties in project_props.json\n"
                    "• [bold magenta]add-todo[/bold magenta] <title> - Create todo using properties in todo_props.json\n\n"
                    "[bold yellow]Examples:[/bold yellow]\n"
                    "• uv run starter_notion_agent.py search \"TheBaby\" --status \"In Review\"\n"
                    "• uv run starter_notion_agent.py database 1e0fdb28-a67c-4711-b5e9-cc99f7d75096\n"
                    "• uv run starter_notion_agent.py query 1e0fdb28-a67c-4711-b5e9-cc99f7d75096\n"
                    "• uv run starter_notion_agent.py create-task \"New Development Task\" \"project_id_here\" \"In Progress\"\n"
                    "• uv run starter_notion_agent.py thebaby-todo",
                    title="Notion Database Manager",
                    border_style="cyan",
                )
            )
            return 0

        # Parse command and arguments
        command = sys.argv[1].lower()

        # Welcome message
        console.print(
            Panel.fit(
                f"[bold blue]🤖 Notion Database Manager[/bold blue]\n\n"
                f"[green]Executing command: [bold]{command}[/bold][/green]",
                title="OpenAI Agents + Notion",
                border_style="cyan",
            )
        )

        # Define available commands and their implementations
        if command == "create-project":
            if len(sys.argv) < 3:
                console.print("[bold red]ERROR: Please provide at least a project title.[/bold red]")
                console.print("Usage: uv run starter_notion_agent.py create-project \"Project Title\" \"Project Summary\" [status] [priority] [start_date] [end_date]")
                return 1
                
            # Get parameters from command line
            title = sys.argv[2]
            summary = sys.argv[3] if len(sys.argv) > 3 else "Project summary"
            status = sys.argv[4] if len(sys.argv) > 4 else "Planning"
            priority = sys.argv[5] if len(sys.argv) > 5 else "Medium"
            start_date = sys.argv[6] if len(sys.argv) > 6 else None
            end_date = sys.argv[7] if len(sys.argv) > 7 else None
            
            # Create project
            console.print(f"[bold cyan]🏗️ Creating new project: {title}[/bold cyan]")
            
            # Prepare properties with correct Notion API format
            properties = {
                "Title": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                },
                "Summary": {
                    "rich_text": [
                        {
                            "text": {
                                "content": summary
                            }
                        }
                    ]
                },
                "Status": {
                    "select": {
                        "name": status
                    }
                },
                "Priority": {
                    "select": {
                        "name": priority
                    }
                }
            }
            
            # Add dates if provided
            if start_date:
                if end_date:
                    properties["Dates"] = {
                        "date": {
                            "start": start_date,
                            "end": end_date
                        }
                    }
                else:
                    properties["Dates"] = {
                        "date": {
                            "start": start_date
                        }
                    }
            
            # Create direct agent for project creation
            direct_notion_agent = Agent(
                name="Project Creator Agent",
                model=MODEL,
                instructions=f"""
                You are an agent that directly creates projects in the Notion Projects database.
                
                Create a new project with the following properties:
                {json.dumps(properties, indent=2)}
                
                Use the mcp__notionApi__API-post-page endpoint with:
                - parent: {{database_id: "{PROJECTS_DATABASE_ID}"}}
                - properties: the project properties
                
                Return the ID and URL of the newly created project.
                """,
                mcp_servers=[await get_notion_mcp_server()],
            )
            
            # Run the agent
            console.print("Creating project...", style="bold cyan")
            result = await Runner.run(direct_notion_agent, f"Create a new project titled '{title}' in the Projects database with ID: {PROJECTS_DATABASE_ID}")
            
            # Display results
            console.print("[green]✓ Project created successfully[/green]")
            console.print(Panel.fit(
                result.final_output,
                title="Project Creation Results",
                border_style="green"
            ))
                
        elif command == "create-task":
            if len(sys.argv) < 3:
                console.print("[bold red]ERROR: Please provide at least a task title.[/bold red]")
                console.print("Usage: uv run starter_notion_agent.py create-task \"Task Title\" [project_id] [status] [priority] [due_date] [tags]")
                return 1
                
            # Get parameters from command line
            title = sys.argv[2]
            project_id = sys.argv[3] if len(sys.argv) > 3 else None
            status = sys.argv[4] if len(sys.argv) > 4 else "Not started"
            priority = sys.argv[5] if len(sys.argv) > 5 else "Medium"
            due_date = sys.argv[6] if len(sys.argv) > 6 else None
            tags = sys.argv[7] if len(sys.argv) > 7 else None
            
            # Create task
            console.print(f"[bold cyan]✅ Creating new task: {title}[/bold cyan]")
            
            # Prepare properties with correct Notion API format
            properties = {
                "Title": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                },
                "Status": {
                    "select": {
                        "name": status
                    }
                },
                "Priority": {
                    "select": {
                        "name": priority
                    }
                }
            }
            
            # Add project relation if provided
            if project_id:
                properties["Project"] = {
                    "relation": [
                        {
                            "id": project_id
                        }
                    ]
                }
            
            # Add due date if provided
            if due_date:
                properties["Due date"] = {
                    "date": {
                        "start": due_date
                    }
                }
                
            # Add tags if provided
            if tags:
                tag_list = []
                for tag in tags.split(","):
                    tag_list.append({"name": tag.strip()})
                
                if tag_list:
                    properties["Tags"] = {
                        "multi_select": tag_list
                    }
            
            # Create direct agent for task creation
            direct_notion_agent = Agent(
                name="Task Creator Agent",
                model=MODEL,
                instructions=f"""
                You are an agent that directly creates tasks in the Notion Tasks database.
                
                Create a new task with the following properties:
                {json.dumps(properties, indent=2)}
                
                Use the mcp__notionApi__API-post-page endpoint with:
                - parent: {{database_id: "{TASKS_DATABASE_ID}"}}
                - properties: the task properties
                
                Return the ID and URL of the newly created task.
                """,
                mcp_servers=[await get_notion_mcp_server()],
            )
            
            # Run the agent
            console.print("Creating task...", style="bold cyan")
            result = await Runner.run(direct_notion_agent, f"Create a new task titled '{title}' in the Tasks database with ID: {TASKS_DATABASE_ID}")
            
            # Display results
            console.print("[green]✓ Task created successfully[/green]")
            console.print(Panel.fit(
                result.final_output,
                title="Task Creation Results",
                border_style="green"
            ))
                
        elif command == "create-todo":
            if len(sys.argv) < 3:
                console.print("[bold red]ERROR: Please provide at least a todo title.[/bold red]")
                console.print("Usage: uv run starter_notion_agent.py create-todo \"Todo Title\" [status] [priority] [due_date] [tags]")
                return 1
                
            # Get parameters from command line
            title = sys.argv[2]
            status = sys.argv[3] if len(sys.argv) > 3 else "Not started"
            priority = sys.argv[4] if len(sys.argv) > 4 else "Medium"
            due_date = sys.argv[5] if len(sys.argv) > 5 else None
            tags = sys.argv[6] if len(sys.argv) > 6 else None
            
            # Create todo
            console.print(f"[bold cyan]📝 Creating new todo: {title}[/bold cyan]")
            
            # Prepare properties with correct Notion API format
            properties = {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                },
                "Status": {
                    "select": {
                        "name": status
                    }
                },
                "Priority": {
                    "select": {
                        "name": priority
                    }
                }
            }
            
            # Add due date if provided
            if due_date:
                properties["Due date"] = {
                    "date": {
                        "start": due_date
                    }
                }
                
            # Add tags if provided
            if tags:
                tag_list = []
                for tag in tags.split(","):
                    tag_list.append({"name": tag.strip()})
                
                if tag_list:
                    properties["Multi-select"] = {
                        "multi_select": tag_list
                    }
            
            # Create direct agent for todo creation
            direct_notion_agent = Agent(
                name="Todo Creator Agent",
                model=MODEL,
                instructions=f"""
                You are an agent that directly creates todo items in the Notion ToDo database.
                
                Create a new todo item with the following properties:
                {json.dumps(properties, indent=2)}
                
                Use the mcp__notionApi__API-post-page endpoint with:
                - parent: {{database_id: "{TODO_DATABASE_ID}"}}
                - properties: the todo properties
                
                Return the ID and URL of the newly created todo item.
                """,
                mcp_servers=[await get_notion_mcp_server()],
            )
            
            # Run the agent
            console.print("Creating todo item...", style="bold cyan")
            result = await Runner.run(direct_notion_agent, f"Create a new todo titled '{title}' in the ToDo database with ID: {TODO_DATABASE_ID}")
            
            # Display results
            console.print("[green]✓ Todo created successfully[/green]")
            console.print(Panel.fit(
                result.final_output,
                title="Todo Creation Results",
                border_style="green"
            ))
                
        elif command == "update-task-status":
            if len(sys.argv) < 4:
                console.print("[bold red]ERROR: Please provide a task ID and status.[/bold red]")
                console.print("Usage: uv run starter_notion_agent.py update-task-status \"task_id\" \"status\"")
                return 1
                
            # Get parameters from command line
            task_id = sys.argv[2]
            status = sys.argv[3]
            
            # Update task status
            console.print(f"[bold cyan]🔄 Updating task status to {status}: {task_id}[/bold cyan]")
            
            # Create direct agent for task update
            direct_notion_agent = Agent(
                name="Task Status Updater",
                model=MODEL,
                instructions=f"""
                You are an agent that directly updates task status in the Notion Tasks database.
                
                Update the task with ID: {task_id}
                Set the Status to: {status}
                
                Use the mcp__notionApi__API-patch-page endpoint with:
                - page_id: the task ID
                - properties: {{ "Status": {{ "select": {{ "name": "{status}" }} }} }}
                
                Return confirmation of the update with the ID and new status.
                """,
                mcp_servers=[await get_notion_mcp_server()],
            )
            
            # Run the agent
            console.print("Updating task status...", style="bold cyan")
            result = await Runner.run(direct_notion_agent, f"Update the status of task {task_id} to '{status}'")
            
            # Display the result
            console.print("[green]✓ Task status updated successfully[/green]")
            console.print(Panel.fit(
                result.final_output,
                title="Task Status Update Results",
                border_style="green"
            ))
                
        elif command == "complete-todo":
            if len(sys.argv) < 3:
                console.print("[bold red]ERROR: Please provide a todo ID.[/bold red]")
                console.print("Usage: uv run starter_notion_agent.py complete-todo \"todo_id\"")
                return 1
                
            # Get parameters from command line
            todo_id = sys.argv[2]
            
            # Complete todo
            console.print(f"[bold cyan]✅ Marking todo as complete: {todo_id}[/bold cyan]")
            
            # Create direct agent for todo completion
            direct_notion_agent = Agent(
                name="Todo Completer",
                model=MODEL,
                instructions=f"""
                You are an agent that directly marks todo items as complete in Notion.
                
                Mark the todo item with ID: {todo_id} as complete
                
                For a to_do block type, use the mcp__notionApi__API-update-a-block endpoint with:
                - block_id: the todo ID
                - type: {{ "to_do": {{ "checked": true }} }}
                
                For a database item, use the mcp__notionApi__API-patch-page endpoint with:
                - page_id: the todo ID
                - properties: {{ "Status": {{ "select": {{ "name": "Done" }} }} }}
                
                Return confirmation of the update with the ID and new status.
                """,
                mcp_servers=[await get_notion_mcp_server()],
            )
            
            # Run the agent
            console.print("Marking todo as complete...", style="bold cyan")
            result = await Runner.run(direct_notion_agent, f"Mark the todo item with ID {todo_id} as complete. Try both approaches - to_do block type and database item.")
            
            # Display the result
            console.print("[green]✓ Todo marked as complete[/green]")
            console.print(Panel.fit(
                result.final_output,
                title="Todo Completion Results",
                border_style="green"
            ))
                
        elif command == "thebaby-todo":
            # Special command for TheBaby ToDo database management
            console.print("[bold cyan]🔧 Managing TheBaby ToDo database...[/bold cyan]")
            
            todo_db_id = "1e9e13474afd8115ac29c6fcbd9a16e2"  # Hardcoded TheBaby ToDo database ID
            
            # Create specialized agent for TheBaby ToDo management
            thebaby_todo_agent = Agent(
                name="TheBaby ToDo Manager",
                model=MODEL,
                instructions=f"""
                # TheBaby ToDo Manager
                
                ## Objective
                You are a specialized agent that manages the TheBaby ToDo database.
                
                ## Task
                1. Archive all existing records in the TheBaby ToDo database
                2. Create 10 new todo entries related to TheBaby MCP server testing
                3. Ensure these entries have appropriate titles, priorities, and due dates
                4. Link these entries to corresponding TheBaby projects if applicable
                
                ## Process
                1. First, use query_notion_database to get all current records in the ToDo database
                2. Use batch_update_notion_records with "archive" operation type to archive all existing records
                3. Create 10 new todo entries with varied priorities and realistic due dates
                4. Ensure a mix of project-related and life-related tasks
                5. Use batch_update_notion_records with "create" operation type to add these new records
                
                ## Guidelines
                - Create realistic, detailed todo items
                - Include task titles, priorities (High/Medium/Low), and due dates
                - Add appropriate tags and statuses
                - Provide a clear summary of all changes made
                """,
                tools=[
                    query_notion_database,
                    batch_update_notion_records,
                    get_notion_database
                ],
            )
            
            # Run the TheBaby ToDo management agent with our patched silent Runner
            console.print("Managing TheBaby ToDo database...", style="bold cyan")
            result = await Runner.run(
                thebaby_todo_agent,
                f"""Manage the TheBaby ToDo database with ID: {todo_db_id}
                
                1. First, archive all existing records in the database
                2. Then create 10 new todo entries with the following requirements:
                   - 5 entries should be related to TheBaby MCP server testing projects
                   - 5 entries should be related to TheBaby life tasks
                   - Each entry should have an appropriate title, priority, status, and due date
                   - MCP-related tasks should include things like testing, data validation, API development
                   - Life-related tasks should include real-world activities like meetings, emails, etc.
                   - Include appropriate tags for categorization
                
                Make sure all operations are performed correctly and provide a summary of changes made.
                """
            )
            # Display the result
            console.print("[green]✓ Database management complete[/green]")
            console.print(Panel.fit(
                result.final_output,
                title="TheBaby ToDo Management Results",
                border_style="green"
            ))
    
        elif command == "search":
            if len(sys.argv) < 3:
                console.print("[bold red]ERROR: Please provide a search query.[/bold red]")
                return 1

            query = sys.argv[2]
            status = None

            # Check for status filter
            if len(sys.argv) > 4 and sys.argv[3] == "--status":
                status = sys.argv[4]

            # Create search agent
            notion_search_agent = Agent(
                name="Notion Page Search Agent",
                model=MODEL,
                instructions=f"""
                # Notion Page Search Agent
                
                ## Objective
                You are a helpful agent that searches for Notion pages by name and status.
                
                ## Task
                Search for pages matching the query: "{query}"
                {f'Filter for pages with status: "{status}"' if status else ''}
                
                ## Process
                1. Use the search_notion_pages tool to find pages matching the criteria
                2. Present the results in a clear, organized way
                3. Include page IDs, titles, and URLs in your response
                
                ## Guidelines
                - Be thorough in your search
                - Format the results for easy readability
                - If no results are found, suggest alternative search terms
                """,
                tools=[search_notion_pages],
            )

            # Run the search agent - without using Progress
            console.print("Searching for pages...", style="bold cyan")
            
            # Comment out Runner.run to prevent logging to stdout
            # with SilenceOutput():
            #    result = await Runner.run(
            #        notion_search_agent,
            #        f"Search for Notion pages matching '{query}'" + 
            #        (f" with status '{status}'" if status else "")
            #    )
            
            # Run with patched silent Runner
            result = await Runner.run(
                notion_search_agent,
                f"Search for Notion pages matching '{query}'" + 
                (f" with status '{status}'" if status else "")
            )
            console.print("[green]✓ Search complete[/green]")
            
            # Clean up any API call output that might have leaked through
            # by setting up stdout filter to suppress API call details
            class CallFilter:
                def __init__(self, original_stdout):
                    self.original_stdout = original_stdout
                    self.buffer = ""
                
                def write(self, text):
                    # Skip anything that looks like an API call
                    if "calling tool" in text or "API-" in text:
                        return
                    # Pass through other text
                    self.original_stdout.write(text)
                
                def flush(self):
                    self.original_stdout.flush()
            
            # Apply the filter
            sys.stdout = CallFilter(sys.stdout)
            
            # Extract and display results
            try:
                # Try to parse the results as JSON
                search_data = json.loads(result.final_output)
                
                # Create a table to display the results
                if isinstance(search_data, list):
                    table = Table(title=f"Found {len(search_data)} Matching Pages")
                    table.add_column("Title", style="cyan")
                    table.add_column("ID", style="green")
                    table.add_column("URL", style="blue")
                    
                    for page in search_data:
                        if isinstance(page, dict):
                            table.add_row(
                                page.get("title", "No title"),
                                page.get("id", "No ID"),
                                page.get("url", "N/A")
                            )
                    
                    console.print(table)
                else:
                    # Display the raw output if not a list
                    console.print(Panel.fit(
                        result.final_output,
                        title="Search Results",
                        border_style="cyan"
                    ))
            except (json.JSONDecodeError, AttributeError):
                # If not valid JSON, display the raw output
                console.print(Panel.fit(
                    result.final_output,
                    title="Search Results",
                    border_style="cyan"
                ))
            finally:
                # Restore normal stdout
                sys.stdout = sys.__stdout__

        elif command == "database":
            if len(sys.argv) < 3:
                console.print("[bold red]ERROR: Please provide a database ID.[/bold red]")
                return 1

            database_id = sys.argv[2]

            # Create database info agent
            notion_db_agent = Agent(
                name="Notion Database Info Agent",
                model=MODEL,
                instructions=f"""
                # Notion Database Info Agent
                
                ## Objective
                You are a helpful agent that retrieves information about Notion databases.
                
                ## Task
                Get detailed information for database ID: "{database_id}"
                
                ## Process
                1. Use the get_notion_database tool to fetch database information
                2. Present the database schema and properties in a clear, organized way
                3. Provide insights about the database structure
                
                ## Guidelines
                - Clearly explain each property in the database schema
                - Highlight important aspects of the database design
                - Format the results for easy readability
                """,
                tools=[get_notion_database],
            )

            # Run the database info agent - without using Progress
            console.print("Retrieving database info...", style="bold cyan")
            # Use SilenceOutput to suppress logging
            with SilenceOutput():
                result = await Runner.run(
                    notion_db_agent,
                    f"Get detailed information about the Notion database with ID: {database_id}"
                )
            console.print("[green]✓ Database info retrieved[/green]")

        elif command == "query":
            if len(sys.argv) < 3:
                console.print("[bold red]ERROR: Please provide a database ID.[/bold red]")
                return 1

            database_id = sys.argv[2]
            filter_criteria = None
            sort_by = None

            # Check for filter and sort parameters
            i = 3
            while i < len(sys.argv):
                if sys.argv[i] == "--filter" and i + 1 < len(sys.argv):
                    filter_criteria = sys.argv[i + 1]
                    i += 2
                elif sys.argv[i] == "--sort" and i + 1 < len(sys.argv):
                    sort_by = sys.argv[i + 1]
                    i += 2
                else:
                    i += 1

            # Create direct agent for database querying
            direct_notion_agent = Agent(
                name="Direct Notion Database Query Agent",
                model=MODEL,
                instructions=f"""
                # Notion Database Query Agent
                
                ## Objective
                You are an agent that directly queries Notion databases using the API.
                
                ## Task
                Query database ID: "{database_id}"
                {f'With filter: {filter_criteria}' if filter_criteria else ''}
                {f'Sort by: {sort_by}' if sort_by else ''}
                
                ## Process
                1. Use the mcp__notionApi__API-post-database-query endpoint directly
                2. Format the request with:
                   - database_id: "{database_id}"
                   {f'- filter: {filter_criteria}' if filter_criteria else ''}
                   {f'- sorts: [{{"{sort_by.split(":")[0]}": "{sort_by.split(":")[1]}"}}]' if sort_by and ":" in sort_by else ''}
                3. Return the results as a formatted list of database records
                
                ## Guidelines
                - Format the results for easy readability
                - Include all record IDs and properties
                - If no results match the filter, explain why
                """,
                mcp_servers=[await get_notion_mcp_server()],
            )

            # Run the query agent directly
            console.print("Querying database...", style="bold cyan")
            
            # Prepare the prompt
            query_prompt = f"""
            Query the Notion database with ID: {database_id}
            
            Use the mcp__notionApi__API-post-database-query endpoint with these parameters:
            - database_id: "{database_id}"
            """
            
            if filter_criteria:
                query_prompt += f"""
                - filter: {filter_criteria}
                """
                
            if sort_by:
                direction = "descending"
                property_name = sort_by
                
                if ":" in sort_by:
                    parts = sort_by.split(":")
                    property_name = parts[0]
                    if len(parts) > 1:
                        if parts[1].lower() in ["asc", "ascending"]:
                            direction = "ascending"
                        elif parts[1].lower() in ["desc", "descending"]:
                            direction = "descending"
                
                query_prompt += f"""
                - sorts: [{{
                    "property": "{property_name}",
                    "direction": "{direction}"
                }}]
                """
            
            query_prompt += """
            Process the results and return them in a clear, organized format.
            Include all relevant fields for each record.
            """
            
            # Execute the query with all output visible
            result = await Runner.run(direct_notion_agent, query_prompt)
            
            console.print("[green]✓ Database query complete[/green]")
            console.print(Panel.fit(
                result.final_output,
                title="Query Results",
                border_style="green"
            ))

        elif command == "create-page":
            if len(sys.argv) < 4:
                console.print("[bold red]ERROR: Please provide a parent ID and title.[/bold red]")
                return 1

            parent_id = sys.argv[2]
            title = sys.argv[3]
            properties = None
            content = None

            # Check for properties and content parameters
            i = 4
            while i < len(sys.argv):
                if sys.argv[i] == "--properties" and i + 1 < len(sys.argv):
                    properties = sys.argv[i + 1]
                    i += 2
                elif sys.argv[i] == "--content" and i + 1 < len(sys.argv):
                    content = sys.argv[i + 1]
                    i += 2
                else:
                    i += 1

            # Print debug information
            console.print(f"[bold yellow]DEBUG: Parent ID:[/bold yellow] {parent_id}")
            console.print(f"[bold yellow]DEBUG: Title:[/bold yellow] {title}")
            console.print(f"[bold yellow]DEBUG: Properties:[/bold yellow] {properties}")
            
            # Create direct notion API call to create a page
            console.print("[bold cyan]📝 Creating page directly with Notion API...[/bold cyan]")
            
            # Determine the correct name field for the title based on parent type and database
            # Different databases can have different names for the title property
            if parent_id == PROJECTS_DATABASE_ID:
                title_field = "Title"  # Projects database uses "Title"
            elif parent_id == TASKS_DATABASE_ID:
                title_field = "Title"  # Tasks database uses "Title"
            elif parent_id == TODO_DATABASE_ID:
                title_field = "Name"   # Todo database uses "Name"
            else:
                title_field = "Title"  # Default to "Title" for other databases
            
            # Prepare the body parameters
            parent = {
                "database_id": parent_id
            }
            
            # Create a properties object starting with the title
            page_properties = {
                title_field: {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                }
            }
            
            # Merge with any additional properties if provided
            if properties:
                try:
                    # Parse the properties JSON
                    additional_props = json.loads(properties)
                    
                    # Add each property to the properties object, with special handling for database-specific fields
                    for key, value in additional_props.items():
                        # Map property names correctly for each database
                        mapped_key = key
                        
                        # Projects database property mappings
                        if parent_id == PROJECTS_DATABASE_ID:
                            # Status in projects database is called "Status" (no mapping needed)
                            pass
                            
                        # Tasks database property mappings
                        elif parent_id == TASKS_DATABASE_ID:
                            # Status in tasks database is called "Status" (no mapping needed)
                            pass
                            
                        # ToDo database property mappings
                        elif parent_id == TODO_DATABASE_ID:
                            # Todo database might have different field names
                            pass
                        
                        # Add the property with mapped key
                        page_properties[mapped_key] = value
                        
                    console.print(f"[bold green]Added {len(additional_props)} properties to the page[/bold green]")
                except json.JSONDecodeError:
                    console.print(f"[bold red]ERROR: Invalid JSON in properties. Using title only.[/bold red]")
            
            # Create a simple direct agent with access to Notion API
            simple_notion_agent = Agent(
                name="Notion Page Creator",
                model=MODEL,
                instructions=f"""
                # Notion Page Creator Agent
                
                ## Objective
                You are an agent that creates pages directly in Notion databases using the API.
                
                ## Task Details
                - Database ID: {parent_id}
                - Database Type: {"Projects" if parent_id == PROJECTS_DATABASE_ID else "Tasks" if parent_id == TASKS_DATABASE_ID else "ToDo" if parent_id == TODO_DATABASE_ID else "Unknown"}
                - Title Field Name: {title_field}
                
                ## Database Structure Information
                - Projects Database: Title field is "Title", status field is "Status" (not "status")
                - Tasks Database: Title field is "Title", status field is "Status"
                - ToDo Database: Title field is "Name", status field is "Status"
                
                ## Process
                1. Use the mcp__notionApi__API-post-page endpoint exactly as instructed
                2. Make sure the properties match the database structure
                3. Pay attention to field names - they are case-sensitive and specific to each database
                4. Return the ID and URL of the created page
                
                ## Common Errors to Avoid
                - Using incorrect property names (e.g., using "Name" when it should be "Title")
                - Using incorrect field types (e.g., using "text" instead of "title" for the title field)
                - Using incorrect values for select fields (e.g., using a value that doesn't exist in the options)
                """,
                mcp_servers=[await get_notion_mcp_server()],
            )
            
            # Run the agent to create the page
            console.print("Creating page with direct API call...", style="bold cyan")
            console.print(f"[bold cyan]Properties:[/bold cyan] {json.dumps(page_properties, indent=2)}")
            
            # First, let's inspect the database to understand its structure (if we haven't seen it before)
            console.print("[bold cyan]📊 Inspecting database structure...[/bold cyan]")
            
            # Direct API call prompt with database inspection
            api_prompt = f"""
            To create a new page in the Notion database correctly:
            
            1. First, check the structure of the database with ID: {parent_id}
               Use the mcp__notionApi__API-retrieve-a-database endpoint to learn its property structure
            
            2. Based on the database structure, create a new page using the mcp__notionApi__API-post-page endpoint with:
               - parent: {json.dumps(parent)}
               - properties: {json.dumps(page_properties)}
            
            Make any necessary adjustments to the properties based on the actual database structure.
            Pay particular attention to the title field and status field names.
            
            Execute this API call and return the page ID and URL.
            """
            
            # Execute the API call
            result = await Runner.run(simple_notion_agent, api_prompt)
            
            console.print("[green]✓ Page created[/green]")
            console.print(Panel.fit(
                result.final_output,
                title="Page Creation Results",
                border_style="green"
            ))

        elif command == "create-db":
            if len(sys.argv) < 5:
                console.print("[bold red]ERROR: Please provide a parent ID, title, and schema.[/bold red]")
                return 1

            parent_id = sys.argv[2]
            title = sys.argv[3]
            properties = sys.argv[4]

            # Create database creation agent
            notion_db_create_agent = Agent(
                name="Notion Database Creation Agent",
                model=MODEL,
                instructions=f"""
                # Notion Database Creation Agent
                
                ## Objective
                You are a helpful agent that creates Notion databases.
                
                ## Task
                Create a new database with title: "{title}"
                Under parent ID: "{parent_id}"
                With schema: {properties}
                
                ## Process
                1. Use the create_notion_database tool to create the new database
                2. Return the new database ID and URL
                
                ## Guidelines
                - Confirm the database was created successfully
                - Provide the direct link to access the new database
                """,
                tools=[create_notion_database],
            )

            # Run the create database agent - without using Progress
            console.print("Creating database...", style="bold cyan")
            
            # Prepare the prompt
            prompt = f"Create a new Notion database titled '{title}' under parent ID: {parent_id} with this schema: {properties}"
            
            # Use SilenceOutput to suppress logging
            with SilenceOutput():
                result = await Runner.run(notion_db_create_agent, prompt)
            console.print("[green]✓ Database created[/green]")

        elif command == "batch":
            if len(sys.argv) < 4:
                console.print("[bold red]ERROR: Please provide a database ID and operations JSON.[/bold red]")
                return 1

            database_id = sys.argv[2]
            operations = sys.argv[3]
            operation_type = "create"  # Default

            # Check for operation type parameter
            if len(sys.argv) > 4 and sys.argv[4] == "--type" and len(sys.argv) > 5:
                operation_type = sys.argv[5]

            # Debug info - print what we're receiving
            console.print(f"[bold yellow]DEBUG: Database ID:[/bold yellow] {database_id}")
            console.print(f"[bold yellow]DEBUG: Operation Type:[/bold yellow] {operation_type}")
            console.print(f"[bold yellow]DEBUG: Operations JSON:[/bold yellow] {operations}")
            
            try:
                # Parse the JSON to validate it
                ops_data = json.loads(operations)
                console.print(f"[bold green]Valid JSON with {len(ops_data)} operations[/bold green]")
                
                # Format operations correctly for Notion API if needed
                formatted_ops = []
                for op in ops_data:
                    # Ensure each operation has properties field
                    if "properties" not in op and operation_type == "create":
                        # If direct properties are provided at root level, move them to properties field
                        properties = {}
                        for key, value in op.items():
                            if key != "id":  # Don't move ID to properties
                                properties[key] = value
                        op = {"properties": properties}
                    formatted_ops.append(op)
                
                # Use the formatted operations
                operations_json = json.dumps(formatted_ops)
                console.print(f"[bold cyan]Using formatted operations:[/bold cyan] {operations_json}")
            except json.JSONDecodeError as e:
                console.print(f"[bold red]ERROR: Invalid JSON format: {str(e)}[/bold red]")
                return 1

            # Create batch operation agent
            notion_batch_agent = Agent(
                name="Notion Batch Operation Agent",
                model=MODEL,
                instructions=f"""
                # Notion Batch Operation Agent
                
                ## Objective
                You are a helpful agent that performs batch operations on Notion databases.
                
                ## Task
                Perform {operation_type} operations on database ID: "{database_id}"
                With these operations: {operations_json}
                
                ## Process
                1. Use the batch_update_notion_records tool to perform the operations
                2. Report on the success and failure of each operation
                
                ## Guidelines
                - Clearly summarize the results of the batch operation
                - Explain any failures that occurred
                - Provide statistics on the success rate
                """,
                tools=[batch_update_notion_records],
                mcp_servers=[await get_notion_mcp_server()],  # Explicitly connect to MCP server
            )

            # Run the batch operation agent directly using the model
            console.print(f"Performing batch {operation_type}...", style="bold cyan")
            
            # Create a simpler agent for direct Notion API access
            direct_notion_agent = Agent(
                name="Direct Notion API Agent",
                model=MODEL,
                instructions=f"""
                You are an agent that directly interacts with the Notion API to perform batch operations.
                
                Your task is to perform a batch {operation_type} operation on the database with ID: {database_id}
                
                Follow these steps:
                1. For create operations, use the mcp__notionApi__API-post-page endpoint for each record
                2. For update operations, use the mcp__notionApi__API-patch-page endpoint for each record
                3. For archive operations, use the mcp__notionApi__API-patch-page endpoint with archived=true
                
                Use the correct format for each API endpoint.
                """,
                mcp_servers=[await get_notion_mcp_server()],
            )
            
            # Run the agent with all details visible
            try:
                # For create operations, we'll handle each item individually
                if operation_type == "create":
                    successes = 0
                    failures = 0
                    messages = []
                    
                    # Get the operations
                    ops = json.loads(operations_json)
                    
                    for i, op in enumerate(ops):
                        try:
                            console.print(f"Creating record {i+1}/{len(ops)}...")
                            
                            # Extract title for display
                            title = "Unknown"
                            if "properties" in op and "Title" in op["properties"]:
                                title_obj = op["properties"]["Title"]
                                if "title" in title_obj and len(title_obj["title"]) > 0:
                                    if "text" in title_obj["title"][0] and "content" in title_obj["title"][0]["text"]:
                                        title = title_obj["title"][0]["text"]["content"]
                            
                            # Format the prompt for creating a single page
                            prompt = f"""
                            Create a new page in the Notion database with ID: {database_id}
                            
                            Use this data for the page:
                            {json.dumps(op, indent=2)}
                            
                            Remember to use the correct API endpoint and format. The database ID should be used as the parent.
                            """
                            
                            # Create the page
                            sub_result = await Runner.run(direct_notion_agent, prompt)
                            
                            # Check if success (assume success if it returns something)
                            if sub_result and sub_result.final_output:
                                successes += 1
                                messages.append(f"✓ Created record: {title}")
                                console.print(f"[green]✓ Created record: {title}[/green]")
                            else:
                                failures += 1
                                messages.append(f"✗ Failed to create record: {title}")
                                console.print(f"[red]✗ Failed to create record: {title}[/red]")
                                
                        except Exception as item_error:
                            failures += 1
                            messages.append(f"✗ Error creating record: {str(item_error)}")
                            console.print(f"[red]✗ Error creating record: {str(item_error)}[/red]")
                    
                    # Build result summary
                    details = ""
                    for msg in messages:
                        details += f"- {msg}\n"
                        
                    result_summary = f"""
                    Operation Summary:
                    
                    Successes: {successes}
                    Failures: {failures}
                    Success Rate: {(successes/len(ops)*100 if len(ops) > 0 else 0):.1f}%
                    
                    Details:
                    {details}
                    """
                    
                    console.print("[green]✓ Batch operations complete[/green]")
                    console.print(Panel.fit(
                        result_summary,
                        title=f"Batch {operation_type.capitalize()} Results",
                        border_style="green" if failures == 0 else "yellow"
                    ))
                    
                else:
                    # For other operation types, try the batch approach
                    prompt = f"""
                    Perform a batch {operation_type} operation on the Notion database with ID: {database_id}
                    
                    Here are the operations to perform:
                    {operations_json}
                    
                    Process each operation individually using the appropriate Notion API endpoint.
                    Return a summary of the results with success and failure counts.
                    """
                    
                    # Run the agent
                    result = await Runner.run(direct_notion_agent, prompt)
                    
                    # Display results
                    console.print("[green]✓ Batch operations complete[/green]")
                    console.print(Panel.fit(
                        result.final_output,
                        title=f"Batch {operation_type.capitalize()} Results",
                        border_style="green"
                    ))
                    
            except Exception as e:
                console.print(f"[bold red]ERROR in batch operation: {str(e)}[/bold red]")
                return 1

        elif command == "duplicate":
            if len(sys.argv) < 4:
                console.print("[bold red]ERROR: Please provide page IDs JSON and a new title.[/bold red]")
                return 1

            page_ids = sys.argv[2]
            new_title = sys.argv[3]
            schema = None

            # Check for schema parameter
            if len(sys.argv) > 5 and sys.argv[4] == "--schema":
                schema = sys.argv[5]

            # Create duplication agent
            notion_duplicate_agent = Agent(
                name="Notion Page Duplication Agent",
                model=MODEL,
                instructions=f"""
                # Notion Page Duplication Agent
                
                ## Objective
                You are a helpful agent that duplicates and consolidates Notion pages.
                
                ## Task
                Duplicate pages with IDs: {page_ids}
                Create a new parent page titled: "{new_title}"
                {f'With consolidated database schema: {schema}' if schema else ''}
                
                ## Process
                1. Use the duplicate_and_consolidate_pages tool to perform the duplication
                2. Return the IDs and URLs of the new pages and databases
                
                ## Guidelines
                - Confirm the pages were duplicated successfully
                - Provide direct links to access the new pages
                - If a consolidated database was created, provide its details
                """,
                tools=[duplicate_and_consolidate_pages],
            )

            # Run the duplication agent - without using Progress
            console.print("Duplicating pages...", style="bold cyan")
            
            # Prepare the prompt
            prompt = f"Duplicate these Notion pages: {page_ids} under a new parent page titled '{new_title}'"
            if schema:
                prompt += f"\nWith this consolidated database schema: {schema}"
            
            # Use SilenceOutput to suppress logging
            with SilenceOutput():
                result = await Runner.run(notion_duplicate_agent, prompt)
            console.print("[green]✓ Pages duplicated[/green]")

        elif command == "add-project":
            if len(sys.argv) < 3:
                console.print("[bold red]ERROR: Please provide a project title.[/bold red]")
                console.print("Usage: uv run starter_notion_agent.py add-project \"Project Title\"")
                return 1
                
            # Get project title from command line
            title = sys.argv[2]
            
            # Load properties from file
            try:
                with open("./bonus/project_props.json", "r") as f:
                    properties_json = f.read()
                    properties = json.loads(properties_json)
                console.print(f"[green]Loaded properties from project_props.json[/green]")
            except Exception as e:
                console.print(f"[bold red]ERROR loading properties: {str(e)}[/bold red]")
                properties = {
                    "Summary": {"rich_text": [{"text": {"content": "Project description"}}]},
                    "Status": {"select": {"name": "Planning"}},
                    "Priority": {"select": {"name": "High"}}
                }
                console.print("[yellow]Using default properties[/yellow]")
            
            # Create properties object with title
            page_properties = {
                "Title": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                }
            }
            
            # Add other properties
            for key, value in properties.items():
                if key != "Title":  # Skip title if already in properties
                    page_properties[key] = value
            
            # Prepare parent object
            parent = {
                "database_id": PROJECTS_DATABASE_ID
            }
            
            # Create direct agent
            console.print(f"[bold cyan]Creating project: {title}[/bold cyan]")
            project_agent = Agent(
                name="Project Creator",
                model=MODEL,
                instructions=f"""
                Create a new project in the Projects database with ID: {PROJECTS_DATABASE_ID}
                
                Use the mcp__notionApi__API-post-page endpoint with:
                - parent: {{database_id: "{PROJECTS_DATABASE_ID}"}}
                - properties: {json.dumps(page_properties, indent=2)}
                
                Return the ID and URL of the created project.
                """,
                mcp_servers=[await get_notion_mcp_server()],
            )
            
            # Run the agent
            result = await Runner.run(project_agent, f"Create a new project titled '{title}' in the Projects database")
            
            # Display results
            console.print("[green]✓ Project created[/green]")
            console.print(Panel.fit(
                result.final_output,
                title="Project Creation Results",
                border_style="green"
            ))
        
        elif command == "add-todo":
            if len(sys.argv) < 3:
                console.print("[bold red]ERROR: Please provide a todo title.[/bold red]")
                console.print("Usage: uv run starter_notion_agent.py add-todo \"Todo Title\"")
                return 1
                
            # Get todo title from command line
            title = sys.argv[2]
            
            # Load properties from file
            try:
                with open("./bonus/todo_props.json", "r") as f:
                    properties_json = f.read()
                    properties = json.loads(properties_json)
                console.print(f"[green]Loaded properties from todo_props.json[/green]")
            except Exception as e:
                console.print(f"[bold red]ERROR loading properties: {str(e)}[/bold red]")
                properties = {
                    "Status": {"select": {"name": "Not started"}},
                    "Priority": {"select": {"name": "Medium"}}
                }
                console.print("[yellow]Using default properties[/yellow]")
            
            # Create properties object with title
            page_properties = {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                }
            }
            
            # Add other properties
            for key, value in properties.items():
                if key != "Name":  # Skip title if already in properties
                    page_properties[key] = value
            
            # Prepare parent object
            parent = {
                "database_id": TODO_DATABASE_ID
            }
            
            # Create direct agent
            console.print(f"[bold cyan]Creating todo: {title}[/bold cyan]")
            todo_agent = Agent(
                name="Todo Creator",
                model=MODEL,
                instructions=f"""
                Create a new todo in the ToDo database with ID: {TODO_DATABASE_ID}
                
                Use the mcp__notionApi__API-post-page endpoint with:
                - parent: {{database_id: "{TODO_DATABASE_ID}"}}
                - properties: {json.dumps(page_properties, indent=2)}
                
                Return the ID and URL of the created todo.
                """,
                mcp_servers=[await get_notion_mcp_server()],
            )
            
            # Run the agent
            result = await Runner.run(todo_agent, f"Create a new todo titled '{title}' in the ToDo database")
            
            # Display results
            console.print("[green]✓ Todo created[/green]")
            console.print(Panel.fit(
                result.final_output,
                title="Todo Creation Results",
                border_style="green"
            ))

        elif command == "todo":
            if len(sys.argv) < 3:
                console.print("[bold red]ERROR: Please provide a page name.[/bold red]")
                return 1

            page_name = sys.argv[2]

            # Create enhanced Notion database manager agent
            notion_db_agent = Agent(
                name="Notion Database Manager",
                model=MODEL,
                instructions="""
                # Notion Database Manager
                
                ## Objective
                You are a powerful agent that can:
                1. Find and search for Notion pages by name and status
                2. Manage projects, tasks, and todo items across multiple databases
                3. Create, update, and link items across databases
                4. Duplicate and consolidate pages and databases
                5. Analyze database structures to understand relationships
                
                ## Available Databases
                - Projects Database (ID: 1e9e13474afd81c1bfa1c84f8b31297f)
                - Tasks Database (ID: 1e9e13474afd81f5badfce2bc7cc7455)
                - ToDo Database (ID: 1e9e13474afd8115ac29c6fcbd9a16e2)
                
                ## Project Management Capabilities
                - Create new projects with detailed properties
                - Create tasks and link them to projects
                - Create todo items for personal or work activities
                - Update status of tasks and todos
                - Analyze database structures to understand schemas
                - Link related items across databases
                
                ## Guidelines
                - Be clear and concise in your responses
                - Use appropriate tools based on the user's request
                - Prevent deletion of existing data
                - Format results nicely for readability
                - Make intelligent use of database relationship capabilities
                """,
                tools=[
                    # Search and retrieval tools
                    search_notion_pages,
                    find_notion_page,
                    get_notion_page_content,
                    get_notion_database,
                    query_notion_database,
                    get_database_structure,
                    
                    # Creation tools
                    create_project,
                    create_task,
                    create_todo,
                    create_notion_page,
                    create_notion_database,
                    
                    # Update tools
                    update_task_status,
                    complete_todo, 
                    link_project_to_tasks,
                    
                    # Batch operations
                    batch_update_notion_records,
                    duplicate_and_consolidate_pages,
                ],
            )

            # Run the database manager agent - without using Progress
            console.print("Starting Notion Database Manager...", style="bold cyan")
            # Use SilenceOutput to suppress logging
            with SilenceOutput():
                result = await Runner.run(
                    notion_db_agent,
                    f"The user wants to interact with Notion page named '{page_name}'. First, search for this page and then help the user manage content across Projects, Tasks, and ToDo databases. Remember to prevent data deletion."
                )
            console.print("[green]✓ Database management complete[/green]")

        else:
            console.print(f"[bold red]ERROR: Unknown command '{command}'[/bold red]")
            return 1

        # We won't print the result here anymore, as each command-specific handler
        # already prints its own success message.
        console.print("\n[bold green]✅ Agent execution complete![/bold green]")
        
        return 0
        
    except Exception as e:
        console.print(f"[bold red]ERROR: {str(e)}[/bold red]")
        return 1
    finally:
        # MCPServerStdio cleanup - we won't use any of its methods directly
        # as they seem to be causing issues
        global _notion_mcp_server
        if _notion_mcp_server is not None:
            try:
                # Try to find and terminate the npx process directly
                try:
                    # Use os.killpg to make sure we kill the whole process group
                    import psutil
                    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                        try:
                            # Look for npx processes with notion-mcp-server
                            if proc.info['name'] == 'node' and proc.info['cmdline'] and any('notion-mcp-server' in cmd for cmd in proc.info['cmdline']):
                                proc.terminate()
                                console.print(f"[cyan]Terminated Notion MCP server process with PID {proc.pid}[/cyan]")
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            pass
                except ImportError:
                    # psutil not available, fallback to basic process termination
                    if hasattr(_notion_mcp_server, '_process') and _notion_mcp_server._process:
                        try:
                            if _notion_mcp_server._process.returncode is None:
                                _notion_mcp_server._process.terminate()
                                _notion_mcp_server._process.wait(timeout=1)
                                console.print("[cyan]Terminated Notion MCP server process[/cyan]")
                        except:
                            # If terminate fails, try kill
                            try:
                                _notion_mcp_server._process.kill()
                                console.print("[cyan]Killed Notion MCP server process[/cyan]")
                            except:
                                pass
                
                # Cleanup reference to avoid further cleanup attempts
                _notion_mcp_server = None
            except Exception as close_error:
                console.print(f"[yellow]Warning during cleanup: {str(close_error)}[/yellow]")

def sync_main():
    """A synchronous wrapper around main() that handles all the asyncio details."""
    # Create and set up the event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Configure asyncio to ignore RuntimeError during shutdown
    # Specifically handle BaseSubprocessTransport.__del__ errors
    def custom_exception_handler(loop, context):
        # Ignore BaseSubprocessTransport.__del__ errors
        error_message = context.get('exception', context.get('message', ''))
        if 'BaseSubprocessTransport.__del__' in str(context):
            return  # Silently ignore these errors
        # For other errors, print them but don't crash
        console.print(f"[yellow]Async warning: {error_message}[/yellow]")
    
    loop.set_exception_handler(custom_exception_handler)
    
    try:
        # Run the main function
        exit_code = loop.run_until_complete(main())
        return exit_code
    except KeyboardInterrupt:
        console.print("[yellow]Operation cancelled by user[/yellow]")
        return 1
    except Exception as e:
        console.print(f"[bold red]Unhandled error: {str(e)}[/bold red]")
        return 1
    finally:
        # Attempt graceful cleanup of all resources
        try:
            # Cancel all running tasks
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            
            # Wait for tasks to complete with a timeout
            if tasks:
                # Use a short timeout to avoid hanging
                future = asyncio.gather(*tasks, return_exceptions=True)
                try:
                    loop.run_until_complete(asyncio.wait_for(future, timeout=2))
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass  # Ignore timeout/cancellation errors during cleanup
        except Exception as e:
            # Just log cleanup errors, don't crash
            console.print(f"[yellow]Cleanup warning: {str(e)}[/yellow]")
        
        # Close the loop
        try:
            # Run loop one final time to ensure transport cleanup
            loop.run_until_complete(asyncio.sleep(0.1))
            loop.close()
        except Exception:
            # Forcefully close if needed
            try:
                loop.close()
            except:
                pass

if __name__ == "__main__":
    # Use our custom main function instead of asyncio.run
    try:
        exit_code = sync_main()
        sys.exit(exit_code)
    except Exception as e:
        console.print(f"[bold red]Fatal error: {str(e)}[/bold red]")
        os._exit(1)  # Force immediate exit if all else fails