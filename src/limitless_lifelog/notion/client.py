"""
Notion API client for Limitless Lifelog.
"""

import os
import time
from typing import Dict, List, Any, Optional
from loguru import logger

class NotionClient:
    """
    Client for interacting with Notion API.
    
    Handles database operations for tasks, projects, todos, and lifelog entries.
    """
    
    def __init__(self, api_key: str, database_ids: Dict[str, str]):
        """
        Initialize Notion client.
        
        Args:
            api_key: Notion API key
            database_ids: Dictionary mapping database types to IDs
        """
        self.api_key = api_key
        self.database_ids = database_ids
        
        # Import Notion client library lazily to avoid startup issues
        # if the environment doesn't have the package installed
        try:
            from notion_client import Client
            self.notion = Client(auth=api_key)
        except (ImportError, Exception) as e:
            logger.error(f"Error initializing Notion client: {e}")
            self.notion = None
    
    def update_databases(self, notion_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
        """
        Update Notion databases with formatted data.
        
        Args:
            notion_data: Dictionary with database types and entries
            
        Returns:
            Dictionary with counts of created/updated items
        """
        if not self.api_key or not self.notion:
            logger.error("Notion API client not properly initialized")
            return {"error": "Notion client not initialized"}
        
        results = {
            "created": 0,
            "updated": 0,
            "failed": 0
        }
        
        # Process each database type
        for db_type, entries in notion_data.items():
            if not entries:
                continue

            db_id = self.database_ids.get(db_type)
            if not db_id:
                logger.warning(f"No database ID provided for {db_type}")
                continue

            logger.info(f"Processing {len(entries)} entries for {db_type} database")

            # First, fetch database schema to determine property mapping
            try:
                db_schema = self.notion.databases.retrieve(database_id=db_id)
                db_properties = db_schema.get("properties", {})
                logger.debug(f"Database {db_type} has properties: {list(db_properties.keys())}")
            except Exception as e:
                logger.error(f"Error retrieving database schema for {db_type}: {e}")
                continue

            for entry in entries:
                try:
                    # Enrich properties with transcript summary and context
                    properties = entry.get("properties", {}).copy()

                    # Add transcript content to the description/notes field if available
                    if "transcript_details" in entry and entry["transcript_details"]:
                        details = entry["transcript_details"]

                        # Select the appropriate description field based on database type
                        description_field = "Description"
                        if db_type == "todo":
                            description_field = "Notes"
                        elif db_type == "lifelog":
                            description_field = "Notes"

                        # If there's an existing description, enhance it
                        if description_field in properties:
                            existing_text = ""
                            if "rich_text" in properties[description_field]:
                                if properties[description_field]["rich_text"] and "content" in properties[description_field]["rich_text"][0]["text"]:
                                    existing_text = properties[description_field]["rich_text"][0]["text"]["content"]

                            # Prepare to add transcript content and metadata - make it more prominent
                            transcript_section = "\n\n# Transcript Details"

                            # Always add transcript ID as a reference
                            transcript_id = entry.get("transcript_id", "")
                            if transcript_id:
                                transcript_section += f"\n\n## Source\nTranscript ID: {transcript_id}"

                            # Add creation date if available
                            if "created_at" in details and details["created_at"]:
                                transcript_section += f"\n\n**Recording Date**: {details['created_at']}"

                            # Add transcript content - making it more prominent with longer excerpt
                            if "content" in details and details["content"]:
                                excerpt = details["content"][:1000] + "..." if len(details["content"]) > 1000 else details["content"]
                                transcript_section += f"\n\n## Full Transcript\n{excerpt}"

                            # Add context if available - moved higher up for importance
                            if "context" in details and details["context"]:
                                transcript_section += f"\n\n## Context\n{details['context']}"

                            # Add extracted content for key information
                            key_info_parts = []

                            # Add keywords with better formatting
                            if "keywords" in details and details["keywords"]:
                                keywords_str = ", ".join([f"**{kw}**" for kw in details["keywords"][:15]])
                                key_info_parts.append(f"**Keywords**: {keywords_str}")

                            # Add importance level
                            if "importance_level" in details and details["importance_level"]:
                                importance = details["importance_level"].upper()
                                key_info_parts.append(f"**Importance**: {importance}")

                            # Add action keywords
                            if "action_keywords" in details and details["action_keywords"]:
                                action_kw_str = ", ".join([f"**{kw}**" for kw in details["action_keywords"][:10]])
                                key_info_parts.append(f"**Action Keywords**: {action_kw_str}")

                            # Add priority indicators if available
                            if "priority_indicators" in details and details["priority_indicators"]:
                                priority_keywords = [f"**{indicator['keyword']}** ({indicator['priority']})"
                                                   for indicator in details["priority_indicators"]]
                                key_info_parts.append(f"**Priority Indicators**: {', '.join(priority_keywords)}")

                            # Add status indicators if available
                            if "status_indicators" in details and details["status_indicators"]:
                                status_keywords = [f"**{indicator['keyword']}** ({indicator['status']})"
                                                 for indicator in details["status_indicators"]]
                                key_info_parts.append(f"**Status Indicators**: {', '.join(status_keywords)}")

                            # Add date indicators if available
                            if "date_indicators" in details and details["date_indicators"]:
                                date_info = [f"**{indicator['date']}**: {indicator['text']}"
                                           for indicator in details["date_indicators"]]
                                key_info_parts.append(f"**Date References**:\n- " + "\n- ".join(date_info))

                            # Add extracted info section
                            if key_info_parts:
                                transcript_section += f"\n\n## Extracted Information\n" + "\n".join(key_info_parts)

                            # Add other metadata if available
                            metadata_items = []
                            for key, value in details.items():
                                if key not in ["content", "context", "priority_indicators", "status_indicators",
                                              "date_indicators", "created_at", "extraction_date", "extraction_method",
                                              "keywords", "importance_level", "action_keywords"]:
                                    if value and isinstance(value, (str, int, float, bool)):
                                        metadata_items.append(f"**{key.replace('_', ' ').title()}**: {value}")

                            # Add metadata section if we have any metadata
                            if metadata_items:
                                transcript_section += f"\n\n## Additional Metadata\n" + "\n".join(metadata_items)

                            # Ensure the transcript details are prominently displayed by putting them at the beginning
                            # if the existing text is very short
                            if len(existing_text) < 100:
                                enhanced_text = transcript_section + "\n\n" + existing_text
                            else:
                                enhanced_text = existing_text + transcript_section

                            properties[description_field] = {"rich_text": [{"text": {"content": enhanced_text}}]}

                    # Sanitize date fields to ensure valid ISO format
                    self._sanitize_date_properties(properties)

                    # Map properties to match the database schema
                    mapped_properties = self._map_properties_to_schema(
                        properties,
                        db_properties,
                        db_type
                    )

                    # Create new page in database
                    response = self.notion.pages.create(
                        parent={"database_id": db_id},
                        properties=mapped_properties
                    )
                    
                    if response:
                        results["created"] += 1

                        # Add detailed comment with transcript context
                        if "transcript_id" in entry:
                            # Enhanced reference comment with rich details
                            comment_text = f"# Transcript Information\n\n**ID**: {entry['transcript_id']}"

                            # Add rich details if available
                            if "transcript_details" in entry and entry["transcript_details"]:
                                # Format transcript details into a rich comment
                                details = entry["transcript_details"]

                                # Add transcript date/time if available
                                if "created_at" in details:
                                    comment_text += f"\n**Recorded**: {details['created_at']}"

                                # Add importance level
                                if "importance_level" in details:
                                    comment_text += f"\n**Importance**: {details['importance_level'].upper()}"

                                # Add keywords section
                                if "keywords" in details and details["keywords"]:
                                    keywords_str = ", ".join([f"**{kw}**" for kw in details["keywords"][:10]])
                                    comment_text += f"\n\n## Keywords\n{keywords_str}"

                                # Add transcript content preview - with more content
                                if "content" in details:
                                    content_preview = details["content"][:1000] + "..." if len(details["content"]) > 1000 else details["content"]
                                    comment_text += f"\n\n## Transcript Content\n{content_preview}"

                                # Add context from transcript - more prominently displayed
                                if "context" in details:
                                    comment_text += f"\n\n## Context\n{details['context']}"

                                # Add extracted action keywords
                                if "action_keywords" in details and details["action_keywords"]:
                                    action_keywords = ", ".join(details["action_keywords"])
                                    comment_text += f"\n\n**Action Keywords**: {action_keywords}"

                                # Add extracted timestamps
                                if "timestamps" in details:
                                    comment_text += f"\n\n**Timestamps**: {details['timestamps']}"

                            try:
                                # Add comment to the newly created page
                                self._add_comment(response["id"], comment_text)
                            except Exception as e:
                                logger.warning(f"Failed to add comment to page {response['id']}: {e}")
                                # Even if comment fails, the page was still created successfully
                    
                except Exception as e:
                    logger.error(f"Error creating Notion entry: {e}")
                    results["failed"] += 1
                    
                # Respect rate limits
                time.sleep(0.3)
        
        return results
    
    def _add_comment(self, page_id: str, comment_text: str):
        """
        Add a comment to a Notion page.

        Args:
            page_id: ID of the Notion page
            comment_text: Text content for the comment
        """
        # Ensure the comment text is not too long (Notion has limits)
        if len(comment_text) > 2000:
            logger.debug(f"Comment text too long ({len(comment_text)} chars), truncating to 2000 chars")
            comment_text = comment_text[:1997] + "..."

        # Add a small delay to prevent rate limiting (Notion API has rate limits)
        import time
        time.sleep(0.5)

        try:
            self.notion.comments.create(
                parent={"page_id": page_id},
                rich_text=[{"text": {"content": comment_text}}]
            )
            logger.debug(f"Added comment to page {page_id}")
        except Exception as e:
            # If rate limited, try again after a delay
            if "429" in str(e) or "rate limit" in str(e).lower():
                logger.warning(f"Rate limited when adding comment, retrying after delay: {e}")
                time.sleep(2)
                try:
                    self.notion.comments.create(
                        parent={"page_id": page_id},
                        rich_text=[{"text": {"content": comment_text}}]
                    )
                    logger.debug(f"Added comment to page {page_id} after retry")
                    return
                except Exception as retry_e:
                    logger.error(f"Failed to add comment even after retry: {retry_e}")
            else:
                logger.error(f"Error adding comment to page {page_id}: {e}")
    
    def get_database_items(self, db_type: str, query: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Query items from a Notion database.
        
        Args:
            db_type: Database type (tasks, projects, todo, lifelog)
            query: Query parameters for filtering
            
        Returns:
            List of database items
        """
        if not self.api_key or not self.notion:
            logger.error("Notion API client not properly initialized")
            return []
            
        db_id = self.database_ids.get(db_type)
        if not db_id:
            logger.warning(f"No database ID provided for {db_type}")
            return []
            
        try:
            query_params = {"database_id": db_id}
            if query:
                query_params.update(query)
                
            response = self.notion.databases.query(**query_params)
            return response.get("results", [])
            
        except Exception as e:
            logger.error(f"Error querying Notion database: {e}")
            return []
    
    def update_item(self, page_id: str, properties: Dict[str, Any]) -> bool:
        """
        Update a Notion page/item.
        
        Args:
            page_id: ID of the Notion page
            properties: Updated properties
            
        Returns:
            True if successful, False otherwise
        """
        if not self.api_key or not self.notion:
            logger.error("Notion API client not properly initialized")
            return False
            
        try:
            self.notion.pages.update(
                page_id=page_id,
                properties=properties
            )
            return True
            
        except Exception as e:
            logger.error(f"Error updating Notion page {page_id}: {e}")
            return False
    
    def _map_properties_to_schema(self, properties: Dict[str, Any], schema: Dict[str, Any], db_type: str) -> Dict[str, Any]:
        """
        Map properties to match the database schema.

        Args:
            properties: Properties to map
            schema: Database schema
            db_type: Database type

        Returns:
            Mapped properties
        """
        mapped_properties = {}
        property_name_map = self._get_property_name_map(db_type)

        # Iterate through each source property
        for prop_name, prop_value in properties.items():
            # Check if the property needs to be renamed
            mapped_name = property_name_map.get(prop_name, prop_name)

            # Check if the mapped property exists in the schema
            if mapped_name in schema:
                schema_type = schema[mapped_name].get("type")

                # Handle different property types and conversions
                if schema_type == "select" and prop_value.get("select"):
                    # Check if the select option exists
                    existing_options = [option["name"] for option in schema[mapped_name].get("select", {}).get("options", [])]
                    select_value = prop_value["select"].get("name")

                    if select_value in existing_options:
                        mapped_properties[mapped_name] = prop_value
                    else:
                        # If not, use a default/first option if available
                        if existing_options:
                            mapped_properties[mapped_name] = {"select": {"name": existing_options[0]}}
                            logger.debug(f"Using default select option '{existing_options[0]}' for property '{mapped_name}'")

                # Handle relation types
                elif schema_type == "relation" and prop_value.get("select"):
                    # Convert select to relation format
                    # For simplicity, we're omitting the actual relation lookup
                    mapped_properties[mapped_name] = {"relation": []}
                    logger.debug(f"Converting select to empty relation for property '{mapped_name}'")

                # Handle checkbox type
                elif schema_type == "checkbox" and "checkbox" not in prop_value:
                    # Convert status to checkbox if needed
                    if "status" in prop_value:
                        status_value = prop_value["status"].get("name", "").lower()
                        checkbox_value = status_value in ["done", "completed", "finished"]
                        mapped_properties[mapped_name] = {"checkbox": checkbox_value}
                    else:
                        mapped_properties[mapped_name] = {"checkbox": False}

                # Handle status type
                elif schema_type == "status" and "status" not in prop_value:
                    # Check for valid status options
                    status_options = [option["name"] for option in schema[mapped_name].get("status", {}).get("options", [])]
                    default_status = status_options[0] if status_options else "Not Started"
                    mapped_properties[mapped_name] = {"status": {"name": default_status}}
                    logger.debug(f"Using default status '{default_status}' for property '{mapped_name}'")

                # Use the property as-is if types match
                else:
                    mapped_properties[mapped_name] = prop_value

            # If we're dealing with the title property, try to find the actual title field
            elif prop_name == "Title" or prop_name == "Name" or prop_name == "Entry":
                # Find the title-type property
                for schema_prop_name, schema_prop in schema.items():
                    if schema_prop.get("type") == "title":
                        mapped_properties[schema_prop_name] = {"title": prop_value.get("title", [])}
                        logger.debug(f"Mapped title property '{prop_name}' to '{schema_prop_name}'")
                        break

        # Ensure there's a title property
        title_set = False
        for prop_name, prop in schema.items():
            if prop.get("type") == "title" and prop_name not in mapped_properties:
                # Find any property with title content
                for orig_prop, value in properties.items():
                    if "title" in value or "text" in value:
                        content = value.get("title", value.get("text", []))
                        mapped_properties[prop_name] = {"title": content}
                        title_set = True
                        break

                # If no title content found, use a default
                if not title_set:
                    mapped_properties[prop_name] = {"title": [{"text": {"content": f"New {db_type[:-1] if db_type.endswith('s') else db_type}"}}]}
                break

        return mapped_properties

    def _sanitize_date_properties(self, properties: Dict[str, Any]) -> None:
        """
        Sanitize date properties to ensure valid ISO format values.

        Removes null/empty date values that would cause Notion API validation errors.

        Args:
            properties: Properties dictionary to sanitize
        """
        from datetime import datetime

        date_fields = ["Due Date", "Due", "Created Date", "Date", "Meeting Date",
                      "Timeline", "Date Range", "Follow-up Date"]

        default_date = datetime.now().strftime("%Y-%m-%d")

        # Check and fix each property
        for field_name in list(properties.keys()):
            property_value = properties[field_name]

            # Check if it's a date property
            if field_name in date_fields or (isinstance(property_value, dict) and "date" in property_value):
                # Handle date property
                if isinstance(property_value, dict) and "date" in property_value:
                    date_value = property_value["date"]

                    # Remove null date
                    if date_value is None:
                        logger.debug(f"Removing null date value for {field_name}")
                        del properties[field_name]
                        continue

                    # Fix empty or invalid start date
                    if isinstance(date_value, dict) and "start" in date_value:
                        if date_value["start"] is None or date_value["start"] == "":
                            logger.debug(f"Fixing empty start date for {field_name}")
                            date_value["start"] = default_date

                    # Fix empty or invalid end date
                    if isinstance(date_value, dict) and "end" in date_value:
                        if date_value["end"] is None or date_value["end"] == "":
                            logger.debug(f"Fixing empty end date for {field_name}")
                            date_value["end"] = None  # Remove end date instead of setting default

    def _get_property_name_map(self, db_type: str) -> Dict[str, str]:
        """
        Get property name mapping for a specific database type.

        Args:
            db_type: Database type

        Returns:
            Dictionary mapping source property names to target property names
        """
        # Define common property name mappings
        common_mappings = {
            "Description": "Notes",
            "Content": "Notes",
            "Status": "Status",
            "Priority": "Priority",
            "Due Date": "Due",
            "Timeline": "Date Range"
        }

        # Database-specific mappings
        if db_type == "tasks":
            return {
                **common_mappings,
                "Title": "Name",
                "Type": "Type"
            }
        elif db_type == "projects":
            return {
                **common_mappings,
                "Name": "Project",
                "Description": "Description"
            }
        elif db_type == "todo":
            return {
                **common_mappings,
                "Title": "Task",
                "Status": "Done"
            }
        elif db_type == "lifelog":
            return {
                **common_mappings,
                "Entry": "Title",
                "Date": "Date",
                "Notes": "Notes"
            }

        return {}

    def create_comment(self, page_id: str, content: str) -> bool:
        """
        Create a comment on a Notion page.

        Args:
            page_id: ID of the Notion page
            content: Comment text content

        Returns:
            True if successful, False otherwise
        """
        if not self.api_key or not self.notion:
            logger.error("Notion API client not properly initialized")
            return False

        try:
            self.notion.comments.create(
                parent={"page_id": page_id},
                rich_text=[{"text": {"content": content}}]
            )
            return True

        except Exception as e:
            logger.error(f"Error creating comment on page {page_id}: {e}")
            return False

    def get_existing_tags(self, db_type: str) -> List[str]:
        """
        Retrieve existing tags from a Notion database to avoid creating duplicates.

        Args:
            db_type: Database type (tasks, projects, todo, lifelog)

        Returns:
            List of existing tag names
        """
        if not self.api_key or not self.notion:
            logger.error("Notion API client not properly initialized")
            return []

        db_id = self.database_ids.get(db_type)
        if not db_id:
            logger.warning(f"No database ID provided for {db_type}")
            return []

        try:
            # First get the database schema to find the tags property
            db_schema = self.notion.databases.retrieve(database_id=db_id)
            properties = db_schema.get("properties", {})

            # Find the multi-select property for tags
            tag_property = None
            for prop_name, prop_schema in properties.items():
                if prop_schema.get("type") == "multi_select" and (
                    prop_name == "Tags" or
                    prop_name == "Keywords" or
                    prop_name == "Categories"
                ):
                    tag_property = prop_name
                    # Get all pre-defined options for this property
                    options = prop_schema.get("multi_select", {}).get("options", [])
                    return [option["name"] for option in options]

            if not tag_property:
                logger.debug(f"No multi-select tag property found in {db_type} database")
                return []

        except Exception as e:
            logger.error(f"Error retrieving existing tags from {db_type} database: {e}")
            return []

        return []