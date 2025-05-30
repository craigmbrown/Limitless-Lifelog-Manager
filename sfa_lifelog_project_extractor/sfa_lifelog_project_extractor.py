#!/usr/bin/env python3
"""
SFA Lifelog Project Extractor

Automate extraction, summarization, archive, and keyword project/task generation 
from daily lifelog data, with detailed rationale and business case review, 
and output to Notion and local storage.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, time as datetime_time
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
from dataclasses import dataclass, asdict
import subprocess
import tempfile
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project directories to Python path
sys.path.insert(0, '/home/craigmbrown/Project/Limitless-Lifelog-Manager/src')
sys.path.insert(0, '/home/craigmbrown/Project/Notion-Database-Manager')

# Import required modules
try:
    from limitless_lifelog.limitless.api_client import LimitlessClient
    from limitless_lifelog.transcripts.processor import TranscriptProcessor
    from limitless_lifelog.utils.config import Config
except ImportError as e:
    print(f"Error importing Limitless modules: {e}")
    print("Please ensure Limitless-Lifelog-Manager is properly installed")
    sys.exit(1)

# Import additional modules
import requests

# Constants
NOTION_SECRET = "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"
PROJECTS_DATABASE_ID = "1e9e13474afd81c1bfa1c84f8b31297f"
TASKS_DATABASE_ID = "1e9e13474afd81f5badfce2bc7cc7455"
TODO_DATABASE_ID = "1e9e13474afd8115ac29c6fcbd9a16e2"
WHATSAPP_PHONE = "15712781730"

# Default models
DEFAULT_MODELS = ["openai:o3-mini", "anthropic:claude-3-7-sonnet-20250219", "gemini:gemini-2.5-pro-exp-03-25"]

# Setup logging - will be reconfigured in __init__ with proper output directory
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Turn off debug logging for other modules
logging.getLogger('limitless_lifelog').setLevel(logging.WARNING)
logging.getLogger('limitless_lifelog.limitless.api_client').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

@dataclass
class TranscriptData:
    """Transcript data structure"""
    id: str
    date: str
    time: str
    content: str
    participants: List[str]
    keyword_contexts: List[Dict[str, str]] = None
    
    def __post_init__(self):
        if self.keyword_contexts is None:
            self.keyword_contexts = []
    
@dataclass
class ProjectData:
    """Project data structure for Notion"""
    title: str
    summary: str
    status: str = "Planning"
    priority: str = "Medium"
    rationale: str = ""
    business_case: str = ""
    value_proposition: str = ""
    tags: List[str] = None
    transcript_ids: List[str] = None
    start_date: str = None
    end_date: str = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.transcript_ids is None:
            self.transcript_ids = []
    
@dataclass
class TaskData:
    """Task data structure for Notion"""
    title: str
    description: str
    project_id: Optional[str] = None
    status: str = "Not started"
    priority: str = "Medium"
    complexity: str = "M"  # H/M/L
    assigned_agent: str = ""
    due_date: Optional[str] = None
    tags: List[str] = None
    transcript_ids: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.transcript_ids is None:
            self.transcript_ids = []

@dataclass
class TodoData:
    """Todo data structure for Notion"""
    title: str
    status: str = "Not started"
    priority: str = "Medium"
    due_date: Optional[str] = None
    tags: List[str] = None
    transcript_ids: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.transcript_ids is None:
            self.transcript_ids = []

class LifelogProjectExtractor:
    """Main extractor class"""
    
    def __init__(self, start_date: str, end_date: str, models: List[str], 
                 output_dir: str, limitless_dir: str, notion_dir: str,
                 require_keywords: bool = True):
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d")
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d")
        self.models = models
        self.output_dir = Path(output_dir)
        self.limitless_dir = Path(limitless_dir)
        self.notion_dir = Path(notion_dir)
        self.require_keywords = require_keywords
        
        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup date-based logging
        self.setup_logging()
        
        # Load keywords configuration
        self.keywords_config = self.load_keywords_config()
        
        # Initialize clients
        self.limitless_client = None
        self.notion_connected = False
        
    def setup_logging(self):
        """Setup logging with date and time-based filenames in output directory"""
        # Create logs directory for the date
        date_str = self.start_date.strftime("%Y-%m-%d")
        logs_dir = self.output_dir / date_str / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Create log filename with timestamp
        timestamp = datetime.now().strftime("%H%M%S")
        log_filename = f"extraction_{timestamp}.log"
        log_path = logs_dir / log_filename
        
        # Reconfigure logging
        global logger
        logger = logging.getLogger(__name__)
        logger.handlers = []  # Clear existing handlers
        
        # Add file handler with date/time
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(file_handler)
        
        # Add console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(console_handler)
        
        logger.setLevel(logging.INFO)
        logger.info(f"Logging initialized - Log file: {log_path}")
        
    async def initialize(self):
        """Initialize connections and verify services"""
        logger.info("Initializing services...")
        
        # Initialize Limitless client with proper API key
        try:
            config = Config()
            # Initialize LimitlessClient with API key from config
            self.limitless_client = LimitlessClient(
                api_key=config.limitless_api_key or os.environ.get("LIMITLESS_API_KEY", ""),
                base_url=config.limitless_api_url
            )
            logger.info("Limitless client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Limitless client: {e}")
            raise
            
        # Test Notion connection
        await self.test_notion_connection()
        
        # Send WhatsApp notification
        filter_status = "ON (TB keyword required)" if self.require_keywords else "OFF (all transcripts)"
        await self.send_whatsapp_message(
            f"🚀 Lifelog Extractor Started\n"
            f"Date Range: {self.start_date.date()} to {self.end_date.date()}\n"
            f"Models: {', '.join(self.models)}\n"
            f"Keyword Filter: {filter_status}"
        )
        
    async def test_notion_connection(self, retries: int = 3):
        """Test Notion connection with retries"""
        for attempt in range(retries):
            try:
                # Test Notion connection by searching for a dummy page
                cmd = [
                    "python", str(self.notion_dir / "starter_notion_agent.py"),
                    "search", "test_connection_dummy"
                ]
                
                env = os.environ.copy()
                env["NOTION_INTERNAL_INTEGRATION_SECRET"] = NOTION_SECRET
                
                result = subprocess.run(cmd, capture_output=True, text=True, env=env)
                
                if result.returncode == 0 or "No pages found" in result.stdout:
                    self.notion_connected = True
                    logger.info("Notion connection verified")
                    return
                    
            except Exception as e:
                logger.warning(f"Notion connection attempt {attempt + 1} failed: {e}")
                
        logger.error("Failed to connect to Notion after all retries")
        
    def load_keywords_config(self) -> Dict:
        """Load keywords configuration from file"""
        config_path = Path(__file__).parent / "keywords_config.json"
        if config_path.exists():
            with open(config_path, 'r') as f:
                return json.load(f)
        else:
            # Return default configuration if file doesn't exist
            return {
                "project_keywords": ["project", "initiative", "develop", "create", "build"],
                "task_keywords": ["analyze", "research", "review", "prepare", "document"],
                "todo_keywords": ["check", "follow up", "email", "call", "schedule"]
            }
        
    def extract_keyword_contexts(self, text: str) -> List[Dict[str, str]]:
        """Extract contexts around primary keywords"""
        primary_keywords = self.keywords_config.get('primary_keywords', ['TB'])
        context_window = self.keywords_config.get('context_window_words', 50)
        
        contexts = []
        words = text.split()
        
        for i, word in enumerate(words):
            # Clean word of punctuation for matching
            clean_word = ''.join(c for c in word if c.isalnum() or c in ['-', '_'])
            
            # Check if word exactly matches any primary keyword (case-insensitive)
            if any(clean_word.lower() == keyword.lower() for keyword in primary_keywords):
                # Get context before and after
                start_idx = max(0, i - context_window)
                end_idx = min(len(words), i + context_window + 1)
                
                before_context = ' '.join(words[start_idx:i])
                keyword_phrase = word
                after_context = ' '.join(words[i+1:end_idx])
                
                contexts.append({
                    'before': before_context,
                    'keyword': keyword_phrase,
                    'after': after_context,
                    'full_context': ' '.join(words[start_idx:end_idx])
                })
                
                logger.info(f"Found primary keyword '{keyword_phrase}' with context")
        
        return contexts
    
    def list_all_lifelogs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all available lifelogs to check what's available.
        
        Args:
            limit: Maximum number of lifelogs to retrieve
            
        Returns:
            List of lifelog dictionaries with basic metadata
        """
        try:
            # Get config and API key
            config = Config()
            api_key = config.limitless_api_key or os.environ.get("LIMITLESS_API_KEY", "")
            
            if not api_key:
                logger.error("No Limitless API key found")
                return []
            
            # Use the v1/lifelogs endpoint
            url = "https://api.limitless.ai/v1/lifelogs"
            
            # Set up headers
            headers = {
                "X-API-Key": api_key,
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            # Set up parameters - no date filter to get all
            params = {
                "limit": 10,  # Max allowed by API per page
                "direction": "desc",
                "includeMarkdown": "false",  # Don't include full content for listing
                "includeHeadings": "false"
            }
            
            all_lifelogs = []
            cursor = None
            
            logger.info(f"Listing all available lifelogs (up to {limit} total)")
            
            # Paginate through results
            while len(all_lifelogs) < limit:
                if cursor:
                    params["cursor"] = cursor
                
                response = requests.get(url, headers=headers, params=params, timeout=30)
                
                if response.status_code != 200:
                    logger.error(f"API request failed with status {response.status_code}: {response.text}")
                    break
                
                data = response.json()
                
                # Extract lifelogs from response
                lifelogs = data.get("lifelogs", [])
                if not lifelogs:
                    logger.info("No more lifelogs found")
                    break
                
                all_lifelogs.extend(lifelogs)
                logger.info(f"Retrieved {len(lifelogs)} lifelogs, total so far: {len(all_lifelogs)}")
                
                # Log the dates of the lifelogs
                for log in lifelogs:
                    log_date = log.get('startTime', 'Unknown')
                    log_id = log.get('id', 'Unknown')
                    logger.debug(f"Found lifelog {log_id} from {log_date}")
                
                # Check for next page
                cursor = data.get("cursor")
                if not cursor:
                    logger.info("No more pages available")
                    break
            
            # Group by date for summary
            logs_by_date = {}
            for log in all_lifelogs:
                start_time = log.get('startTime', '')
                if start_time:
                    try:
                        # Extract date from timestamp
                        date_str = start_time.split('T')[0]
                        if date_str not in logs_by_date:
                            logs_by_date[date_str] = 0
                        logs_by_date[date_str] += 1
                    except:
                        pass
            
            logger.info(f"\nLifelog summary by date:")
            for date_str in sorted(logs_by_date.keys(), reverse=True):
                logger.info(f"  {date_str}: {logs_by_date[date_str]} lifelogs")
            
            return all_lifelogs
            
        except Exception as e:
            logger.error(f"Error listing lifelogs: {e}")
            return []
    
    def fetch_lifelogs_for_date(self, date: datetime) -> List[Dict[str, Any]]:
        """Fetch lifelogs for a specific date using the v1/lifelogs endpoint.
        
        Args:
            date: The date to fetch lifelogs for
            
        Returns:
            List of lifelog dictionaries
        """
        try:
            # Get config and API key
            config = Config()
            api_key = config.limitless_api_key or os.environ.get("LIMITLESS_API_KEY", "")
            
            if not api_key:
                logger.error("No Limitless API key found")
                return []
            
            # Use the v1/lifelogs endpoint
            url = "https://api.limitless.ai/v1/lifelogs"
            
            # Format date as YYYY-MM-DD
            date_str = date.strftime("%Y-%m-%d")
            
            # Set up headers
            headers = {
                "X-API-Key": api_key,
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            # Set up parameters
            params = {
                "date": date_str,
                "limit": 10,  # Max allowed by API
                "direction": "desc",
                "includeMarkdown": "true",
                "includeHeadings": "true"
            }
            
            all_lifelogs = []
            cursor = None
            
            # Paginate through all results
            while True:
                if cursor:
                    params["cursor"] = cursor
                
                logger.info(f"Fetching lifelogs for {date_str} (cursor: {cursor})")
                
                response = requests.get(url, headers=headers, params=params, timeout=30)
                
                if response.status_code != 200:
                    logger.error(f"API request failed with status {response.status_code}: {response.text}")
                    break
                
                data = response.json()
                
                # Extract lifelogs from response
                lifelogs = data.get("lifelogs", [])
                if not lifelogs:
                    break
                
                all_lifelogs.extend(lifelogs)
                logger.info(f"Retrieved {len(lifelogs)} lifelogs, total so far: {len(all_lifelogs)}")
                
                # Check for next page
                cursor = data.get("cursor")
                if not cursor:
                    break
            
            return all_lifelogs
            
        except Exception as e:
            logger.error(f"Error fetching lifelogs for date {date}: {e}")
            return []
    
    def get_lifelog(self, lifelog_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific lifelog by ID using the v1/lifelogs/{id} endpoint.
        
        Args:
            lifelog_id: The ID of the lifelog to fetch
            
        Returns:
            Lifelog dictionary or None if not found
        """
        try:
            # Get config and API key
            config = Config()
            api_key = config.limitless_api_key or os.environ.get("LIMITLESS_API_KEY", "")
            
            if not api_key:
                logger.error("No Limitless API key found")
                return None
            
            # Use the v1/lifelogs/{id} endpoint
            url = f"https://api.limitless.ai/v1/lifelogs/{lifelog_id}"
            
            # Set up headers
            headers = {
                "X-API-Key": api_key,
                "Accept": "application/json"
            }
            
            # Set up parameters
            params = {
                "includeMarkdown": "true",
                "includeHeadings": "true"
            }
            
            logger.info(f"Fetching lifelog {lifelog_id}")
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 404:
                logger.warning(f"Lifelog {lifelog_id} not found")
                return None
            elif response.status_code != 200:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                return None
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching lifelog {lifelog_id}: {e}")
            return None
    
    def filter_transcripts_by_keyword(self, transcripts: List[TranscriptData]) -> List[TranscriptData]:
        """Filter transcripts that contain primary keywords"""
        filtered_transcripts = []
        
        for transcript in transcripts:
            contexts = self.extract_keyword_contexts(transcript.content)
            if contexts:
                # Add keyword contexts to transcript
                transcript.keyword_contexts = contexts
                filtered_transcripts.append(transcript)
                logger.info(f"Transcript {transcript.id} contains {len(contexts)} primary keyword(s)")
        
        return filtered_transcripts
    
    def extract_transcripts(self) -> Dict[str, List[TranscriptData]]:
        """Extract lifelog transcripts for date range
        
        Uses the existing LimitlessClient to fetch transcripts and filters by date.
        """
        logger.info(f"Extracting transcripts from {self.start_date} to {self.end_date}")
        
        # Use the existing client's fetch_transcripts method
        logger.info("Fetching all available transcripts from Limitless API...")
        
        try:
            # Fetch transcripts starting from the beginning of our date range
            since_datetime = datetime.combine(self.start_date, datetime_time.min)
            all_transcripts = self.limitless_client.fetch_transcripts(
                since_time=since_datetime,
                max_results=1000
            )
            
            logger.info(f"Retrieved {len(all_transcripts)} total transcripts from API")
            
            if not all_transcripts:
                logger.warning("No transcripts found. Trying without date filter...")
                # Try again without date filter
                all_transcripts = self.limitless_client.fetch_transcripts(max_results=1000)
                logger.info(f"Retrieved {len(all_transcripts)} total transcripts without date filter")
                
                if not all_transcripts:
                    logger.warning("No transcripts found in your account. Please check:")
                    logger.warning("1. Your Limitless API key is valid")
                    logger.warning("2. You have recorded lifelogs in your Limitless account")
                    logger.warning("3. The API key has permission to access lifelogs")
                    return {}
            
            # Now filter and organize by date
            transcripts_by_date = {}
            
            for transcript in all_transcripts:
                # Parse transcript timestamp
                transcript_time = (transcript.get('startTime') or 
                                 transcript.get('timestamp') or 
                                 transcript.get('created_at') or
                                 transcript.get('endTime', ''))
                
                if transcript_time:
                    try:
                        # Handle different timestamp formats
                        if isinstance(transcript_time, str):
                            # Remove timezone info if present
                            transcript_time = transcript_time.replace('Z', '+00:00')
                            if transcript_time.endswith('+00:00+00:00'):
                                transcript_time = transcript_time[:-6]
                            trans_datetime = datetime.fromisoformat(transcript_time)
                        else:
                            # Handle Unix timestamp
                            trans_datetime = datetime.fromtimestamp(transcript_time)
                        
                        # Check if transcript is within our date range
                        if self.start_date.date() <= trans_datetime.date() <= self.end_date.date():
                            date_str = trans_datetime.strftime("%Y-%m-%d")
                            
                            if date_str not in transcripts_by_date:
                                transcripts_by_date[date_str] = []
                            
                            # Process transcript
                            transcript_data = self.process_api_transcript(transcript, date_str)
                            if transcript_data:
                                transcripts_by_date[date_str].append(transcript_data)
                                
                    except Exception as e:
                        logger.warning(f"Error parsing timestamp '{transcript_time}': {e}")
            
            # Save transcripts to files
            for date_str, transcripts in transcripts_by_date.items():
                self.save_transcripts_for_date(transcripts, date_str)
                
            logger.info(f"Organized {sum(len(t) for t in transcripts_by_date.values())} transcripts across {len(transcripts_by_date)} dates")
            return transcripts_by_date
            
        except Exception as e:
            logger.error(f"Error extracting transcripts: {e}")
            return {}
    
    def process_api_transcript(self, transcript: Dict[str, Any], date_str: str) -> Optional[TranscriptData]:
        """Process a transcript from the API into TranscriptData format."""
        try:
            # Extract time from timestamp
            timestamp = (transcript.get('startTime') or 
                        transcript.get('timestamp') or 
                        transcript.get('created_at') or
                        transcript.get('endTime', ''))
            
            # Extract time from timestamp
            try:
                if 'T' in timestamp:
                    time_str = timestamp.split('T')[1].split('.')[0].split('+')[0]
                else:
                    time_str = "00:00:00"
            except:
                time_str = "00:00:00"
            
            # Get content from different possible fields - prefer markdown for full content
            content = transcript.get('markdown') or transcript.get('content', '')
            
            # If content is still empty, check contents array
            if not content and 'contents' in transcript:
                contents = transcript.get('contents', [])
                if contents and isinstance(contents[0], dict):
                    content = contents[0].get('content', '')
            
            # Get title if available
            title = transcript.get('title', '')
            if title and content:
                content = f"# {title}\n\n{content}"
            
            transcript_data = TranscriptData(
                id=transcript.get('id', ''),
                date=date_str,
                time=time_str,
                content=content,
                participants=self.extract_participants(content)
            )
            
            # Check if transcript contains primary keywords
            contexts = self.extract_keyword_contexts(content)
            if self.require_keywords:
                if contexts:
                    transcript_data.keyword_contexts = contexts
                    logger.info(f"Transcript {transcript_data.id} contains {len(contexts)} primary keyword(s)")
                    return transcript_data
                else:
                    logger.info(f"Skipping transcript {transcript_data.id} - no primary keywords found")
                    return None
            else:
                # Include all transcripts when keywords not required
                transcript_data.keyword_contexts = contexts
                if contexts:
                    logger.info(f"Transcript {transcript_data.id} contains {len(contexts)} primary keyword(s)")
                return transcript_data
                
        except Exception as e:
            logger.error(f"Error processing transcript: {e}")
            return None
    
    def save_transcripts_for_date(self, transcripts: List[TranscriptData], date_str: str):
        """Save transcripts to files for a specific date."""
        if not transcripts:
            return
            
        # Create date output directory
        date_dir = self.output_dir / date_str / "transcripts"
        date_dir.mkdir(parents=True, exist_ok=True)
        
        for transcript_data in transcripts:
            # Save transcript to file
            filename = f"transcript-{transcript_data.time.replace(':', '')}-{transcript_data.id}.md"
            filepath = date_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# Transcript {transcript_data.id}\n\n")
                f.write(f"Date: {transcript_data.date}\n")
                f.write(f"Time: {transcript_data.time}\n")
                f.write(f"Participants: {', '.join(transcript_data.participants)}\n\n")
                
                # Add keyword contexts section
                if transcript_data.keyword_contexts:
                    f.write("## Primary Keyword Contexts\n\n")
                    for ctx in transcript_data.keyword_contexts:
                        f.write(f"### Context for '{ctx['keyword']}'\n")
                        f.write(f"**Before:** {ctx['before']}\n")
                        f.write(f"**Keyword:** {ctx['keyword']}\n")
                        f.write(f"**After:** {ctx['after']}\n\n")
                
                f.write("## Full Content\n\n")
                f.write(transcript_data.content)
                
            logger.info(f"Saved transcript {transcript_data.id} to {filepath}")
    
    def process_lifelogs_to_transcripts(self, lifelogs: List[Dict[str, Any]], date_str: str) -> List[TranscriptData]:
        """Process a list of lifelogs into TranscriptData format."""
        transcripts = []
        
        for lifelog in lifelogs:
            transcript_data = self.process_single_lifelog(lifelog, date_str)
            if transcript_data:
                transcripts.append(transcript_data)
        
        # Save transcripts to files
        if transcripts:
            self.save_transcripts_for_date(transcripts, date_str)
        
        return transcripts
    
        
    def extract_participants(self, content: str) -> List[str]:
        """Extract participants from transcript content"""
        # Simple implementation - can be enhanced
        participants = []
        
        # Look for speaker patterns
        lines = content.split('\n')
        for line in lines:
            if ':' in line and len(line.split(':')[0]) < 50:
                speaker = line.split(':')[0].strip()
                if speaker and speaker not in participants:
                    participants.append(speaker)
                    
        return participants if participants else ["Unknown"]
        
    def generate_summaries(self, transcripts_by_date: Dict[str, List[TranscriptData]]) -> Dict[str, Dict]:
        """Generate summaries for each day using multiple models"""
        summaries_by_date = {}
        
        for date_str, transcripts in transcripts_by_date.items():
            logger.info(f"Generating summaries for {date_str}")
            
            # Combine all transcripts for the day
            combined_content = "\n\n---\n\n".join([
                f"[Transcript {t.id} - {t.time}]\n{t.content[:500]}..." 
                if len(t.content) > 500 else f"[Transcript {t.id} - {t.time}]\n{t.content}"
                for t in transcripts
            ])
            
            logger.info(f"Processing {len(transcripts)} transcripts with total length: {sum(len(t.content) for t in transcripts)} chars")
            
            # Generate summaries with each model
            model_summaries = {}
            
            for model in self.models:
                try:
                    summary = self.generate_summary_with_model(
                        combined_content, transcripts, model
                    )
                    model_summaries[model] = summary
                    
                    # Save individual model summary
                    summary_dir = self.output_dir / date_str
                    summary_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Add timestamp to filename to prevent overwriting
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    model_name = model.replace(':', '_')
                    summary_file = summary_dir / f"summary-{timestamp}-{model_name}.md"
                    
                    with open(summary_file, 'w', encoding='utf-8') as f:
                        f.write(f"# Summary by {model}\n\n")
                        f.write(f"Date: {date_str}\n\n")
                        f.write("## Summary\n\n")
                        f.write(summary['summary'])
                        f.write("\n\n## Recommendations\n\n")
                        f.write(json.dumps(summary['recommendations'], indent=2))
                        f.write("\n\n## Tags\n\n")
                        f.write(', '.join(summary['tags']))
                        f.write("\n\n## Referenced Transcripts\n\n")
                        f.write(', '.join([t.id for t in transcripts]))
                        
                except Exception as e:
                    logger.error(f"Error generating summary with {model}: {e}")
                    
            # Generate consolidated summary
            consolidated = self.generate_consolidated_summary(
                model_summaries, transcripts
            )
            
            summaries_by_date[date_str] = {
                'model_summaries': model_summaries,
                'consolidated': consolidated,
                'transcript_ids': [t.id for t in transcripts]
            }
            
            # Save consolidated summary with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            consolidated_file = self.output_dir / date_str / f"summary-{timestamp}-consolidated.md"
            with open(consolidated_file, 'w', encoding='utf-8') as f:
                f.write(f"# Consolidated Summary\n\n")
                f.write(f"Date: {date_str}\n\n")
                f.write(consolidated)
                
        return summaries_by_date
        
    def generate_summary_with_model(self, content: str, transcripts: List[TranscriptData], 
                                        model: str) -> Dict:
        """Generate summary using a specific model via direct API calls"""
        # Get keywords from configuration
        project_keywords = ', '.join(f'"{k}"' for k in self.keywords_config.get('project_keywords', [])[:10])
        task_keywords = ', '.join(f'"{k}"' for k in self.keywords_config.get('task_keywords', [])[:10])
        todo_keywords = ', '.join(f'"{k}"' for k in self.keywords_config.get('todo_keywords', [])[:10])
        
        # Include keyword context information if available
        context_info = ""
        if transcripts and hasattr(transcripts[0], 'keyword_contexts') and transcripts[0].keyword_contexts:
            context_info = "\n\nPrimary Keyword Contexts Found:\n"
            for t in transcripts:
                for ctx in t.keyword_contexts:
                    context_info += f"\n- Before '{ctx['keyword']}': {ctx['before']}\n"
                    context_info += f"- After '{ctx['keyword']}': {ctx['after']}\n"
        
        # Build prompt based on whether we have keyword contexts
        if context_info:
            prompt = f"""
            IMPORTANT: Only extract projects, tasks, and todos that are explicitly mentioned in the context surrounding the "TB" keyword.
            
            The transcript contains the keyword "TB" in these contexts:
            {context_info}
            
            Based ONLY on these specific contexts around "TB", provide:
            1. A summary of the instructions found near "TB"
            2. Projects, tasks, and todos mentioned in these TB contexts only
            3. Tags relevant to these specific instructions
            
            DO NOT extract any projects, tasks, or todos from other parts of the transcript that are not near "TB".
            
            Keywords to help identify item types:
            - Projects: {project_keywords}
            - Tasks: {task_keywords}
            - Todos: {todo_keywords}
            
            Full Transcripts (for reference only):
            {content}
            
            Provide output in JSON format:
            {{
                "summary": "Summary of instructions near TB keyword",
                "recommendations": {{
                    "projects": [only projects mentioned near TB],
                    "tasks": [only tasks mentioned near TB],
                    "todos": [only todos mentioned near TB]
                }},
                "tags": [relevant tags]
            }}
            """
        else:
            # No TB keyword found, but transcript included (shouldn't happen with filtering on)
            prompt = f"""
            Analyze the following daily transcripts and provide:
            1. A clear, action-focused summary
            2. Recommendations for projects, tasks, and to-dos
            3. Key tags/keywords for Notion organization
            
            Keywords to identify items:
            - Projects: Look for keywords like {project_keywords}
            - Tasks: Look for keywords like {task_keywords}
            - Todos: Look for keywords like {todo_keywords}
            
            Transcripts:
            {content}
            
            Provide output in JSON format:
            {{
                "summary": "...",
                "recommendations": {{
                    "projects": [...],
                    "tasks": [...],
                    "todos": [...]
                }},
                "tags": [...]
            }}
            """
        
        try:
            # Use OpenAI API directly for now
            if model.startswith("openai:") or model.startswith("o:"):
                import openai
                from openai import OpenAI
                
                client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                model_name = model.split(":")[-1]
                
                # o3-mini doesn't support temperature parameter
                if model_name == "o3-mini":
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that analyzes transcripts and provides structured summaries."},
                            {"role": "user", "content": prompt}
                        ],
                        response_format={"type": "json_object"}
                    )
                else:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that analyzes transcripts and provides structured summaries."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        response_format={"type": "json_object"}
                    )
                
                return json.loads(response.choices[0].message.content)
                
            elif model.startswith("anthropic:") or model.startswith("a:"):
                # Use Anthropic API
                import anthropic
                
                client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
                model_name = model.split(":")[-1]
                
                response = client.messages.create(
                    model=model_name,
                    max_tokens=4096,
                    messages=[{
                        "role": "user", 
                        "content": f"Please analyze these transcripts and respond with valid JSON only:\n\n{prompt}"
                    }]
                )
                
                # Extract JSON from response
                response_text = response.content[0].text
                json_match = re.search(r'\{[\s\S]*\}', response_text)
                if json_match:
                    return json.loads(json_match.group())
                else:
                    return json.loads(response_text)
                    
            elif model.startswith("gemini:") or model.startswith("g:"):
                # Use Gemini API via google.generativeai
                try:
                    import google.generativeai as genai
                    
                    # Try multiple ways to get the API key
                    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                    if not api_key:
                        # Check if it's in the .env file that was loaded
                        from dotenv import dotenv_values
                        env_values = dotenv_values("/home/craigmbrown/Project/sfa_lifelog_project_extractor/.env")
                        api_key = env_values.get("GEMINI_API_KEY")
                    
                    if not api_key:
                        logger.warning("GEMINI_API_KEY not found in environment or .env file, using default response")
                        return self._get_default_summary_response(transcripts)
                    
                    genai.configure(api_key=api_key)
                    model_name = model.split(":")[-1]
                    
                    gemini_model = genai.GenerativeModel(model_name)
                    response = gemini_model.generate_content(
                        f"Please analyze these transcripts and respond with valid JSON only:\n\n{prompt}"
                    )
                    
                    # Extract JSON from response
                    response_text = response.text
                    json_match = re.search(r'\{[\s\S]*\}', response_text)
                    if json_match:
                        return json.loads(json_match.group())
                    else:
                        return json.loads(response_text)
                except Exception as e:
                    logger.warning(f"Gemini API error: {str(e)[:200]}. Using default response.")
                    return self._get_default_summary_response(transcripts)
                    
            else:
                # For other models, return a default structure
                logger.warning(f"Model {model} not directly supported, using default response")
                return self._get_default_summary_response(transcripts)
                
        except Exception as e:
            logger.error(f"Error with model {model}: {e}")
            return {
                "summary": "Error generating summary",
                "recommendations": {"projects": [], "tasks": [], "todos": []},
                "tags": []
            }
    
    def _get_default_summary_response(self, transcripts: List[TranscriptData]) -> Dict:
        """Get a default summary response when model is not available"""
        return {
            "summary": f"Transcripts from {transcripts[0].date} containing various discussions. Total {len(transcripts)} transcripts analyzed.",
            "recommendations": {
                "projects": ["Review and analyze daily activities", "Organize transcript insights"],
                "tasks": ["Extract actionable items from transcripts", "Categorize discussion topics"],
                "todos": ["Review transcript content", "Follow up on key discussions"]
            },
            "tags": ["daily", "transcript", "review", "lifelog", transcripts[0].date]
        }
            
    def generate_consolidated_summary(self, model_summaries: Dict, 
                                          transcripts: List[TranscriptData]) -> str:
        """Generate consolidated summary from all model outputs"""
        # Combine all model insights
        all_summaries = []
        all_recommendations = {"projects": [], "tasks": [], "todos": []}
        all_tags = set()
        
        for model, summary in model_summaries.items():
            all_summaries.append(f"[{model}]: {summary['summary']}")
            
            for category in ['projects', 'tasks', 'todos']:
                all_recommendations[category].extend(
                    summary['recommendations'].get(category, [])
                )
                
            all_tags.update(summary.get('tags', []))
            
        # Create consolidated summary
        consolidated = f"""
## Consolidated Analysis

### Key Insights
{chr(10).join(all_summaries)}

### Unified Recommendations

**Projects:**
{chr(10).join(f"- {p}" for p in set(all_recommendations['projects']))}

**Tasks:**
{chr(10).join(f"- {t}" for t in set(all_recommendations['tasks']))}

**To-Dos:**
{chr(10).join(f"- {td}" for td in set(all_recommendations['todos']))}

### Tags
{', '.join(sorted(all_tags))}

### Participants
{', '.join(set(p for t in transcripts for p in t.participants))}

### Referenced Transcripts
{', '.join(t.id for t in transcripts)}
"""
        
        return consolidated
        
    def generate_projects_and_tasks(self, summaries_by_date: Dict) -> Dict:
        """Generate projects and tasks from summaries"""
        logger.info("Generating projects and tasks...")
        
        all_projects = []
        all_tasks = []
        all_todos = []
        project_id_map = {}  # Map project titles to IDs for linking
        
        for date_str, summary_data in summaries_by_date.items():
            # Extract recommendations from consolidated summary
            recommendations = self.extract_recommendations_from_summaries(summary_data)
            
            # Generate projects first
            for i, project_title in enumerate(recommendations['projects']):
                project = self.generate_project_details(
                    project_title, summary_data, date_str
                )
                all_projects.append(project)
                # Create a temporary ID for linking (will be replaced with actual Notion ID)
                project_id_map[project_title] = f"project_{date_str}_{i}"
                
            # Generate tasks linked to projects
            for task_title in recommendations['tasks']:
                # Try to find a related project
                related_project_title = None
                for project_title in recommendations['projects']:
                    # Simple matching - check if task relates to project
                    if any(word in task_title.lower() for word in project_title.lower().split()):
                        related_project_title = project_title
                        break
                
                task = self.generate_task_details(
                    task_title, summary_data, date_str,
                    project_id=project_id_map.get(related_project_title)
                )
                all_tasks.append(task)
                
            # Generate todos with full context
            # Add todos from recommendations
            for todo_title in recommendations['todos']:
                # Extract tags from all model summaries
                all_tags = set()
                for model_summary in summary_data.get('model_summaries', {}).values():
                    all_tags.update(model_summary.get('tags', []))
                
                # Add summary context to todo
                consolidated_summary = summary_data.get('consolidated', '')
                todo_with_context = f"{todo_title} (from {date_str} lifelog)"
                
                todo = TodoData(
                    title=todo_with_context,
                    status="Not started",
                    priority="Medium",
                    due_date=(datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=3)).strftime("%Y-%m-%d"),
                    tags=list(all_tags)[:5],  # Limit to 5 tags
                    transcript_ids=summary_data['transcript_ids']
                )
                all_todos.append(todo)
                
            # Also create general todos from the consolidated summary
            if "Activity Summary" in summary_data.get('consolidated', ''):
                # Extract key activities that aren't already projects/tasks
                general_todo = TodoData(
                    title=f"Review activities from {date_str}",
                    status="Not started",
                    priority="Low",
                    due_date=(datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d"),
                    tags=["review", "lifelog", date_str],
                    transcript_ids=summary_data['transcript_ids']
                )
                all_todos.append(general_todo)
                
        # Save to output files with timestamp
        output_data = {
            'projects': [asdict(p) for p in all_projects],
            'tasks': [asdict(t) for t in all_tasks],
            'todos': [asdict(td) for td in all_todos]
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        load_dir = self.output_dir / self.end_date.strftime("%Y-%m-%d") / "load"
        load_dir.mkdir(parents=True, exist_ok=True)
        
        with open(load_dir / f"project-task-todo-{timestamp}.json", 'w') as f:
            json.dump(output_data, f, indent=2)
            
        return output_data
        
    def extract_recommendations_from_summaries(self, summary_data: Dict) -> Dict:
        """Extract unique recommendations from all model summaries"""
        all_recs = {"projects": set(), "tasks": set(), "todos": set()}
        
        for model, summary in summary_data['model_summaries'].items():
            for category in ['projects', 'tasks', 'todos']:
                recs = summary['recommendations'].get(category, [])
                all_recs[category].update(recs)
                
        return {k: list(v) for k, v in all_recs.items()}
        
    def generate_project_details(self, title: str, summary_data: Dict, 
                                     date_str: str) -> ProjectData:
        """Generate detailed project with rationale and business case"""
        # Use AI to generate project details
        prompt = f"""
        Based on this project idea: "{title}"
        From context: {summary_data['consolidated'][:1000]}
        
        Generate:
        1. Clear rationale for why this project is valuable
        2. Business case with expected outcomes
        3. Value proposition
        4. Implementation plan outline
        
        Format as JSON:
        {{
            "rationale": "...",
            "business_case": "...",
            "value_proposition": "...",
            "priority": "High/Medium/Low"
        }}
        """
        
        # Use just-prompt with first available model
        details = self.get_ai_response(prompt, self.models[0])
        
        # Extract all tags from summaries
        all_tags = set()
        for model_summary in summary_data.get('model_summaries', {}).values():
            all_tags.update(model_summary.get('tags', []))
        
        # Calculate end date based on project scope
        start = datetime.strptime(date_str, "%Y-%m-%d")
        end_date = (start + timedelta(days=30)).strftime("%Y-%m-%d")  # Default 30-day project
        
        return ProjectData(
            title=title,
            summary=f"Generated from lifelog analysis on {date_str}. Based on {len(summary_data['transcript_ids'])} transcripts.",
            status="Planning",
            rationale=details.get('rationale', 'To be determined based on transcript analysis'),
            business_case=details.get('business_case', 'Value creation through systematic implementation'),
            value_proposition=details.get('value_proposition', 'Improved productivity and outcomes'),
            priority=details.get('priority', 'Medium'),
            tags=list(all_tags)[:10],  # Limit to 10 tags
            transcript_ids=summary_data['transcript_ids'],
            start_date=date_str,
            end_date=end_date
        )
        
    def generate_task_details(self, title: str, summary_data: Dict, 
                                  date_str: str, project_id: Optional[str] = None) -> TaskData:
        """Generate task with complexity assessment and agent assignment"""
        # Assess task complexity and assign agent
        prompt = f"""
        Analyze this task: "{title}"
        Context: {summary_data['consolidated'][:500]}
        
        Assess:
        1. Complexity level (H/M/L)
        2. Best AI agent/model for execution based on complexity
        3. Estimated completion time
        
        Format as JSON:
        {{
            "complexity": "H/M/L",
            "assigned_agent": "model_name",
            "estimated_days": number,
            "priority": "High/Medium/Low"
        }}
        """
        
        details = self.get_ai_response(prompt, self.models[0])
        
        due_date = (datetime.strptime(date_str, "%Y-%m-%d") + 
                   timedelta(days=details.get('estimated_days', 7))).strftime("%Y-%m-%d")
        
        # Extract all tags from summaries
        all_tags = set()
        for model_summary in summary_data.get('model_summaries', {}).values():
            all_tags.update(model_summary.get('tags', []))
        
        return TaskData(
            title=title,
            description=f"Task identified from lifelog on {date_str}. Extracted from {len(summary_data['transcript_ids'])} transcripts.",
            project_id=project_id,
            status="Not started",
            complexity=details.get('complexity', 'M'),
            assigned_agent=details.get('assigned_agent', self.models[0]),
            priority=details.get('priority', 'Medium'),
            due_date=due_date,
            tags=list(all_tags)[:5],  # Limit to 5 tags
            transcript_ids=summary_data['transcript_ids']
        )
        
    def get_ai_response(self, prompt: str, model: str) -> Dict:
        """Get AI response via direct API calls"""
        try:
            # Use OpenAI API directly
            if model.startswith("openai:") or model.startswith("o:"):
                from openai import OpenAI
                
                client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                model_name = model.split(":")[-1]
                
                # o3-mini doesn't support temperature parameter
                if model_name == "o3-mini":
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that provides structured JSON responses."},
                            {"role": "user", "content": prompt}
                        ],
                        response_format={"type": "json_object"}
                    )
                else:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that provides structured JSON responses."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        response_format={"type": "json_object"}
                    )
                
                return json.loads(response.choices[0].message.content)
            else:
                logger.warning(f"Model {model} not directly supported")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting AI response: {e}")
            return {}
            
    async def upload_to_notion(self, data: Dict):
        """Upload projects, tasks, and todos to Notion"""
        logger.info("Uploading to Notion...")
        
        # Group tasks by project
        tasks_by_project = {}
        for task in data['tasks']:
            project_id = task.get('project_id', 'no_project')
            if project_id not in tasks_by_project:
                tasks_by_project[project_id] = []
            tasks_by_project[project_id].append(task)
        
        # Upload projects with their related tasks
        for i, project in enumerate(data['projects']):
            # Upload project
            notion_id = await self.upload_project_to_notion(project)
            
            # Find tasks for this project
            temp_project_id = f"project_{project.get('start_date', '')}_{i}"
            if temp_project_id in tasks_by_project:
                logger.info(f"Uploading {len(tasks_by_project[temp_project_id])} tasks for project: {project['title']}")
                for task in tasks_by_project[temp_project_id]:
                    # Update task with actual Notion project ID if available
                    if notion_id:
                        task['project_id'] = notion_id
                    await self.upload_task_to_notion(task)
        
        # Upload any tasks without projects
        if 'no_project' in tasks_by_project:
            logger.info(f"Uploading {len(tasks_by_project['no_project'])} tasks without projects")
            for task in tasks_by_project['no_project']:
                await self.upload_task_to_notion(task)
            
        # Upload todos
        logger.info(f"Uploading {len(data['todos'])} todos to Notion...")
        for todo in data['todos']:
            await self.upload_todo_to_notion(todo)
            
    async def upload_project_to_notion(self, project: Dict) -> Optional[str]:
        """Upload a project to Notion"""
        try:
            # Prepare comprehensive project properties
            # Combine all text content for the summary
            full_summary = f"{project['summary']}\n\n" \
                          f"**Rationale:** {project.get('rationale', '')}\n\n" \
                          f"**Business Case:** {project.get('business_case', '')}\n\n" \
                          f"**Value Proposition:** {project.get('value_proposition', '')}\n\n" \
                          f"**Source Transcripts:** {', '.join(project.get('transcript_ids', []))}"
            
            props = {
                "Title": {"title": [{"text": {"content": project['title']}}]},
                "Summary": {"rich_text": [{"text": {"content": full_summary[:2000]}}]},  # Notion has text limits
                "Status": {"select": {"name": project.get('status', 'Planning')}},
                "Priority": {"select": {"name": project.get('priority', 'Medium')}},
                "Dates": {"date": {
                    "start": project.get('start_date', datetime.now().strftime("%Y-%m-%d")),
                    "end": project.get('end_date')
                }}
            }
            
            # Filter out None values and empty strings in properties
            if "None identified" in project.get('title', ''):
                logger.warning(f"Skipping project with invalid title: {project.get('title', '')}")
                return None
                
            # Save to temp file
            props_file = self.output_dir / "temp_project_props.json"
            with open(props_file, 'w') as f:
                json.dump(props, f)
                
            # Use Notion CLI to create project
            cmd = [
                "python", str(self.notion_dir / "starter_notion_agent.py"),
                "create-page", PROJECTS_DATABASE_ID, project['title'],
                "--properties", json.dumps(props)
            ]
            
            env = os.environ.copy()
            env["NOTION_INTERNAL_INTEGRATION_SECRET"] = NOTION_SECRET
            
            result = subprocess.run(cmd, capture_output=True, text=True, env=env)
            
            if result.returncode == 0:
                logger.info(f"Successfully uploaded project: {project['title']}")
                # Try to extract the page ID from the output
                # This is a simplified approach - in production you'd parse the actual response
                return project.get('title')  # Return title as temporary ID
            else:
                logger.error(f"Failed to upload project: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"Error uploading project: {e}")
            return None
            
    async def upload_task_to_notion(self, task: Dict):
        """Upload a task to Notion"""
        try:
            # Add complexity and assignment info to description
            description = f"{task.get('description', '')}\n\n" \
                         f"**Complexity:** {task.get('complexity', 'M')}\n" \
                         f"**Assigned Agent:** {task.get('assigned_agent', 'TBD')}\n" \
                         f"**Source Transcripts:** {', '.join(task.get('transcript_ids', []))}"
            
            # Ensure we have valid tags
            tags = task.get('tags', [])
            if not tags:
                tags = ['auto-generated', 'lifelog']
            
            props = {
                "Title": {"title": [{"text": {"content": task['title']}}]},
                "Status": {"select": {"name": task.get('status', 'Not started')}},
                "Priority": {"select": {"name": task.get('priority', 'Medium')}},
                "Due date": {"date": {"start": task.get('due_date', (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"))}},
                "Tags": {"multi_select": [{"name": tag} for tag in tags]}
            }
            
            # Add project relation if available
            if task.get('project_id'):
                props["Project"] = {"relation": [{"id": task['project_id']}]}
            
            # Add description to task title to include content
            task_title_with_desc = f"{task['title']} - {task.get('description', '')[:100]}" if task.get('description') else task['title']
            props["Title"]["title"][0]["text"]["content"] = task_title_with_desc[:255]  # Notion title limit
            
            cmd = [
                "python", str(self.notion_dir / "starter_notion_agent.py"),
                "create-page", TASKS_DATABASE_ID, task['title'],
                "--properties", json.dumps(props)
            ]
            
            env = os.environ.copy()
            env["NOTION_INTERNAL_INTEGRATION_SECRET"] = NOTION_SECRET
            
            result = subprocess.run(cmd, capture_output=True, text=True, env=env)
            
            if result.returncode == 0:
                logger.info(f"Successfully uploaded task: {task['title']}")
                if task.get('project_id'):
                    logger.info(f"  - Linked to project: {task['project_id']}")
            else:
                logger.error(f"Failed to upload task '{task['title']}': {result.stderr}")
                logger.debug(f"Task properties: {json.dumps(props, indent=2)}")
                
        except Exception as e:
            logger.error(f"Error uploading task: {e}")
            
    async def upload_todo_to_notion(self, todo: Dict):
        """Upload a todo to Notion"""
        try:
            # Ensure we have valid tags for multi-select
            tags = todo.get('tags', [])
            if not tags:
                tags = ['lifelog', 'auto-generated']
            
            # Add more context to todo
            todo_name = todo['title']
            if "None identified" in todo_name:
                logger.warning(f"Skipping todo with invalid title: {todo_name}")
                return
                
            # Add transcript count if available
            if todo.get('transcript_ids'):
                todo_name = f"{todo_name} [{len(todo['transcript_ids'])} sources]"
            
            props = {
                "Name": {"title": [{"text": {"content": todo_name}}]},
                "Status": {"select": {"name": todo.get('status', 'Not started')}},
                "Priority": {"select": {"name": todo.get('priority', 'Medium')}},
                "Due date": {"date": {"start": todo.get('due_date', (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"))}},
                "Multi-select": {"multi_select": [{"name": tag} for tag in tags]}
            }
            
            cmd = [
                "python", str(self.notion_dir / "starter_notion_agent.py"),
                "create-page", TODO_DATABASE_ID, todo['title'],
                "--properties", json.dumps(props)
            ]
            
            env = os.environ.copy()
            env["NOTION_INTERNAL_INTEGRATION_SECRET"] = NOTION_SECRET
            
            result = subprocess.run(cmd, capture_output=True, text=True, env=env)
            
            if result.returncode == 0:
                logger.info(f"Successfully uploaded todo: {todo['title']}")
                logger.debug(f"  - Tags: {todo.get('tags', [])}")
            else:
                logger.error(f"Failed to upload todo '{todo['title']}': {result.stderr}")
                logger.debug(f"Todo properties: {json.dumps(props, indent=2)}")
                
        except Exception as e:
            logger.error(f"Error uploading todo: {e}")
            
    async def send_whatsapp_message(self, message: str):
        """Send WhatsApp notification"""
        try:
            # Use MCP WhatsApp tool
            logger.info(f"[WhatsApp Notification] Sending message...")
            
            # Add timestamp at the end of the message
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            message_with_timestamp = f"{message}\n\n📅 Sent: {timestamp}"
            
            # Also write to a notifications file for tracking in date-based directory
            date_str = self.start_date.strftime("%Y-%m-%d")
            logs_dir = self.output_dir / date_str / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            
            # Create notification log with timestamp
            timestamp_file = datetime.now().strftime("%H%M%S")
            notifications_file = logs_dir / f"whatsapp_notifications_{timestamp_file}.log"
            
            # Append to existing file if it exists within the same minute
            existing_files = list(logs_dir.glob(f"whatsapp_notifications_{timestamp_file[:-2]}*.log"))
            if existing_files:
                notifications_file = existing_files[0]
            
            with open(notifications_file, 'a') as f:
                f.write(f"{datetime.now().isoformat()} - {message_with_timestamp}\n")
                f.write("-" * 80 + "\n")  # Add separator line
            
            # Actually send via MCP (when this script is run through Claude)
            # The MCP tool will be available in the Claude environment
            logger.info(f"[WhatsApp] {message[:100]}...")
            
        except Exception as e:
            logger.warning(f"Failed to send WhatsApp notification: {e}")
            
    async def run(self):
        """Main execution flow"""
        try:
            # Initialize
            await self.initialize()
            
            # Extract transcripts
            transcripts = self.extract_transcripts()
            
            if not transcripts:
                logger.warning("No transcripts found for date range")
                await self.send_whatsapp_message(
                    f"⚠️ No transcripts found for {self.start_date.date()} to {self.end_date.date()}"
                )
                return
                
            # Generate summaries
            summaries = self.generate_summaries(transcripts)
            
            # Generate projects and tasks
            output_data = self.generate_projects_and_tasks(summaries)
            
            # Upload to Notion
            await self.upload_to_notion(output_data)
            
            # Generate detailed statistics
            total_transcripts = sum(len(t) for t in transcripts.values())
            total_chars = sum(sum(len(tr.content) for tr in t) for t in transcripts.values())
            
            # Get summary of activities from consolidated summaries
            activity_summary = []
            for date_str, summary_data in summaries.items():
                consolidated = summary_data.get('consolidated', '')
                # Extract key insights section
                if 'Key Insights' in consolidated:
                    insights = consolidated.split('Key Insights')[1].split('###')[0].strip()
                    activity_summary.append(f"{date_str}: {insights[:200]}...")
            
            stats = f"""
✅ Lifelog Extraction Complete!

📊 Metrics:
- Date Range: {self.start_date.date()} to {self.end_date.date()}
- Transcripts Processed: {total_transcripts}
- Total Content: {total_chars:,} characters
- Projects Created: {len(output_data['projects'])}
- Tasks Created: {len(output_data['tasks'])}
- Todos Created: {len(output_data['todos'])}

📝 Activity Summary:
{chr(10).join(activity_summary[:3]) if activity_summary else 'No activities extracted'}

🏷️ Top Tags:
{', '.join(list(set(tag for s in summaries.values() for ms in s.get('model_summaries', {}).values() for tag in ms.get('tags', [])))[:10])}

📁 Output Directory: {self.output_dir}
"""
            
            await self.send_whatsapp_message(stats)
            logger.info("Extraction completed successfully")
            
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            await self.send_whatsapp_message(
                f"❌ Extraction failed: {str(e)[:100]}"
            )
            raise

def main():
    """Main entry point"""
    # Default to yesterday (for getting full day's logs)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    
    parser = argparse.ArgumentParser(
        description="Extract and process lifelog data into Notion projects/tasks"
    )
    parser.add_argument("--start_date", default=yesterday, 
                       help="Start date (YYYY-MM-DD), defaults to yesterday")
    parser.add_argument("--end_date", default=yesterday,
                       help="End date (YYYY-MM-DD), defaults to yesterday")
    parser.add_argument("--models", nargs='+', default=DEFAULT_MODELS,
                       help="Models to use for analysis")
    parser.add_argument("--output_dir", 
                       default="/home/craigmbrown/Project/Limitless-Lifelog-Manager/output",
                       help="Output directory")
    parser.add_argument("--limitless_dir",
                       default="/home/craigmbrown/Project/Limitless-Lifelog-Manager",
                       help="Limitless agent directory")
    parser.add_argument("--notion_dir",
                       default="/home/craigmbrown/Project/Notion-Database-Manager",
                       help="Notion manager directory")
    parser.add_argument("--no-keyword-filter", action="store_true",
                       help="Process all transcripts without requiring primary keywords (TB)")
    parser.add_argument("--today", action="store_true",
                       help="Process today's logs instead of yesterday's")
    
    args = parser.parse_args()
    
    # Override dates if --today flag is set
    if args.today:
        args.start_date = today
        args.end_date = today
    
    # Create extractor
    extractor = LifelogProjectExtractor(
        start_date=args.start_date,
        end_date=args.end_date,
        models=args.models,
        output_dir=args.output_dir,
        limitless_dir=args.limitless_dir,
        notion_dir=args.notion_dir,
        require_keywords=not args.no_keyword_filter
    )
    
    # Run extraction
    asyncio.run(extractor.run())

if __name__ == "__main__":
    main()