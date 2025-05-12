"""
State management for Limitless Lifelog.
"""

import os
import json
import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from loguru import logger

class StateManager:
    """
    Manages state between runs, including tracking last execution time,
    processed transcript IDs, and Notion mapping information.
    """
    
    def __init__(self, state_file: str = None):
        """
        Initialize state manager with optional custom state file path.
        
        Args:
            state_file: Path to state file (optional)
        """
        if state_file:
            self.state_file = Path(state_file)
        else:
            # Default to user config directory
            config_dir = Path.home() / ".config" / "limitless-lifelog"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.state_file = config_dir / "state.json"
        
        # Create state file if it doesn't exist
        if not self.state_file.exists():
            self._initialize_state_file()
        
        # Load state
        self.state = self._load_state()
    
    def _initialize_state_file(self):
        """Initialize state file with default values."""
        default_state = {
            "last_run_time": None,
            "processed_transcripts": [],
            "notion_mappings": {
                "tasks": {},
                "projects": {},
                "todo": {}
            },
            "statistics": {
                "total_transcripts_processed": 0,
                "items_created": {
                    "tasks": 0,
                    "projects": 0,
                    "todo": 0
                }
            }
        }
        
        with open(self.state_file, "w") as f:
            json.dump(default_state, f, indent=2, default=str)
    
    def _load_state(self) -> Dict[str, Any]:
        """
        Load state from state file.
        
        Returns:
            Dictionary containing state information
        """
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Error loading state file: {e}")
            # If corrupted or missing, create a new one
            self._initialize_state_file()
            return self._load_state()
    
    def _save_state(self):
        """Save current state to state file."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving state file: {e}")
    
    def get_last_run_time(self) -> Optional[datetime.datetime]:
        """
        Get the timestamp of the last run.
        
        Returns:
            Datetime of last run or None if first run
        """
        last_run = self.state.get("last_run_time")
        if not last_run:
            return None
        
        # Convert string to datetime
        try:
            return datetime.datetime.fromisoformat(last_run)
        except ValueError:
            logger.error(f"Invalid last run time format: {last_run}")
            return None
    
    def set_last_run_time(self, time: datetime.datetime = None):
        """
        Set the last run time to current time or specified time.
        
        Args:
            time: Datetime to set (defaults to current time)
        """
        if time is None:
            time = datetime.datetime.now()
        
        self.state["last_run_time"] = time.isoformat()
        self._save_state()
    
    def add_processed_transcript(self, transcript_id: str):
        """
        Add a transcript ID to the list of processed transcripts.
        
        Args:
            transcript_id: ID of processed transcript
        """
        if transcript_id not in self.state["processed_transcripts"]:
            self.state["processed_transcripts"].append(transcript_id)
            self.state["statistics"]["total_transcripts_processed"] += 1
            self._save_state()
    
    def is_transcript_processed(self, transcript_id: str) -> bool:
        """
        Check if a transcript has already been processed.
        
        Args:
            transcript_id: ID of transcript to check
            
        Returns:
            True if transcript has been processed, False otherwise
        """
        return transcript_id in self.state["processed_transcripts"]
    
    def add_notion_mapping(self, item_type: str, transcript_id: str, notion_id: str):
        """
        Add mapping between transcript item and Notion item.
        
        Args:
            item_type: Type of item (tasks, projects, todo)
            transcript_id: ID from transcript
            notion_id: ID in Notion
        """
        if item_type not in self.state["notion_mappings"]:
            self.state["notion_mappings"][item_type] = {}
        
        self.state["notion_mappings"][item_type][transcript_id] = notion_id
        
        # Update statistics
        if item_type in self.state["statistics"]["items_created"]:
            self.state["statistics"]["items_created"][item_type] += 1
        
        self._save_state()
    
    def get_notion_id(self, item_type: str, transcript_id: str) -> Optional[str]:
        """
        Get Notion ID for a transcript item.
        
        Args:
            item_type: Type of item (tasks, projects, todo)
            transcript_id: ID from transcript
            
        Returns:
            Notion ID or None if not found
        """
        if item_type not in self.state["notion_mappings"]:
            return None
        
        return self.state["notion_mappings"][item_type].get(transcript_id)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get processing statistics.
        
        Returns:
            Dictionary of statistics
        """
        return self.state["statistics"]