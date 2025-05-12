"""
Test the enhanced tag generation features.

Verifies that at least 5 tags are being generated for all item types with useful information.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.limitless_lifelog.transcripts.transformer import DataTransformer


class TestEnhancedTagGeneration(unittest.TestCase):
    """Test case for enhanced tag generation in DataTransformer."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_notion_client = MagicMock()
        self.mock_notion_client.get_existing_tags.return_value = [
            "API Integration", "Web Development", "Client Project", "Workflow Automation",
            "Data Analysis", "Machine Learning", "Urgent", "High Impact"
        ]
        
        self.transformer = DataTransformer(
            notion_client=self.mock_notion_client
        )
        
        # Sample project data
        self.project_data = {
            "name": "Test Project",
            "description": "This is a test project",
            "priority": "high",
            "status": "Planning",
            "url": "https://example.com/project",
            "transcript_id": "test123",
            "transcript_details": {
                "content": "This is a sample transcript content discussing the development of a new application. We need to focus on features like authentication and data storage. The design should be clean and user-friendly.",
                "keywords": ["development", "application", "features"],
                "action_keywords": ["development", "design", "create", "build"]
            }
        }
        
        # Sample task data
        self.task_data = {
            "title": "Test Task",
            "description": "This is a test task",
            "priority": "medium",
            "due_date": (datetime.now().strftime("%Y-%m-%d")),  # Today
            "status": "Not Started",
            "project": "Client Portal",
            "transcript_id": "test456",
            "transcript_details": {
                "content": "Create a login form with email and password fields. Add validation and error handling. The design should match our brand guidelines.",
                "keywords": ["login", "form", "validation"],
                "action_keywords": ["create", "build", "design"]
            }
        }

    def test_generate_enhanced_tags_for_tasks(self):
        """Test enhanced tag generation for tasks."""
        # Get tags using the new function
        tags = self.transformer._generate_enhanced_tags(
            self.task_data, "task", self.task_data["transcript_details"]
        )
        
        # Verify at least 5 tags are generated
        self.assertGreaterEqual(len(tags), 5, f"Not enough tags generated: {tags}")
        
        # Verify specific types of tags
        self.assertTrue(any(tag.startswith("Priority:") for tag in tags), 
                       f"No priority tag found in: {tags}")
        
        self.assertTrue(any(tag in ["Due Today", "Due Soon", "Overdue", "Future Due Date"] for tag in tags),
                       f"No due date tag found in: {tags}")
        
        # Verify project name is included
        self.assertIn("Client Portal", tags)
        
        # Verify content keywords are included
        self.assertTrue(any(kw.lower() in [t.lower() for t in tags] 
                           for kw in ["login", "form", "validation"]),
                       f"No content keywords found in: {tags}")
        
        print(f"Task tags generated: {tags}")

    def test_generate_enhanced_tags_for_projects(self):
        """Test enhanced tag generation for projects."""
        # Get tags using the new function
        tags = self.transformer._generate_enhanced_tags(
            self.project_data, "project", self.project_data["transcript_details"]
        )
        
        # Verify at least 5 tags are generated
        self.assertGreaterEqual(len(tags), 5, f"Not enough tags generated: {tags}")
        
        # Verify specific types of tags
        self.assertTrue(any(tag.startswith("Priority:") for tag in tags), 
                       f"No priority tag found in: {tags}")
        
        # Verify URL tag is included
        self.assertIn("Has URL", tags)
        
        # Verify content keywords are included
        content_keywords = ["development", "application", "features"]
        self.assertTrue(any(kw.lower() in [t.lower() for t in tags] 
                           for kw in content_keywords),
                       f"No content keywords found in: {tags}")
        
        # Verify project type is detected
        self.assertTrue(any(tag in ["Development", "Web"] for tag in tags),
                       f"No project type tag found in: {tags}")
        
        print(f"Project tags generated: {tags}")

    def test_tags_from_existing_notion_tags(self):
        """Test that existing Notion tags are used when relevant."""
        # Add a known tag to the content
        self.task_data["transcript_details"]["content"] += " This task involves Web Development and API Integration."
        
        # Get tags using the new function
        tags = self.transformer._generate_enhanced_tags(
            self.task_data, "task", self.task_data["transcript_details"]
        )
        
        # Verify existing Notion tags are found and included
        self.assertTrue(any(tag in ["Web Development", "API Integration"] for tag in tags),
                       f"No existing Notion tags found in: {tags}")
        
        print(f"Tags with existing Notion tags: {tags}")

    def test_tags_for_minimal_item(self):
        """Test tag generation for items with minimal data."""
        # Create a minimal task with no keywords or transcript details
        minimal_task = {
            "title": "Minimal Task",
            "priority": "low",
            "transcript_id": "min123"
        }
        
        # Get tags using the new function
        tags = self.transformer._generate_enhanced_tags(
            minimal_task, "task", {}
        )
        
        # Verify at least 5 tags are generated even with minimal data
        self.assertGreaterEqual(len(tags), 5, f"Not enough tags generated for minimal task: {tags}")
        
        # Verify priority tag is included
        self.assertIn("Priority: Low", tags)
        
        # Verify default tags are included
        default_tags = ["Task", "Action", "Voice", "Transcript"]
        self.assertTrue(any(tag in default_tags for tag in tags),
                       f"No default tags found in: {tags}")
        
        print(f"Minimal task tags generated: {tags}")


if __name__ == "__main__":
    unittest.main()