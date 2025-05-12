"""
Extract actionable items from transcripts.
"""

import os
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from loguru import logger

class ItemExtractor:
    """
    Extracts actionable items from transcript content.
    
    Uses LLM APIs to identify tasks, meetings, projects, and other
    relevant information for Notion integration.
    """
    
    def __init__(self, llm_provider: str = "openai", llm_model: str = "gpt-4"):
        """
        Initialize item extractor.
        
        Args:
            llm_provider: Provider for LLM processing ("openai" or "anthropic")
            llm_model: Model to use for processing
        """
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        
        # Initialize appropriate client based on provider
        if llm_provider == "openai":
            import openai
            self.client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        elif llm_provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        else:
            logger.error(f"Unsupported LLM provider: {llm_provider}")
            self.client = None
    
    def extract_items(self, transcripts: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract actionable items from a list of transcripts.
        
        Args:
            transcripts: List of transcript dictionaries
            
        Returns:
            Dictionary with categories of extracted items
        """
        result = {
            "tasks": [],
            "meetings": [],
            "projects": [],
            "research": [],
            "messages": []
        }
        
        for transcript in transcripts:
            content = transcript.get("content", "")
            if not content or self.client is None:
                continue
                
            try:
                # Extract items using LLM
                # Pass the full transcript object to ensure details are transferred
                extracted = self._extract_with_llm(content, transcript.get("id", ""), transcript)
                
                # Merge results
                for category in result.keys():
                    if category in extracted:
                        result[category].extend(extracted[category])
                        
            except Exception as e:
                logger.error(f"Error extracting items from transcript {transcript.get('id')}: {e}")
        
        return result
    
    def _extract_with_llm(self, content: str, transcript_id: str, transcript: Dict[str, Any] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Use LLM to extract structured information from transcript content.
        
        Args:
            content: Transcript text content
            transcript_id: ID of the transcript for reference
            transcript: Full transcript object including transcript_details

        Returns:
            Dictionary with categories of extracted items
        """
        system_prompt = """
        You are an AI assistant that extracts actionable items from voice transcripts.
        Analyze the following transcript and extract:
        
        1. Tasks: Any actions that need to be done, with title, description, priority, due date, and project.
        2. Meetings: Any mentioned meetings, with title, date, time, participants, and agenda.
        3. Projects: Any project references, with name, description, and timeline.
        4. Research: Any research topics or information needs.
        5. Messages: Any messages that need to be sent to specific people.
        
        Format your response as a JSON object with these categories.
        For dates, use ISO format (YYYY-MM-DD) and extract them if mentioned.
        If a date is relative (e.g., "next Monday"), convert it appropriately based on today's date.
        If priority is not explicitly mentioned, infer it from the context as "high", "medium", or "low".
        
        Today's date is: {today}
        """
        
        user_prompt = f"Transcript content: {content}"
        
        today = datetime.now().strftime("%Y-%m-%d")
        system_prompt = system_prompt.format(today=today)
        
        try:
            if self.llm_provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                extraction_json = response.choices[0].message.content.strip()
                    
            elif self.llm_provider == "anthropic":
                response = self.client.messages.create(
                    model=self.llm_model,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": user_prompt}
                    ]
                )
                extraction_json = response.content[0].text.strip()
                
            else:
                logger.error(f"Unsupported LLM provider: {self.llm_provider}")
                return {}
            
            # Parse the JSON
            extracted_data = json.loads(extraction_json)
            
            # Add transcript ID and item IDs to each item
            for category, items in extracted_data.items():
                for item in items:
                    item["transcript_id"] = transcript_id
                    item["item_id"] = str(uuid.uuid4())

                    # Add transcript_details to each item if available in the transcript
                    # This ensures the details are passed through to Notion
                    if transcript and "transcript_details" in transcript:
                        item["transcript_details"] = transcript.get("transcript_details", {})
            
            return extracted_data
                
        except Exception as e:
            logger.error(f"Error in LLM extraction: {e}")
            return {}
    
    def _estimate_date(self, date_text: str) -> Optional[str]:
        """
        Convert relative date references to ISO format.
        
        Args:
            date_text: Text mentioning a date
            
        Returns:
            ISO format date string or None if parsing fails
        """
        today = datetime.now()
        
        # Common relative date mappings
        if "today" in date_text.lower():
            return today.strftime("%Y-%m-%d")
        elif "tomorrow" in date_text.lower():
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "next week" in date_text.lower():
            return (today + timedelta(days=7)).strftime("%Y-%m-%d")
        elif "next month" in date_text.lower():
            # Simple approximation
            if today.month == 12:
                next_month = datetime(today.year + 1, 1, 1)
            else:
                next_month = datetime(today.year, today.month + 1, 1)
            return next_month.strftime("%Y-%m-%d")
        
        # Weekday references
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for i, day in enumerate(weekdays):
            if day in date_text.lower():
                days_ahead = i - today.weekday()
                if days_ahead <= 0:  # Target day already happened this week
                    days_ahead += 7
                return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        
        return None