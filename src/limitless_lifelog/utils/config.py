"""
Configuration management for Limitless Lifelog.
"""

import os
import configparser
from pathlib import Path
from typing import Dict, Optional
from loguru import logger

class Config:
    """
    Configuration manager for Limitless Lifelog.
    
    Handles loading configuration from environment variables and config files.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration with optional config file path.
        
        Args:
            config_path: Path to configuration file (optional)
        """
        # Default settings
        self.limitless_api_key = os.environ.get("LIMITLESS_API_KEY", "")
        # Default to environment variable or use a more direct endpoint without added path segments
        self.limitless_api_url = os.environ.get("LIMITLESS_API_URL", "https://api.limitless.ai/v1")
        self.notion_api_key = os.environ.get("NOTION_API_KEY", "")

        self.llm_provider = os.environ.get("DEFAULT_LLM_PROVIDER", "openai")
        self.llm_model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4")

        self.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        
        self.notion_database_ids = {
            "tasks": os.environ.get("NOTION_TASKS_DB_ID", ""),
            "projects": os.environ.get("NOTION_PROJECTS_DB_ID", ""),
            "todo": os.environ.get("NOTION_TODO_DB_ID", ""),
            "lifelog": os.environ.get("NOTION_LIFELOG_DB_ID", "")
        }
        
        # Load from config file if provided
        if config_path:
            self._load_from_file(config_path)
        
        # Validate configuration
        self._validate_config()
    
    def _load_from_file(self, config_path: str):
        """
        Load configuration from file.
        
        Args:
            config_path: Path to configuration file
        """
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Config file not found: {config_path}")
            return
        
        config = configparser.ConfigParser()
        config.read(path)
        
        # API Keys
        if "API" in config:
            self.limitless_api_key = config.get("API", "LIMITLESS_API_KEY", fallback=self.limitless_api_key)
            self.limitless_api_url = config.get("API", "LIMITLESS_API_URL", fallback=self.limitless_api_url)
            self.notion_api_key = config.get("API", "NOTION_API_KEY", fallback=self.notion_api_key)
            self.openai_api_key = config.get("API", "OPENAI_API_KEY", fallback=self.openai_api_key)
            self.anthropic_api_key = config.get("API", "ANTHROPIC_API_KEY", fallback=self.anthropic_api_key)
        
        # LLM Settings
        if "LLM" in config:
            self.llm_provider = config.get("LLM", "PROVIDER", fallback=self.llm_provider)
            self.llm_model = config.get("LLM", "MODEL", fallback=self.llm_model)
        
        # Notion Database IDs
        if "NOTION" in config:
            for key in self.notion_database_ids:
                db_key = f"{key.upper()}_DB_ID"
                if db_key in config["NOTION"]:
                    self.notion_database_ids[key] = config["NOTION"][db_key]
    
    def _validate_config(self):
        """Validate configuration and warn about missing values."""
        if not self.limitless_api_key:
            logger.warning("Limitless API key not found")

        if not self.limitless_api_url:
            logger.warning("Limitless API URL not configured")

        if not self.notion_api_key:
            logger.warning("Notion API key not found")

        if self.llm_provider == "openai" and not self.openai_api_key:
            logger.warning("OpenAI API key not found but provider is set to OpenAI")

        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            logger.warning("Anthropic API key not found but provider is set to Anthropic")

        for key, value in self.notion_database_ids.items():
            if not value:
                logger.warning(f"Notion {key} database ID not found")