"""
Keyword configuration loader for Limitless Lifelog.

Provides functions to load and manage keyword configurations for transcript processing.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from loguru import logger

class KeywordsConfig:
    """
    Manages keyword configurations for transcript processing and extraction.

    Loads keywords from configuration files and provides them to the processor
    and transformer modules.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize keywords configuration.

        Args:
            config_path: Path to the keywords configuration file
        """
        self.default_config_path = str(Path(__file__).parent.parent.parent.parent / "specs" / "config" / "keywords.json")
        self.config_path = config_path or self.default_config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """
        Load keywords configuration from file.

        Returns:
            Dictionary with keyword configurations
        """
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                logger.debug(f"Loaded keywords configuration from {self.config_path}")
                return config
            else:
                logger.warning(f"Keywords configuration file not found at {self.config_path}, using defaults")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading keywords configuration: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """
        Get default keyword configurations.

        Returns:
            Dictionary with default keyword configurations
        """
        return {
            "priority_keywords": {
                "high": ["urgent", "asap", "critical", "important", "high priority", "p0", "p1"],
                "medium": ["moderate", "medium priority", "p2", "soon"],
                "low": ["low priority", "whenever", "p3", "p4", "sometime"]
            },
            "status_keywords": {
                "Not Started": ["todo", "to-do", "to do", "planned", "not started", "upcoming", "new", "need to"],
                "In Progress": ["in progress", "started", "working on", "ongoing", "underway", "beginning"],
                "Completed": ["done", "completed", "finished", "complete", "resolved"]
            },
            "action_keywords": [
                "todo", "to-do", "to do", "task", "action", "action item",
                "need to", "should", "must", "will", "plan", "remind me",
                "don't forget", "remember to", "important", "priority",
                "follow up", "followup", "follow-up", "deadline", "due",
                "schedule", "meeting", "project", "complete", "finish",
                "implement", "create", "build", "make", "fix", "update",
                "write", "send", "email", "call", "contact", "check",
                "review", "investigate", "research", "analyze", "test",
                "TB", "TeeBee"
            ],
            "excluded_common_words": [
                "the", "and", "or", "but", "if", "then", "to", "a", "an", "of", "for", "in",
                "on", "at", "by", "with", "about", "task", "todo", "need", "should", "must",
                "important", "critical", "high", "medium", "low", "tb", "teebee"
            ],
            "existing_notion_tags": [],
            "descriptor_tags": {
                "task": ["action", "task", "todo", "assignment", "work", "responsibility", "duty", "job", "activity"],
                "project": ["project", "initiative", "endeavor", "undertaking", "plan", "effort", "venture", "mission"],
                "meeting": ["meeting", "discussion", "call", "conference", "gathering", "session", "huddle", "sync"],
                "research": ["research", "investigation", "analysis", "study", "exploration", "review", "assessment"],
                "message": ["message", "communication", "email", "notification", "update", "reminder", "alert"]
            }
        }

    def get_priority_keywords(self) -> Dict[str, List[str]]:
        """
        Get priority keywords.

        Returns:
            Dictionary mapping priority levels to keywords
        """
        return self.config.get("priority_keywords", self._get_default_config()["priority_keywords"])

    def get_status_keywords(self) -> Dict[str, List[str]]:
        """
        Get status keywords.

        Returns:
            Dictionary mapping status values to keywords
        """
        return self.config.get("status_keywords", self._get_default_config()["status_keywords"])

    def get_action_keywords(self) -> List[str]:
        """
        Get action keywords.

        Returns:
            List of action keywords
        """
        return self.config.get("action_keywords", self._get_default_config()["action_keywords"])

    def get_excluded_words(self) -> List[str]:
        """
        Get excluded common words.

        Returns:
            List of common words to exclude from keyword extraction
        """
        return self.config.get("excluded_common_words", self._get_default_config()["excluded_common_words"])

    def get_project_category_keywords(self) -> Dict[str, List[str]]:
        """
        Get project category keywords.

        Returns:
            Dictionary mapping project categories to keywords
        """
        return self.config.get("project_category_keywords", {})

    def get_date_keywords(self) -> List[str]:
        """
        Get date reference keywords.

        Returns:
            List of date reference keywords
        """
        return self.config.get("date_keywords", [])

    def get_existing_notion_tags(self) -> List[str]:
        """
        Get existing tags from Notion that have been previously cached.

        Returns:
            List of existing Notion tags
        """
        return self.config.get("existing_notion_tags", [])

    def get_descriptor_tags(self, item_type: str) -> List[str]:
        """
        Get descriptor tags for a specific item type.

        Args:
            item_type: Type of item (task, project, meeting, research, message)

        Returns:
            List of descriptor tags for the item type
        """
        descriptors = self.config.get("descriptor_tags", self._get_default_config()["descriptor_tags"])
        return descriptors.get(item_type, [])

    def update_existing_notion_tags(self, tags: List[str]) -> None:
        """
        Update the existing Notion tags in the configuration.

        Args:
            tags: List of tags from Notion
        """
        if not tags:
            return

        # Get existing tags
        existing_tags = set(self.config.get("existing_notion_tags", []))

        # Add new tags
        existing_tags.update(tags)

        # Update config
        self.config["existing_notion_tags"] = sorted(list(existing_tags))

        # Save to file
        self._save_config()

    def _save_config(self) -> None:
        """Save the current configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.debug(f"Saved updated keywords configuration to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving keywords configuration: {e}")

    def add_descriptor_tag(self, item_type: str, tag: str) -> None:
        """
        Add a descriptor tag for a specific item type.

        Args:
            item_type: Type of item (task, project, meeting, research, message)
            tag: Tag to add
        """
        if not item_type or not tag:
            return

        # Initialize descriptor_tags if it doesn't exist
        if "descriptor_tags" not in self.config:
            self.config["descriptor_tags"] = self._get_default_config()["descriptor_tags"]

        # Initialize item type if it doesn't exist
        if item_type not in self.config["descriptor_tags"]:
            self.config["descriptor_tags"][item_type] = []

        # Add tag if it doesn't exist
        if tag not in self.config["descriptor_tags"][item_type]:
            self.config["descriptor_tags"][item_type].append(tag)
            self._save_config()