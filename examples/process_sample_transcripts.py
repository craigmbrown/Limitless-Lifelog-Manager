#!/usr/bin/env python3
"""
Example script for processing sample transcripts with Limitless Lifelog.

This script demonstrates how to:
1. Generate mock transcript data
2. Process transcripts
3. Extract actionable items
4. Transform to Notion format
5. Print the results without updating Notion

This can be used for testing or to understand the data flow.
"""

import os
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import argparse

# Add the parent directory to sys.path so we can import the package
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from limitless_lifelog.limitless.api_client import LimitlessClient
from limitless_lifelog.transcripts.processor import TranscriptProcessor
from limitless_lifelog.transcripts.extractor import ItemExtractor
from limitless_lifelog.transcripts.transformer import DataTransformer


def save_mock_transcripts(count=10, output_file="sample_transcripts.json"):
    """Generate and save mock transcript data."""
    client = LimitlessClient(api_key="mock_key")
    mock_transcripts = client.mock_transcript_data(count=count)
    
    with open(output_file, 'w') as f:
        json.dump(mock_transcripts, f, indent=2)
    
    print(f"Saved {count} mock transcripts to {output_file}")
    return mock_transcripts


def process_transcripts(transcripts, llm_provider="openai", llm_model="gpt-4"):
    """Process transcripts and extract items."""
    # Since this is just a demo, we'll mock the LLM processing
    # by hardcoding some extracted items
    
    processor = TranscriptProcessor(llm_provider=llm_provider, llm_model=llm_model)
    
    # Filter transcripts
    print(f"Processing {len(transcripts)} transcripts...")
    filtered_transcripts = processor.filter_transcripts(transcripts)
    print(f"{len(filtered_transcripts)} transcripts remain after filtering")
    
    # Extract items (mocked for demo)
    # Skip creating actual extractor to avoid API calls
    # extractor = ItemExtractor(llm_provider=llm_provider, llm_model=llm_model)

    # Simulate extraction results
    extracted_items = {
        "tasks": [],
        "meetings": [],
        "projects": [],
        "research": [],
        "messages": []
    }
    
    # Create sample extracted items from transcripts
    for i, transcript in enumerate(filtered_transcripts):
        content = transcript.get("content", "")
        
        # Sample task extraction
        if "task" in content.lower() or "todo" in content.lower() or i % 3 == 0:
            # Create a more detailed task with rich transcript details
            task = {
                "item_id": f"task-{i}",
                "transcript_id": transcript.get("id", ""),
                "title": f"Task from transcript {i+1}",
                "description": content[:100] + "...",
                "priority": ["high", "medium", "low"][i % 3],
                "due_date": (datetime.now() + timedelta(days=i+1)).strftime("%Y-%m-%d"),
                "transcript_details": {
                    "content": content,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "context": f"Extended context for task from transcript {i+1}",
                    "keywords": ["task", "important", "project", "timeline", "deadline", "database"],
                    "importance_level": ["high", "medium", "medium-high"][i % 3],
                    "action_keywords": ["complete", "update", "review", "implement", "schedule"],
                    "priority_indicators": [
                        {"keyword": "important", "priority": "high", "context": "This is important work"},
                        {"keyword": "soon", "priority": "medium", "context": "Complete this soon"}
                    ],
                    "status_indicators": [
                        {"keyword": "started", "status": "In Progress", "context": "We've already started this"}
                    ],
                    "date_indicators": [
                        {"date": "next week", "text": "due next week", "position": 50}
                    ]
                }
            }
            extracted_items["tasks"].append(task)
        
        # Sample meeting extraction
        if "meeting" in content.lower() or "schedule" in content.lower() or i % 4 == 1:
            # Create a more detailed meeting with rich transcript details
            meeting = {
                "item_id": f"meeting-{i}",
                "transcript_id": transcript.get("id", ""),
                "title": f"Meeting from transcript {i+1}",
                "agenda": f"Discuss topics from transcript {i+1}",
                "participants": "Team members",
                "date": (datetime.now() + timedelta(days=i+2)).strftime("%Y-%m-%d"),
                "time": "10:00:00",
                "transcript_details": {
                    "content": content,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "context": f"Extended context for meeting from transcript {i+1}",
                    "keywords": ["meeting", "discussion", "team", "timeline", "product", "rollout"],
                    "importance_level": ["high", "medium", "medium-high"][i % 3],
                    "action_keywords": ["discuss", "finalize", "present", "schedule", "coordinate"],
                    "priority_indicators": [
                        {"keyword": "important", "priority": "high", "context": "Important meeting to attend"}
                    ],
                    "status_indicators": [
                        {"keyword": "scheduled", "status": "Not Started", "context": "Meeting is scheduled"}
                    ],
                    "date_indicators": [
                        {"date": "Thursday", "text": "meeting on Thursday", "position": 30}
                    ]
                }
            }
            extracted_items["meetings"].append(meeting)
        
        # Sample project extraction
        if "project" in content.lower() or i % 5 == 2:
            # Create a more detailed project with rich transcript details
            project = {
                "item_id": f"project-{i}",
                "transcript_id": transcript.get("id", ""),
                "name": f"Project from transcript {i+1}",
                "description": content[:100] + "...",
                "timeline": {
                    "start": datetime.now().strftime("%Y-%m-%d"),
                    "end": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                },
                "transcript_details": {
                    "content": content,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "context": f"Extended context for project from transcript {i+1}",
                    "keywords": ["project", "planning", "timeline", "implementation", "budget", "resources"],
                    "importance_level": ["high", "medium", "medium-high"][i % 3],
                    "action_keywords": ["launch", "develop", "design", "test", "implement"],
                    "priority_indicators": [
                        {"keyword": "critical", "priority": "high", "context": "This is a critical project"},
                        {"keyword": "key", "priority": "high", "context": "Key project for Q2"}
                    ],
                    "status_indicators": [
                        {"keyword": "in progress", "status": "In Progress", "context": "Project is in progress"},
                        {"keyword": "started", "status": "In Progress", "context": "We've already started this"}
                    ],
                    "date_indicators": [
                        {"date": "July", "text": "complete by July", "position": 40},
                        {"date": "Q2", "text": "Q2 goal", "position": 60}
                    ]
                }
            }
            extracted_items["projects"].append(project)
    
    print("Extracted items:")
    for category, items in extracted_items.items():
        print(f"  {category}: {len(items)}")
    
    return extracted_items


def transform_to_notion(extracted_items):
    """Transform extracted items to Notion format."""
    transformer = DataTransformer()
    notion_data = transformer.transform(extracted_items)
    
    print("Transformed for Notion:")
    for db_type, items in notion_data.items():
        print(f"  {db_type}: {len(items)}")
    
    return notion_data


def main():
    """Main function to run the example."""
    parser = argparse.ArgumentParser(
        description="Process sample transcripts with Limitless Lifelog"
    )
    parser.add_argument(
        "--count", 
        type=int, 
        default=10,
        help="Number of mock transcripts to generate"
    )
    parser.add_argument(
        "--output", 
        default="sample_transcripts.json",
        help="Output file for mock transcripts"
    )
    parser.add_argument(
        "--save-notion", 
        action="store_true",
        help="Save Notion data to file"
    )
    
    args = parser.parse_args()
    
    # Create mock transcripts
    transcripts = save_mock_transcripts(args.count, args.output)
    
    # Process transcripts
    extracted_items = process_transcripts(transcripts)
    
    # Transform for Notion
    notion_data = transform_to_notion(extracted_items)
    
    # Optionally save Notion data
    if args.save_notion:
        notion_output = os.path.splitext(args.output)[0] + "_notion.json"
        with open(notion_output, 'w') as f:
            json.dump(notion_data, f, indent=2, default=str)
        print(f"Saved Notion data to {notion_output}")
    
    print("\nExample complete! In a real run, this data would be sent to Notion.")


if __name__ == "__main__":
    main()