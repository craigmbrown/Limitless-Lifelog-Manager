"""
Tests for tag generation in the DataTransformer class.

Ensures that at least 5 tags are being properly generated for both tasks and projects.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.limitless_lifelog.transcripts.transformer import DataTransformer


class TestTagGeneration(unittest.TestCase):
    """Test case for tag generation in DataTransformer."""

    def setUp(self):
        """Set up test fixtures."""
        self.transformer = DataTransformer()
        
        # Sample project data
        self.project_data = {
            "name": "Test Project",
            "description": "This is a test project",
            "priority": "high",
            "status": "Planning",
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
            "status": "Not Started",
            "transcript_id": "test456",
            "transcript_details": {
                "content": "Create a login form with email and password fields. Add validation and error handling. The design should match our brand guidelines.",
                "keywords": ["login", "form", "validation"],
                "action_keywords": ["create", "build", "design"]
            }
        }

    def test_project_tag_generation(self):
        """Test that at least 5 tags are generated for projects."""
        # Transform the test project
        notion_project = self.transformer._transform_project(self.project_data)
        
        # Check that Tags property exists
        self.assertIn("Tags", notion_project["properties"])
        
        # Check that at least 5 tags are generated
        tags = [tag["name"] for tag in notion_project["properties"]["Tags"]["multi_select"]]
        self.assertGreaterEqual(len(tags), 5)
        
        # Check that priority is included in tags
        self.assertIn("Priority: High", tags)
        
        # Check that some project type tags are included
        project_type_tags = ["Development", "Design"]
        self.assertTrue(any(tag in tags for tag in project_type_tags), f"No project type tag found in {tags}")
        
        # Check that keywords from transcript content are included
        content_keywords = ["Application", "Features", "Authentication", "Storage"]
        self.assertTrue(any(tag in tags for tag in content_keywords), f"No content keyword found in {tags}")
        
        print(f"Project tags generated: {tags}")

    def test_task_tag_generation(self):
        """Test that at least 5 tags are generated for tasks."""
        # Transform the test task
        notion_task = self.transformer._transform_task(self.task_data)
        
        # Check that Tags property exists
        self.assertIn("Tags", notion_task["properties"])
        
        # Check that at least 5 tags are generated
        tags = [tag["name"] for tag in notion_task["properties"]["Tags"]["multi_select"]]
        self.assertGreaterEqual(len(tags), 5)
        
        # Check that priority is included in tags
        self.assertIn("Priority: Medium", tags)
        
        # Check that some task keywords are included
        task_keywords = ["Login", "Form", "Validation"]
        self.assertTrue(any(tag in tags for tag in task_keywords), f"No task keyword found in {tags}")
        
        print(f"Task tags generated: {tags}")

    def test_minimal_project_tag_generation(self):
        """Test tag generation for projects with minimal data."""
        # Create a minimal project with no keywords or transcript details
        minimal_project = {
            "name": "Minimal Project",
            "priority": "low",
            "transcript_id": "min123"
        }
        
        # Transform the minimal project
        notion_project = self.transformer._transform_project(minimal_project)
        
        # Check that Tags property exists
        self.assertIn("Tags", notion_project["properties"])
        
        # Check that at least 5 tags are generated
        tags = [tag["name"] for tag in notion_project["properties"]["Tags"]["multi_select"]]
        self.assertGreaterEqual(len(tags), 5)
        
        # Check that priority is included in tags
        self.assertIn("Priority: Low", tags)
        
        # Check that default tags are included
        default_tags = ["Project", "Initiative", "Planning", "Voice", "Transcript"]
        self.assertTrue(any(tag in tags for tag in default_tags), f"No default tag found in {tags}")
        
        print(f"Minimal project tags generated: {tags}")


if __name__ == "__main__":
    unittest.main()