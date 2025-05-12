#!/bin/bash
# Setup script for Limitless Lifelog
# Creates a template .env file and checks dependencies

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

echo "Setting up Limitless Lifelog environment..."

# Create .env file if it doesn't exist
if [ ! -f "$ENV_FILE" ]; then
  echo "Creating template .env file..."
  cat > "$ENV_FILE" << EOF
# API Keys
LIMITLESS_API_KEY=your_limitless_api_key
NOTION_API_KEY=your_notion_api_key

# LLM Configuration
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key

# Default LLM Settings
DEFAULT_LLM_PROVIDER=openai
DEFAULT_LLM_MODEL=gpt-4

# Notion Database IDs
NOTION_TASKS_DB_ID=your_notion_tasks_database_id
NOTION_PROJECTS_DB_ID=your_notion_projects_database_id
NOTION_TODO_DB_ID=your_notion_todo_database_id
NOTION_LIFELOG_DB_ID=your_notion_lifelog_database_id
EOF
  echo "Created template .env file at $ENV_FILE"
  echo "Please edit this file and add your API keys and database IDs."
else
  echo ".env file already exists at $ENV_FILE"
fi

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
  echo "Warning: Limitless Lifelog requires Python 3.10 or newer."
  echo "Current version: $PYTHON_VERSION"
  echo "Please upgrade your Python installation."
else
  echo "Python version $PYTHON_VERSION is compatible."
fi

# Try installing package in development mode
echo "Installing package in development mode..."
if pip install -e "$PROJECT_ROOT"; then
  echo "Package installed successfully in development mode."
else
  echo "Warning: Failed to install package. Please check your Python environment."
fi

# Check for required dependencies
echo "Checking dependencies..."
MISSING_DEPS=0

check_dependency() {
  if ! pip show "$1" > /dev/null 2>&1; then
    echo "Warning: Missing dependency: $1"
    MISSING_DEPS=$((MISSING_DEPS + 1))
  fi
}

check_dependency "requests"
check_dependency "python-dotenv"
check_dependency "pydantic"
check_dependency "loguru"

if [ $MISSING_DEPS -gt 0 ]; then
  echo "Missing $MISSING_DEPS dependencies. Installing them..."
  pip install -r "$PROJECT_ROOT/requirements.txt"
else
  echo "All core dependencies are installed."
fi

# Create log directory
mkdir -p "$PROJECT_ROOT/logs"
echo "Created logs directory."

echo "Setup complete! You can now run the application using 'lifelog' command."
echo "For testing, try running the example script:"
echo "python $PROJECT_ROOT/examples/process_sample_transcripts.py"