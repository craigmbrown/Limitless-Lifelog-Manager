"""
Transform extracted items into Notion-compatible format.
"""

from typing import Dict, List, Any
from loguru import logger

class DataTransformer:
    """
    Transforms extracted items into formats compatible with Notion databases.
    
    Maps extracted properties to the appropriate Notion schema.
    """
    
    def __init__(self, notion_client=None, keywords_config_path: str = None):
        """
        Initialize data transformer.

        Args:
            notion_client: Optional Notion client for retrieving existing tags
            keywords_config_path: Path to custom keywords configuration file
        """
        from datetime import datetime, timedelta
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        # Default projected completion is 7 days from now
        self.default_due_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        # Default empty values
        self.empty_value_handling = "default_date"  # options: "default_date", "remove", "null"

        # Default assignee (blank by default, can be set to "Craig Brown" or "babyproject418@gmail.com")
        self.default_assignee = ""

        # Format for date prefix in titles
        self.date_format = "%Y-%m-%d"
        self.add_date_prefix = True  # Whether to add date prefix to titles

        # Store keywords config path
        self.keywords_config_path = keywords_config_path
        
        # Store Notion client
        self.notion_client = notion_client
        
        # Initialize existing tags from Notion
        self.existing_tags = {}
        
        # Load existing tags from Notion if client is available
        if self.notion_client:
            self._load_existing_tags()
    
    def _load_existing_tags(self) -> None:
        """
        Load existing tags from Notion databases and update the keywords.json file.
        """
        if not self.notion_client:
            return
            
        # Load tags for each database type
        database_types = ["tasks", "projects", "todo", "lifelog"]
        
        for db_type in database_types:
            try:
                tags = self.notion_client.get_existing_tags(db_type)
                if tags:
                    self.existing_tags[db_type] = tags
                    
                    # Update keywords.json with new tags
                    from ..utils.keywords_config import KeywordsConfig
                    keywords_config = KeywordsConfig(self.keywords_config_path)
                    keywords_config.update_existing_notion_tags(tags)
                    
            except Exception as e:
                from loguru import logger
                logger.error(f"Error loading existing tags for {db_type}: {e}")
                
    def _get_existing_tags(self, db_type: str = None) -> List[str]:
        """
        Get existing tags for a specific database type or all databases.
        
        Args:
            db_type: Optional database type to filter tags
            
        Returns:
            List of existing tags
        """
        # Get tags from keywords config first
        from ..utils.keywords_config import KeywordsConfig
        keywords_config = KeywordsConfig(self.keywords_config_path)
        all_tags = keywords_config.get_existing_notion_tags()
        
        # Add tags from memory if available
        if db_type and db_type in self.existing_tags:
            all_tags.extend(self.existing_tags[db_type])
        elif not db_type:
            for tags in self.existing_tags.values():
                all_tags.extend(tags)
                
        # Remove duplicates and return
        return sorted(list(set(all_tags)))
            
    def transform(self, extracted_items: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Transform extracted items into Notion-compatible format.

        Args:
            extracted_items: Dictionary with categories of extracted items

        Returns:
            Dictionary with Notion-formatted entries grouped by database
        """
        notion_data = {
            "tasks": [],
            "projects": [],
            "todo": [],
            "lifelog": []
        }

        # Process tasks
        for task in extracted_items.get("tasks", []):
            # Enrich task with transcript details
            enriched_task = self._enrich_transcript_details(task)

            notion_task = self._transform_task(enriched_task)
            notion_data["tasks"].append(notion_task)

            # Create a todo item for each task as well
            notion_todo = self._transform_todo(enriched_task)
            notion_data["todo"].append(notion_todo)

        # Process meetings
        for meeting in extracted_items.get("meetings", []):
            # Enrich meeting with transcript details
            enriched_meeting = self._enrich_transcript_details(meeting)

            notion_task = self._transform_meeting_to_task(enriched_meeting)
            notion_data["tasks"].append(notion_task)

        # Process projects
        for project in extracted_items.get("projects", []):
            # Enrich project with transcript details
            enriched_project = self._enrich_transcript_details(project)

            notion_project = self._transform_project(enriched_project)
            notion_data["projects"].append(notion_project)

        # Process research items
        for research in extracted_items.get("research", []):
            # Enrich research with transcript details
            enriched_research = self._enrich_transcript_details(research)

            notion_task = self._transform_research_to_task(enriched_research)
            notion_data["tasks"].append(notion_task)

        # Process messages
        for message in extracted_items.get("messages", []):
            # Enrich message with transcript details
            enriched_message = self._enrich_transcript_details(message)

            notion_todo = self._transform_message_to_todo(enriched_message)
            notion_data["todo"].append(notion_todo)

        # Create lifelog entries
        lifelog_entry = self._create_lifelog_entry(extracted_items)
        if lifelog_entry:
            notion_data["lifelog"].append(lifelog_entry)

        # Add source transcript information to all entries
        for db_type, entries in notion_data.items():
            for entry in entries:
                if "transcript_id" in entry and "properties" in entry:
                    # Add source transcript ID to all entries in a visible field
                    transcript_id = entry["transcript_id"]
                    if "Source" not in entry["properties"] and transcript_id:
                        entry["properties"]["Source"] = {"rich_text": [{"text": {"content": f"Transcript ID: {transcript_id}"}}]}

        return notion_data
    
    def _generate_enhanced_tags(self, item: Dict[str, Any], item_type: str, transcript_details: Dict[str, Any]) -> List[str]:
        """
        Generate enhanced tags for an item based on its content, type, and existing tags.
        
        Args:
            item: The item dictionary
            item_type: Type of item (task, project, meeting, etc.)
            transcript_details: Transcript details dictionary
            
        Returns:
            List of generated tags
        """
        # Start with any explicit tags
        tags = []
        if "tags" in item:
            if isinstance(item["tags"], list):
                tags.extend(item["tags"])
            elif isinstance(item["tags"], str):
                tags.extend([tag.strip() for tag in item["tags"].split(",")])
                
        # Also check categories for projects
        if item_type == "project" and "categories" in item:
            if isinstance(item["categories"], list):
                tags.extend(item["categories"])
            elif isinstance(item["categories"], str):
                tags.extend([cat.strip() for cat in item["categories"].split(",")])
                
        # Load keywords config
        from ..utils.keywords_config import KeywordsConfig
        keywords_config = KeywordsConfig(self.keywords_config_path)
        
        # Get excluded words
        excluded_words = keywords_config.get_excluded_words()
        
        # Add keywords from transcript details
        if transcript_details and "keywords" in transcript_details:
            for keyword in transcript_details["keywords"]:
                if keyword.lower() not in excluded_words and len(keyword) > 2:
                    clean_keyword = keyword[:20].capitalize()
                    if clean_keyword not in tags:
                        tags.append(clean_keyword)
                        
        # Extract additional tags from content if needed
        if len(tags) < 5 and transcript_details and "content" in transcript_details:
            import re
            from collections import Counter
            
            # Extract all words from content
            content = transcript_details["content"].lower()
            words = re.findall(r'\b\w+\b', content)
            
            # Count frequency of each word
            word_counts = Counter(words)
            
            # Add most common words that aren't in excluded list
            for word, count in word_counts.most_common(20):
                if len(word) > 3 and word not in excluded_words and word not in [t.lower() for t in tags]:
                    tags.append(word.capitalize())
                    if len(tags) >= 5:
                        break
                        
        # Check for any matching existing tags from Notion
        existing_tags = self._get_existing_tags(f"{item_type}s")  # Convert to plural for database type
        for tag in existing_tags:
            if transcript_details and "content" in transcript_details and tag.lower() in transcript_details["content"].lower():
                if tag not in tags:
                    tags.append(tag)
                    
        # Add descriptor tags based on item type
        descriptor_tags = keywords_config.get_descriptor_tags(item_type)
        for tag in descriptor_tags:
            if tag not in tags:
                tags.append(tag)
                if len(tags) >= 5:
                    break
                    
        # Add default category tags if still below 5 tags
        if len(tags) < 5:
            default_tags = []
            if item_type == "task":
                default_tags = ["Task", "Action", "Voice", "Transcript"]
            elif item_type == "project":
                default_tags = ["Project", "Initiative", "Planning", "Voice", "Transcript"]
            elif item_type == "meeting":
                default_tags = ["Meeting", "Discussion", "Event", "Voice", "Transcript"]
            elif item_type == "research":
                default_tags = ["Research", "Analysis", "Investigation", "Voice", "Transcript"]
            else:
                default_tags = ["Voice", "Transcript", item_type.capitalize()]
                
            for tag in default_tags:
                if tag not in tags:
                    tags.append(tag)
                    if len(tags) >= 5:
                        break
                        
        # Add item-specific tags
        if item_type == "task" or item_type == "todo":
            # Add project name as a tag if available
            if item.get("project", "") and item["project"] not in tags:
                tags.append(item["project"])
                
            # Add due date indicator tag
            if item.get("due_date", ""):
                from datetime import datetime
                try:
                    due_date = datetime.strptime(item["due_date"], "%Y-%m-%d")
                    today = datetime.now()
                    days_remaining = (due_date - today).days
                    
                    if days_remaining < 0:
                        date_tag = "Overdue"
                    elif days_remaining == 0:
                        date_tag = "Due Today"
                    elif days_remaining <= 3:
                        date_tag = "Due Soon"
                    else:
                        date_tag = "Future Due Date"
                        
                    if date_tag not in tags:
                        tags.append(date_tag)
                except:
                    pass  # Skip if date parsing fails
                    
        elif item_type == "project":
            # Add URL tag if available
            if "url" in item and item["url"]:
                url_tag = "Has URL"
                if url_tag not in tags:
                    tags.append(url_tag)
            
            # Add project type tag if available
            project_type = None
            if transcript_details and "action_keywords" in transcript_details:
                project_keywords = keywords_config.get_project_category_keywords()
                
                for proj_type, keywords in project_keywords.items():
                    for keyword in keywords:
                        if keyword in [k.lower() for k in transcript_details.get("action_keywords", [])]:
                            project_type = proj_type
                            break
                    if project_type:
                        break
                        
            if project_type and project_type not in tags:
                tags.append(project_type)
                
        # Add priority as a tag for all item types
        priority = item.get("priority", "medium").capitalize()
        priority_tag = f"Priority: {priority}"
        if priority_tag not in tags:
            tags.append(priority_tag)
            
        # Limit to 10 tags
        return tags[:10]
    
    def _transform_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a task item to Notion Tasks database format.

        Args:
            task: Task item dictionary

        Returns:
            Notion-formatted task
        """
        # Get basic title
        raw_title = task.get("title", "Untitled Task")

        # Add date prefix to title if enabled
        if self.add_date_prefix:
            from datetime import datetime
            date_str = task.get("created_date", self.current_date)
            title = f"{date_str} | {raw_title}"
        else:
            title = raw_title

        # Enhance description with transcript context and purpose section
        description_parts = []

        # Create a clear "Purpose" section
        purpose_parts = []
        if task.get("description", ""):
            purpose_parts.append(task["description"])

        # Add purpose statement if not in description
        if not any(keyword in " ".join(purpose_parts).lower() for keyword in ["purpose", "goal", "aim", "objective", "intention"]):
            purpose_parts.append(f"This task is intended to track and complete the work described in this entry.")

        # Add to description with heading
        description_parts.append("## Purpose & Objectives\n" + "\n\n".join(purpose_parts))

        # Add transcript context if available
        context_parts = []
        if task.get("context", ""):
            context_parts.append(task["context"])
        elif task.get("extracted_context", ""):
            context_parts.append(task["extracted_context"])

        # Add context with proper formatting if we have it
        if context_parts:
            description_parts.append(f"## Background & Context\n{' '.join(context_parts)}")

        # Add detailed information section
        details_parts = []

        # Add project-task relationship if available
        if task.get("project", ""):
            details_parts.append(f"**Project**: {task['project']}")

        # Add due date reasoning if available
        if task.get("due_date", ""):
            details_parts.append(f"**Target Completion**: {task['due_date']}")

        # Add dependencies if available
        if task.get("blocked_by", ""):
            blocked_text = task["blocked_by"] if isinstance(task["blocked_by"], str) else ", ".join(task["blocked_by"])
            details_parts.append(f"**Dependencies**: {blocked_text}")

        # Add any additional task details
        if details_parts:
            description_parts.append("## Task Details\n" + "\n".join(details_parts))

        # Add transcript details section
        transcript_details = task.get("transcript_details", {})
        if transcript_details:
            # Add original content excerpt with more context
            if "content" in transcript_details:
                excerpt = transcript_details["content"][:500] + "..." if len(transcript_details["content"]) > 500 else transcript_details["content"]
                description_parts.append(f"## Original Transcript\n{excerpt}")

            # Add keywords found with better formatting
            if "keywords" in transcript_details and transcript_details["keywords"]:
                keywords_str = ", ".join([f"**{kw}**" for kw in transcript_details["keywords"][:15]])
                description_parts.append(f"## Key Topics & Themes\n{keywords_str}")

            # Add importance level with reasoning
            if "importance_level" in transcript_details:
                importance = transcript_details["importance_level"].upper()
                description_parts.append(f"## Priority Assessment\nThis task has been assessed as **{importance} PRIORITY** based on the transcript content and context.")

        # Add original transcript ID reference
        if task.get("transcript_id", ""):
            description_parts.append(f"## Reference\nSource: Transcript ID {task['transcript_id']}")

        # Join all description parts
        description = "\n\n".join(description_parts)

        # Extract or set date fields
        created_date = task.get("created_date", self.current_date)
        due_date = task.get("due_date", self.default_due_date)

        # Determine status - use provided or default to "Not Started"
        status = task.get("status", "Not Started")

        # Determine priority - use provided or default to "Medium"
        priority = task.get("priority", "Medium").capitalize()

        # Default assignee (can be overridden if explicit assignment exists)
        assignee = task.get("assignee", self.default_assignee)

        # Extract blocked by information
        blocked_by = []
        if "blocked_by" in task and task["blocked_by"]:
            if isinstance(task["blocked_by"], list):
                blocked_by = task["blocked_by"]
            else:
                blocked_by = [task["blocked_by"]]
        elif "dependencies" in task and task["dependencies"]:
            if isinstance(task["dependencies"], list):
                blocked_by = task["dependencies"]
            else:
                blocked_by = [task["dependencies"]]

        # Check for blocked info in description or context
        if not blocked_by:
            blocked_keywords = ["blocked by", "depends on", "waiting for", "dependent on", "blocked until"]
            for keyword in blocked_keywords:
                if task.get("description", "") and keyword in task["description"].lower():
                    # Extract simple blocked by info from description
                    start_idx = task["description"].lower().find(keyword)
                    if start_idx != -1:
                        # Extract the next 30 chars after the keyword as potential blocker info
                        end_idx = min(start_idx + len(keyword) + 30, len(task["description"]))
                        blocked_info = task["description"][start_idx:end_idx].strip()
                        blocked_by.append(blocked_info)
                        break

        # Generate enhanced tags for the task
        tags = self._generate_enhanced_tags(task, "task", transcript_details)

        # Define project if not already defined
        project = task.get("project", "")
        if not project and "action_keywords" in transcript_details:
            # Load configurable keywords
            from ..utils.keywords_config import KeywordsConfig
            keywords_config = KeywordsConfig()

            # Try to infer project from keywords using configuration
            project_keywords = keywords_config.get_project_category_keywords()

            for proj, keywords in project_keywords.items():
                for keyword in keywords:
                    if keyword in [k.lower() for k in transcript_details.get("action_keywords", [])]:
                        project = proj
                        break
                if project:
                    break

            # If still no project, default to "General Tasks"
            if not project:
                project = "General Tasks"

        notion_task = {
            "item_id": task.get("item_id"),
            "transcript_id": task.get("transcript_id"),
            "transcript_details": task.get("transcript_details", {}),  # Store full transcript details for comments
            "properties": {
                "Title": {"title": [{"text": {"content": title}}]},
                "Description": {"rich_text": [{"text": {"content": description}}]},
                "Status": {"status": {"name": status}},
                "Priority": {"select": {"name": priority}},
                "Created Date": {"date": {"start": created_date}},
                "Due Date": {"date": {"start": due_date}},
                "Assignee": {"people": []},  # Changed to people type to match Notion schema
                "Project": {"select": {"name": project}}
            }
        }

        # Add estimated completion time if present
        if "estimated_time" in task and task["estimated_time"]:
            notion_task["properties"]["Estimated Time"] = {"rich_text": [{"text": {"content": task["estimated_time"]}}]}

        # Add tags as multi-select
        if tags:
            # Limit to top 10 tags to avoid overwhelming the UI
            tags = tags[:10]
            notion_task["properties"]["Tags"] = {"multi_select": [{"name": tag} for tag in tags]}

        # Add comments for updates if present
        if "updates" in task and task["updates"]:
            updates_text = "\n".join([f"- {update}" for update in task["updates"]])
            notion_task["properties"]["Updates"] = {"rich_text": [{"text": {"content": updates_text}}]}

        # Add blocked by information if present
        if blocked_by:
            blocked_text = ", ".join(blocked_by)
            notion_task["properties"]["Blocked By"] = {"rich_text": [{"text": {"content": blocked_text}}]}

        # Add completion percentage if present
        completion = task.get("completion_percentage", task.get("percent_complete", task.get("progress", 0)))
        if completion:
            try:
                # Convert to number if it's a string like "50%"
                if isinstance(completion, str):
                    completion = int(completion.replace("%", ""))
                notion_task["properties"]["Completion"] = {"number": completion}
            except:
                pass  # Skip if we can't parse a valid number

        return notion_task
    
    def _transform_todo(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a task item to Notion Todo database format.

        Args:
            task: Task item dictionary

        Returns:
            Notion-formatted todo
        """
        # Get basic title
        raw_title = task.get("title", "Untitled Todo")

        # Add date prefix to title if enabled
        if self.add_date_prefix:
            from datetime import datetime
            date_str = task.get("created_date", self.current_date)
            title = f"{date_str} | {raw_title}"
        else:
            title = raw_title

        # Build notes from description and context
        notes_parts = []

        # Add base description
        if task.get("description", ""):
            notes_parts.append(task["description"])

        # Add transcript context if available
        if task.get("context", ""):
            notes_parts.append(f"Context: {task['context']}")
        elif task.get("extracted_context", ""):
            notes_parts.append(f"Context: {task['extracted_context']}")

        # Add transcript details section
        transcript_details = task.get("transcript_details", {})
        if transcript_details:
            # Add original content excerpt
            if "content" in transcript_details:
                excerpt = transcript_details["content"][:300] + "..." if len(transcript_details["content"]) > 300 else transcript_details["content"]
                notes_parts.append(f"Transcript Content:\n{excerpt}")

            # Add keywords found
            if "keywords" in transcript_details and transcript_details["keywords"]:
                keywords_str = ", ".join(transcript_details["keywords"])
                notes_parts.append(f"Keywords: {keywords_str}")

            # Add importance level
            if "importance_level" in transcript_details:
                notes_parts.append(f"Importance Level: {transcript_details['importance_level']}")

        # Add original transcript reference
        if task.get("transcript_id", ""):
            notes_parts.append(f"Source: Transcript {task['transcript_id']}")

        # Join all notes parts
        notes = "\n\n".join(notes_parts)

        # Determine status - use provided or default to "Not Started"
        status = False  # Checkbox for todo completion status
        if task.get("status", "").lower() in ["done", "completed", "finished"]:
            status = True

        # Determine priority - use provided or default to "Medium"
        priority_map = {"high": "High", "medium": "Medium", "low": "Low"}
        priority = priority_map.get(task.get("priority", "medium").lower(), "Medium")

        # Extract or set date fields
        created_date = task.get("created_date", self.current_date)
        due_date = task.get("due_date", self.default_due_date)

        # Default assignee (can be overridden if explicit assignment exists)
        assignee = task.get("assignee", self.default_assignee)

        # Generate enhanced tags for the todo
        tags = self._generate_enhanced_tags(task, "todo", transcript_details)

        # Extract completion percentage if present
        completion = 100 if status else 0  # Default based on checkbox status

        # Define project if not already defined
        project = task.get("project", "")
        if not project and transcript_details and "action_keywords" in transcript_details:
            # Load configurable keywords
            from ..utils.keywords_config import KeywordsConfig
            keywords_config = KeywordsConfig()

            # Try to infer project from keywords using configuration
            project_keywords = keywords_config.get_project_category_keywords()

            for proj, keywords in project_keywords.items():
                for keyword in keywords:
                    if keyword in [k.lower() for k in transcript_details.get("action_keywords", [])]:
                        project = proj
                        break
                if project:
                    break

            # If still no project, default to "General Tasks"
            if not project:
                project = "General Tasks"

        notion_todo = {
            "item_id": task.get("item_id"),
            "transcript_id": task.get("transcript_id"),
            "transcript_details": task.get("transcript_details", {}),  # Store full transcript details for comments
            "properties": {
                "Title": {"title": [{"text": {"content": title}}]},
                "Status": {"checkbox": status},
                "Priority": {"select": {"name": priority}},
                "Created Date": {"date": {"start": created_date}},
                "Due": {"date": {"start": due_date}},
                "Notes": {"rich_text": [{"text": {"content": notes}}]},
                "Assignee": {"people": []},  # Changed to people type to match Notion schema
                "Progress": {"number": completion}
            }
        }

        # Add project if defined
        if project:
            notion_todo["properties"]["Project"] = {"select": {"name": project}}

        # Add tags/keywords if present
        if tags:
            # Limit to top 10 tags to avoid overwhelming the UI
            tags = tags[:10]
            notion_todo["properties"]["Tags"] = {"multi_select": [{"name": tag} for tag in tags]}

        # Add estimated completion time if present
        if "estimated_time" in task and task["estimated_time"]:
            notion_todo["properties"]["Estimated Time"] = {"rich_text": [{"text": {"content": task["estimated_time"]}}]}

        # Add updates if present
        if "updates" in task and task["updates"]:
            updates_text = "\n".join([f"- {update}" for update in task["updates"]])
            notion_todo["properties"]["Updates"] = {"rich_text": [{"text": {"content": updates_text}}]}

        return notion_todo
    
    def _transform_meeting_to_task(self, meeting: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a meeting item to Notion Tasks database format.

        Args:
            meeting: Meeting item dictionary

        Returns:
            Notion-formatted task
        """
        # Get basic title
        raw_title = f"Meeting: {meeting.get('title', 'Untitled Meeting')}"

        # Add date prefix to title if enabled
        if self.add_date_prefix:
            from datetime import datetime
            date_str = meeting.get("created_date", self.current_date)
            title = f"{date_str} | {raw_title}"
        else:
            title = raw_title

        # Build enhanced description with meeting details
        description_parts = []

        # Add base description
        if meeting.get("description", ""):
            description_parts.append(meeting["description"])

        # Add agenda
        if "agenda" in meeting and meeting["agenda"]:
            description_parts.append(f"Agenda: {meeting['agenda']}")

        # Add participants
        if "participants" in meeting and meeting["participants"]:
            if isinstance(meeting["participants"], list):
                participants_text = ", ".join(meeting["participants"])
            else:
                participants_text = meeting["participants"]
            description_parts.append(f"Participants: {participants_text}")

        # Add location
        if "location" in meeting and meeting["location"]:
            description_parts.append(f"Location: {meeting['location']}")

        # Add transcript context if available
        if meeting.get("context", ""):
            description_parts.append(f"Context: {meeting['context']}")
        elif meeting.get("extracted_context", ""):
            description_parts.append(f"Context: {meeting['extracted_context']}")

        # Add original transcript reference
        if meeting.get("transcript_id", ""):
            description_parts.append(f"Source: Transcript {meeting['transcript_id']}")

        # Join all description parts
        description = "\n\n".join(description_parts)

        # Extract or set date fields
        created_date = meeting.get("created_date", self.current_date)

        # Determine priority if present, otherwise default to Medium
        priority = meeting.get("priority", "Medium").capitalize()

        notion_task = {
            "item_id": meeting.get("item_id"),
            "transcript_id": meeting.get("transcript_id"),
            "transcript_details": meeting.get("transcript_details", {}),  # Store full transcript details for comments
            "properties": {
                "Title": {"title": [{"text": {"content": title}}]},
                "Description": {"rich_text": [{"text": {"content": description}}]},
                "Status": {"status": {"name": "Not Started"}},
                "Type": {"select": {"name": "Meeting"}},
                "Priority": {"select": {"name": priority}},
                "Created Date": {"date": {"start": created_date}}
            }
        }

        # Add scheduled date/time if present
        scheduled_date = None

        if "date" in meeting and meeting["date"]:
            scheduled_date = meeting["date"]

            date_value = {"start": scheduled_date}

            # Add time if present
            if "time" in meeting and meeting["time"]:
                date_value["start"] += f"T{meeting['time']}"

            notion_task["properties"]["Due Date"] = {"date": date_value}
            notion_task["properties"]["Meeting Date"] = {"date": date_value}
        else:
            # Default to one week from now
            from datetime import datetime, timedelta
            default_meeting_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            notion_task["properties"]["Due Date"] = {"date": {"start": default_meeting_date}}
            notion_task["properties"]["Meeting Date"] = {"date": {"start": default_meeting_date}}

        # Add duration if present
        if "duration" in meeting and meeting["duration"]:
            notion_task["properties"]["Duration"] = {"rich_text": [{"text": {"content": meeting["duration"]}}]}

        # Add recurrence if present
        if "recurrence" in meeting and meeting["recurrence"]:
            notion_task["properties"]["Recurrence"] = {"rich_text": [{"text": {"content": meeting["recurrence"]}}]}

        # Add meeting notes if present
        if "notes" in meeting and meeting["notes"]:
            notion_task["properties"]["Meeting Notes"] = {"rich_text": [{"text": {"content": meeting["notes"]}}]}

        return notion_task
    
    def _transform_project(self, project: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a project item to Notion Projects database format.

        Args:
            project: Project item dictionary

        Returns:
            Notion-formatted project
        """
        # Get basic title
        raw_title = project.get("name", "Untitled Project")

        # Add date prefix to title if enabled
        if self.add_date_prefix:
            from datetime import datetime
            date_str = project.get("created_date", self.current_date)
            title = f"{date_str} | {raw_title}"
        else:
            title = raw_title

        # Build enhanced description with better structure
        description_parts = []

        # Project Purpose and Overview section
        overview_parts = []
        if project.get("description", ""):
            overview_parts.append(project["description"])
        else:
            overview_parts.append("This project was created based on transcript content and detected project references.")

        description_parts.append("## Project Overview\n" + "\n\n".join(overview_parts))

        # Project Goals and Objectives section
        goal_parts = []
        if project.get("goals", ""):
            if isinstance(project["goals"], list):
                goals_text = "\n".join([f"- {goal}" for goal in project["goals"]])
                goal_parts.append(f"{goals_text}")
            else:
                goal_parts.append(f"{project['goals']}")

        # Make sure we have some goals, even if very basic
        if not goal_parts:
            goal_parts.append("- Successfully implement and deliver the project as described")
            goal_parts.append("- Track progress and coordinate efforts related to this project")

        description_parts.append("## Goals & Objectives\n" + "\n".join(goal_parts))

        # Project Scope section
        scope_parts = []
        if project.get("scope", ""):
            scope_parts.append(project["scope"])

        # Add a timeline scope if we have timeline data
        if "timeline" in project and project["timeline"]:
            if isinstance(project["timeline"], dict):
                if "start" in project["timeline"] and "end" in project["timeline"]:
                    scope_parts.append(f"**Timeline**: {project['timeline']['start']} to {project['timeline']['end']}")
            elif isinstance(project["timeline"], str):
                scope_parts.append(f"**Timeline**: {project['timeline']}")

        if scope_parts:
            description_parts.append("## Project Scope\n" + "\n\n".join(scope_parts))

        # Context and Background
        context_parts = []
        if project.get("context", ""):
            context_parts.append(project["context"])
        elif project.get("extracted_context", ""):
            context_parts.append(project["extracted_context"])

        if context_parts:
            description_parts.append("## Background & Context\n" + "\n\n".join(context_parts))

        # Team and Stakeholders
        stakeholder_parts = []
        if "team" in project and project["team"]:
            if isinstance(project["team"], list):
                team_text = ", ".join(project["team"])
                stakeholder_parts.append(f"**Team Members**: {team_text}")
            else:
                stakeholder_parts.append(f"**Team Members**: {project['team']}")

        # Add owner info if available
        if project.get("owner", "") or project.get("manager", ""):
            owner = project.get("owner", project.get("manager", ""))
            if owner:
                stakeholder_parts.append(f"**Project Owner**: {owner}")

        if stakeholder_parts:
            description_parts.append("## Team & Stakeholders\n" + "\n".join(stakeholder_parts))

        # Dependencies and Relationships
        dependency_parts = []
        if "dependencies" in project or "blocked_by" in project:
            deps = []
            if "dependencies" in project and project["dependencies"]:
                if isinstance(project["dependencies"], list):
                    deps.extend(project["dependencies"])
                else:
                    deps.append(project["dependencies"])

            if "blocked_by" in project and project["blocked_by"]:
                if isinstance(project["blocked_by"], list):
                    deps.extend(project["blocked_by"])
                else:
                    deps.append(project["blocked_by"])

            if deps:
                dependency_parts.append("**Dependencies**:")
                for dep in deps:
                    dependency_parts.append(f"- {dep}")

        if dependency_parts:
            description_parts.append("## Dependencies & Relationships\n" + "\n".join(dependency_parts))

        # Transcript Information section
        transcript_details = project.get("transcript_details", {})
        if transcript_details:
            # Add original content excerpt with more context
            if "content" in transcript_details:
                excerpt = transcript_details["content"][:500] + "..." if len(transcript_details["content"]) > 500 else transcript_details["content"]
                description_parts.append(f"## Original Transcript\n{excerpt}")

            # Add keywords with better formatting
            if "keywords" in transcript_details and transcript_details["keywords"]:
                keywords_str = ", ".join([f"**{kw}**" for kw in transcript_details["keywords"][:15]])
                description_parts.append(f"## Key Topics & Themes\n{keywords_str}")

            # Add importance level with reasoning
            if "importance_level" in transcript_details:
                importance = transcript_details["importance_level"].upper()
                description_parts.append(f"## Priority Assessment\nThis project has been assessed as **{importance} PRIORITY** based on the transcript content and context.")

        # Add original transcript reference
        if project.get("transcript_id", ""):
            description_parts.append(f"## Reference\nSource: Transcript ID {project['transcript_id']}")

        # Join all description parts
        description = "\n\n".join(description_parts)

        # Extract status and priority
        status = project.get("status", "Planning")
        priority = project.get("priority", "Medium").capitalize()

        # Extract date fields
        created_date = project.get("created_date", self.current_date)

        # Default owner/manager (can be overridden if explicit assignment exists)
        owner = project.get("owner", project.get("manager", self.default_assignee))

        # Generate enhanced tags for the project
        tags = self._generate_enhanced_tags(project, "project", transcript_details)

        # Determine completion percentage
        completion = project.get("completion_percentage", project.get("percent_complete", project.get("progress", 0)))
        if isinstance(completion, str):
            try:
                completion = int(completion.replace("%", ""))
            except:
                completion = 0

        notion_project = {
            "item_id": project.get("item_id"),
            "transcript_id": project.get("transcript_id"),
            "transcript_details": project.get("transcript_details", {}),  # Store transcript details for comments
            "properties": {
                "Name": {"title": [{"text": {"content": title}}]},
                "Description": {"rich_text": [{"text": {"content": description}}]},
                "Status": {"select": {"name": status}},
                "Priority": {"select": {"name": priority}},
                "Created Date": {"date": {"start": created_date}},
                "Owner": {"people": []},  # Changed to people type to match Notion schema
                "Completion": {"number": completion}
            }
        }

        # Add timeline if present
        if "timeline" in project and project["timeline"]:
            if isinstance(project["timeline"], dict) and "start" in project["timeline"] and "end" in project["timeline"]:
                notion_project["properties"]["Timeline"] = {
                    "date": {
                        "start": project["timeline"]["start"],
                        "end": project["timeline"]["end"]
                    }
                }
            elif isinstance(project["timeline"], str):
                notion_project["properties"]["Timeline Description"] = {
                    "rich_text": [{"text": {"content": project["timeline"]}}]
                }
        else:
            # Add default timeline (3 months by default)
            from datetime import datetime, timedelta
            start_date = self.current_date
            end_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
            notion_project["properties"]["Timeline"] = {
                "date": {
                    "start": start_date,
                    "end": end_date
                }
            }

        # Add team/stakeholders if present
        if "team" in project and project["team"]:
            if isinstance(project["team"], list):
                team_text = ", ".join(project["team"])
            else:
                team_text = project["team"]
            notion_project["properties"]["Team"] = {"rich_text": [{"text": {"content": team_text}}]}

        # Add tags as multi-select if we have any
        if tags:
            # Limit to top 10 tags to avoid overwhelming the UI
            tags = tags[:10]
            notion_project["properties"]["Tags"] = {"multi_select": [{"name": tag} for tag in tags]}

        # Add updates if present
        if "updates" in project and project["updates"]:
            updates_text = "\n".join([f"- {update}" for update in project["updates"]])
            notion_project["properties"]["Updates"] = {"rich_text": [{"text": {"content": updates_text}}]}

        # Add budget if present
        if "budget" in project and project["budget"]:
            notion_project["properties"]["Budget"] = {"rich_text": [{"text": {"content": str(project["budget"])}}]}

        # Add dependencies or blocked by information if present
        dependencies = []
        if "dependencies" in project and project["dependencies"]:
            if isinstance(project["dependencies"], list):
                dependencies.extend(project["dependencies"])
            else:
                dependencies.append(project["dependencies"])

        if "blocked_by" in project and project["blocked_by"]:
            if isinstance(project["blocked_by"], list):
                dependencies.extend(project["blocked_by"])
            else:
                dependencies.append(project["blocked_by"])

        if dependencies:
            dependencies_text = ", ".join(dependencies)
            notion_project["properties"]["Dependencies"] = {"rich_text": [{"text": {"content": dependencies_text}}]}

        return notion_project
    
    def _transform_research_to_task(self, research: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a research item to Notion Tasks database format.

        Args:
            research: Research item dictionary

        Returns:
            Notion-formatted task
        """
        # Get basic title
        raw_title = f"Research: {research.get('topic', 'Untitled Research')}"

        # Add date prefix to title if enabled
        if self.add_date_prefix:
            from datetime import datetime
            date_str = research.get("created_date", self.current_date)
            title = f"{date_str} | {raw_title}"
        else:
            title = raw_title

        # Build enhanced description
        description_parts = []

        # Add base description
        if research.get("description", ""):
            description_parts.append(research["description"])

        # Add research details
        if research.get("questions", ""):
            if isinstance(research["questions"], list):
                questions_text = "\n".join([f"- {q}" for q in research["questions"]])
                description_parts.append(f"Questions:\n{questions_text}")
            else:
                description_parts.append(f"Questions: {research['questions']}")

        # Add sources if present
        if research.get("sources", ""):
            if isinstance(research["sources"], list):
                sources_text = "\n".join([f"- {source}" for source in research["sources"]])
                description_parts.append(f"Sources:\n{sources_text}")
            else:
                description_parts.append(f"Sources: {research['sources']}")

        # Add transcript context if available
        if research.get("context", ""):
            description_parts.append(f"Context: {research['context']}")
        elif research.get("extracted_context", ""):
            description_parts.append(f"Context: {research['extracted_context']}")

        # Add original transcript reference
        if research.get("transcript_id", ""):
            description_parts.append(f"Source: Transcript {research['transcript_id']}")

        # Join all description parts
        description = "\n\n".join(description_parts)

        # Extract or set date fields
        created_date = research.get("created_date", self.current_date)
        due_date = research.get("due_date", self.default_due_date)

        # Determine status and priority
        status = research.get("status", "Not Started")
        priority = research.get("priority", "Medium").capitalize()

        notion_task = {
            "item_id": research.get("item_id"),
            "transcript_id": research.get("transcript_id"),
            "transcript_details": research.get("transcript_details", {}),  # Store full transcript details for comments
            "properties": {
                "Title": {"title": [{"text": {"content": title}}]},
                "Description": {"rich_text": [{"text": {"content": description}}]},
                "Status": {"status": {"name": status}},
                "Type": {"select": {"name": "Research"}},
                "Priority": {"select": {"name": priority}},
                "Created Date": {"date": {"start": created_date}},
                "Due Date": {"date": {"start": due_date}}
            }
        }

        # Add project if present
        if "project" in research and research["project"]:
            notion_task["properties"]["Project"] = {"select": {"name": research["project"]}}

        # Add tags/keywords if present
        if "tags" in research and research["tags"]:
            if isinstance(research["tags"], list):
                notion_task["properties"]["Tags"] = {"multi_select": [{"name": tag} for tag in research["tags"]]}
            elif isinstance(research["tags"], str):
                notion_task["properties"]["Tags"] = {"multi_select": [{"name": tag.strip()} for tag in research["tags"].split(",")]}

        # Add estimated completion time if present
        if "estimated_time" in research and research["estimated_time"]:
            notion_task["properties"]["Estimated Time"] = {"rich_text": [{"text": {"content": research["estimated_time"]}}]}

        return notion_task
    
    def _transform_message_to_todo(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a message item to Notion Todo database format.

        Args:
            message: Message item dictionary

        Returns:
            Notion-formatted todo
        """
        recipient = message.get("recipient", "")
        content = message.get("content", "")
        raw_title = f"Message to {recipient}: {content[:30]}..." if len(content) > 30 else f"Message to {recipient}: {content}"

        # Add date prefix to title if enabled
        if self.add_date_prefix:
            from datetime import datetime
            date_str = message.get("created_date", self.current_date)
            title = f"{date_str} | {raw_title}"
        else:
            title = raw_title

        # Build enhanced notes
        notes_parts = []

        # Add full message content
        notes_parts.append(f"Message Content: {content}")

        # Add additional details if present
        if message.get("medium", ""):
            notes_parts.append(f"Medium: {message['medium']}")

        if message.get("urgency", ""):
            notes_parts.append(f"Urgency: {message['urgency']}")

        # Add transcript context if available
        if message.get("context", ""):
            notes_parts.append(f"Context: {message['context']}")
        elif message.get("extracted_context", ""):
            notes_parts.append(f"Context: {message['extracted_context']}")

        # Add original transcript reference
        if message.get("transcript_id", ""):
            notes_parts.append(f"Source: Transcript {message['transcript_id']}")

        # Join all notes parts
        notes = "\n\n".join(notes_parts)

        # Extract or set date fields
        created_date = message.get("created_date", self.current_date)
        due_date = message.get("due_date", self.current_date)  # Messages usually need to be sent today

        # Determine status - use provided or default to Not Sent
        status = False  # Not sent yet (checkbox)
        if message.get("status", "").lower() in ["sent", "completed", "done"]:
            status = True

        # Determine priority based on urgency or default to Medium
        if message.get("urgency", "").lower() in ["high", "urgent", "important"]:
            priority = "High"
        elif message.get("urgency", "").lower() in ["low", "whenever"]:
            priority = "Low"
        else:
            priority = "Medium"

        notion_todo = {
            "item_id": message.get("item_id"),
            "transcript_id": message.get("transcript_id"),
            "transcript_details": message.get("transcript_details", {}),  # Store full transcript details for comments
            "properties": {
                "Title": {"title": [{"text": {"content": title}}]},
                "Status": {"checkbox": status},
                "Type": {"select": {"name": "Message"}},
                "Priority": {"select": {"name": priority}},
                "Created Date": {"date": {"start": created_date}},
                "Due": {"date": {"start": due_date}},
                "Notes": {"rich_text": [{"text": {"content": notes}}]},
                "Recipient": {"rich_text": [{"text": {"content": recipient}}]}
            }
        }

        # Add communication medium if present (call, email, text, etc.)
        if "medium" in message and message["medium"]:
            notion_todo["properties"]["Medium"] = {"select": {"name": message["medium"].capitalize()}}

        # Add follow-up date if present
        if "follow_up_date" in message and message["follow_up_date"]:
            notion_todo["properties"]["Follow-up Date"] = {"date": {"start": message["follow_up_date"]}}

        # Add tags if present
        if "tags" in message and message["tags"]:
            if isinstance(message["tags"], list):
                notion_todo["properties"]["Tags"] = {"multi_select": [{"name": tag} for tag in message["tags"]]}
            elif isinstance(message["tags"], str):
                notion_todo["properties"]["Tags"] = {"multi_select": [{"name": tag.strip()} for tag in message["tags"].split(",")]}

        return notion_todo
    
    def _create_lifelog_entry(self, extracted_items: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Create a lifelog entry from all extracted items.

        Args:
            extracted_items: Dictionary with all extracted items

        Returns:
            Notion-formatted lifelog entry
        """
        # Count items in each category
        counts = {
            "tasks": len(extracted_items.get("tasks", [])),
            "meetings": len(extracted_items.get("meetings", [])),
            "projects": len(extracted_items.get("projects", [])),
            "research": len(extracted_items.get("research", [])),
            "messages": len(extracted_items.get("messages", []))
        }

        # Only create entry if we have any items
        total_items = sum(counts.values())
        if total_items == 0:
            return None

        # Create entry title based on counts
        title_parts = []
        for category, count in counts.items():
            if count > 0:
                title_parts.append(f"{count} {category}")

        title = "Processed: " + ", ".join(title_parts)

        # Create enhanced notes with detailed summary
        notes_parts = []

        # Overall summary
        notes_parts.append(f"Processed {total_items} total items on {self._get_today_date()}:")

        # Category counts
        category_summary = []
        for category, count in counts.items():
            if count > 0:
                category_summary.append(f"- {count} {category}")
        notes_parts.append("\n".join(category_summary))

        # Add details about each category
        # Tasks
        if counts["tasks"] > 0:
            task_summary = ["", "## Tasks"]
            for task in extracted_items.get("tasks", []):
                task_title = task.get("title", "Untitled Task")
                priority = task.get("priority", "Medium").capitalize()
                task_summary.append(f"- {task_title} (Priority: {priority})")
            notes_parts.append("\n".join(task_summary))

        # Meetings
        if counts["meetings"] > 0:
            meeting_summary = ["", "## Meetings"]
            for meeting in extracted_items.get("meetings", []):
                meeting_title = meeting.get("title", "Untitled Meeting")
                date_info = meeting.get("date", "No date specified")
                meeting_summary.append(f"- {meeting_title} (Date: {date_info})")
            notes_parts.append("\n".join(meeting_summary))

        # Projects
        if counts["projects"] > 0:
            project_summary = ["", "## Projects"]
            for project in extracted_items.get("projects", []):
                project_name = project.get("name", "Untitled Project")
                status = project.get("status", "Planning")
                project_summary.append(f"- {project_name} (Status: {status})")
            notes_parts.append("\n".join(project_summary))

        # Research items
        if counts["research"] > 0:
            research_summary = ["", "## Research"]
            for research in extracted_items.get("research", []):
                topic = research.get("topic", "Untitled Research")
                research_summary.append(f"- {topic}")
            notes_parts.append("\n".join(research_summary))

        # Messages
        if counts["messages"] > 0:
            message_summary = ["", "## Messages"]
            for message in extracted_items.get("messages", []):
                recipient = message.get("recipient", "")
                content_preview = message.get("content", "")[:50] + "..." if len(message.get("content", "")) > 50 else message.get("content", "")
                message_summary.append(f"- To {recipient}: {content_preview}")
            notes_parts.append("\n".join(message_summary))

        # Add transcript sources if available
        transcript_ids = set()
        for category, items in extracted_items.items():
            for item in items:
                if "transcript_id" in item and item["transcript_id"]:
                    transcript_ids.add(item["transcript_id"])

        if transcript_ids:
            transcript_part = ["", "## Source Transcripts"]
            for transcript_id in sorted(transcript_ids):
                transcript_part.append(f"- Transcript ID: {transcript_id}")
            notes_parts.append("\n".join(transcript_part))

        # Join all notes parts
        detailed_notes = "\n".join(notes_parts)

        # Create mood based on items
        mood = "Productive"  # Default mood for entries with tasks
        if counts["projects"] > 0:
            mood = "Creative"
        elif counts["research"] > 0:
            mood = "Curious"
        elif counts["meetings"] > counts["tasks"]:
            mood = "Collaborative"

        notion_entry = {
            "properties": {
                "Entry": {"title": [{"text": {"content": title}}]},
                "Date": {"date": {"start": self._get_today_date()}},
                "Notes": {"rich_text": [{"text": {"content": detailed_notes}}]},
                "Category": {"select": {"name": "Productivity"}},
                "Mood": {"select": {"name": mood}},
                "Item Count": {"number": total_items}
            }
        }

        # Add tags for each category that has items
        tags = []
        for category, count in counts.items():
            if count > 0:
                tags.append(category.capitalize())

        if tags:
            notion_entry["properties"]["Tags"] = {"multi_select": [{"name": tag} for tag in tags]}

        return notion_entry
    
    def _get_today_date(self) -> str:
        """
        Get today's date in ISO format.

        Returns:
            ISO format date string (YYYY-MM-DD)
        """
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d")

    def _ensure_valid_dates(self, item: Dict[str, Any]) -> None:
        """
        Ensure all date fields in an item are valid ISO format.

        Args:
            item: Dictionary with item details
        """
        from datetime import datetime

        # Date fields to check
        date_fields = ["due_date", "created_date", "timeline", "date", "follow_up_date", "meeting_date"]

        # Validate each field
        for field in date_fields:
            if field in item and item[field] is not None:
                # Check if empty
                if item[field] == "":
                    if self.empty_value_handling == "default_date":
                        if field == "due_date":
                            item[field] = self.default_due_date
                        else:
                            item[field] = self.current_date
                    elif self.empty_value_handling == "remove":
                        del item[field]
                    else:  # "null"
                        item[field] = None

                # Check for special date object formats
                elif isinstance(item[field], dict):
                    if "start" in item[field]:
                        if not item[field]["start"] or item[field]["start"] == "":
                            item[field]["start"] = self.current_date
                    if "end" in item[field]:
                        if not item[field]["end"] or item[field]["end"] == "":
                            if self.empty_value_handling != "null":
                                # Default end date is 30 days from start
                                try:
                                    from datetime import datetime, timedelta
                                    start_date = datetime.strptime(item[field]["start"], "%Y-%m-%d")
                                    item[field]["end"] = (start_date + timedelta(days=30)).strftime("%Y-%m-%d")
                                except:
                                    del item[field]["end"]
                            else:
                                del item[field]["end"]

        # Also check in properties directly if this is already a Notion-formatted item
        if "properties" in item:
            for prop_name, prop_value in item["properties"].items():
                if isinstance(prop_value, dict) and "date" in prop_value:
                    date_value = prop_value["date"]

                    # Skip if None
                    if date_value is None:
                        continue

                    # Handle start date
                    if isinstance(date_value, dict) and "start" in date_value:
                        if not date_value["start"] or date_value["start"] == "":
                            date_value["start"] = self.current_date

                    # Handle end date
                    if isinstance(date_value, dict) and "end" in date_value:
                        if not date_value["end"] or date_value["end"] == "":
                            date_value["end"] = None  # Remove end date

    def _enrich_transcript_details(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich an item with additional transcript details for better Notion integration.

        Args:
            item: Dictionary with item details

        Returns:
            Updated item with enriched transcript details
        """
        # Skip if no transcript ID
        if "transcript_id" not in item:
            return item

        # Create a copy to avoid modifying the original
        enriched_item = item.copy()

        # Ensure there's a transcript_details dictionary
        if "transcript_details" not in enriched_item:
            enriched_item["transcript_details"] = {
                "content": "",
                "created_at": self.current_date
            }

        # Add contextual information about the extraction
        if "context" not in enriched_item["transcript_details"] and "context" in enriched_item:
            enriched_item["transcript_details"]["context"] = enriched_item["context"]

        # Add creation date
        if "created_date" in enriched_item:
            enriched_item["transcript_details"]["created_at"] = enriched_item["created_date"]
        else:
            # Add creation date as of today if not present
            enriched_item["created_date"] = self.current_date
            enriched_item["transcript_details"]["created_at"] = self.current_date

        # Add source reference
        transcript_id = enriched_item.get("transcript_id", "")
        if transcript_id:
            enriched_item["transcript_details"]["source_reference"] = f"Transcript ID: {transcript_id}"

        # Add extraction metadata
        enriched_item["transcript_details"]["extraction_date"] = self.current_date
        enriched_item["transcript_details"]["extraction_method"] = "Limitless Lifelog Processor"

        # Validate all date fields to ensure they are ISO format
        self._ensure_valid_dates(enriched_item)

        return enriched_item