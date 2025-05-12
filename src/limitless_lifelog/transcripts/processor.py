"""
Transcript processing module for Limitless Lifelog.
"""

import os
import json
import glob
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger

class TranscriptProcessor:
    """
    Handles transcript processing, filtering, and summarization.
    
    Uses LLM APIs for advanced analysis and summarization.
    """
    
    def __init__(self, llm_provider: str = "openai", llm_model: str = "gpt-4", keywords_config_path: str = None):
        """
        Initialize transcript processor.

        Args:
            llm_provider: Provider for LLM processing ("openai" or "anthropic")
            llm_model: Model to use for processing
            keywords_config_path: Path to custom keywords configuration file
        """
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.archive_dir = "./transcripts_archive"  # Default archive directory
        self.keywords_config_path = keywords_config_path

    def set_archive_dir(self, directory: str):
        """
        Set the directory for archiving transcripts.

        Args:
            directory: Path to the archive directory
        """
        self.archive_dir = directory
        logger.debug(f"Set archive directory to: {directory}")
        
        # Initialize appropriate client based on provider
        if self.llm_provider == "openai":
            import openai
            self.client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        elif self.llm_provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        else:
            logger.error(f"Unsupported LLM provider: {self.llm_provider}")
            self.client = None
    
    def filter_transcripts(self, transcripts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter transcripts to remove nonsensical or irrelevant content.

        Args:
            transcripts: List of transcript dictionaries

        Returns:
            Filtered list of transcripts
        """
        filtered_transcripts = []

        # Load configurable keywords from config
        from ..utils.keywords_config import KeywordsConfig

        # Initialize keywords configuration with custom path if provided
        keywords_config = KeywordsConfig(self.keywords_config_path)

        # Get keywords from configuration
        action_keywords = keywords_config.get_action_keywords()
        priority_keywords = keywords_config.get_priority_keywords()
        status_keywords = keywords_config.get_status_keywords()
        date_keywords = keywords_config.get_date_keywords()

        # Special keywords that need context extraction
        special_keywords = ["TB", "TeeBee"]

        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")

        for transcript in transcripts:
            content = transcript.get("content", "")
            transcript_id = transcript.get("id", "unknown")
            created_at = transcript.get("created_at", current_date)

            # Basic filters
            if not content:
                logger.debug(f"Skipping empty transcript: {transcript_id}")
                continue

            if len(content) < 50:
                logger.debug(f"Skipping short transcript: {transcript_id}")
                continue

            # Look for action keywords
            has_action_keywords = False
            tb_context = None

            # Add structured details to transcript with much more contextual information
            transcript_details = {
                "content": content,
                "created_at": created_at,
                "context": "",
                "priority_indicators": [],
                "status_indicators": [],
                "date_indicators": [],
                "keywords": [],
                "word_count": len(content.split()),
                "transcript_date": created_at,
                "processed_date": current_date,
                "importance_level": "medium",  # default, may be updated later
                "source_type": "voice_transcript",
                "transcript_id": transcript_id
            }

            # Check for priority indicators in content
            for priority, keywords in priority_keywords.items():
                for keyword in keywords:
                    if keyword.lower() in content.lower():
                        # Find the keyword in context
                        keyword_lower = keyword.lower()
                        content_lower = content.lower()
                        idx = content_lower.find(keyword_lower)
                        start = max(0, idx - 15)
                        end = min(len(content), idx + len(keyword) + 15)
                        keyword_context = content[start:end]

                        transcript_details["priority_indicators"].append({
                            "priority": priority,
                            "keyword": keyword,
                            "context": keyword_context
                        })

                        # If high priority, update importance level
                        if priority.lower() == "high":
                            transcript_details["importance_level"] = "high"

                        # Add to general keywords list
                        if keyword not in transcript_details["keywords"]:
                            transcript_details["keywords"].append(keyword)

            # Check for status indicators in content
            for status, keywords in status_keywords.items():
                for keyword in keywords:
                    if keyword.lower() in content.lower():
                        # Find the keyword in context
                        keyword_lower = keyword.lower()
                        content_lower = content.lower()
                        idx = content_lower.find(keyword_lower)
                        start = max(0, idx - 15)
                        end = min(len(content), idx + len(keyword) + 15)
                        keyword_context = content[start:end]

                        transcript_details["status_indicators"].append({
                            "status": status,
                            "keyword": keyword,
                            "context": keyword_context
                        })

                        # Add to general keywords list
                        if keyword not in transcript_details["keywords"]:
                            transcript_details["keywords"].append(keyword)

            # Date keywords already loaded from configuration

            for date_keyword in date_keywords:
                if date_keyword.lower() in content.lower():
                    # Find the keyword in context
                    keyword_lower = date_keyword.lower()
                    content_lower = content.lower()
                    idx = content_lower.find(keyword_lower)
                    start = max(0, idx - 15)
                    end = min(len(content), idx + len(date_keyword) + 15)
                    date_context = content[start:end]

                    transcript_details["date_indicators"].append({
                        "date": date_keyword,
                        "text": date_context,
                        "position": idx
                    })

                    # Add to general keywords list
                    if date_keyword not in transcript_details["keywords"]:
                        transcript_details["keywords"].append(date_keyword)

            # Special action keywords collection will store all found keywords for analysis
            found_action_keywords = []

            for keyword in action_keywords:
                keyword_lower = keyword.lower()
                content_lower = content.lower()

                if keyword_lower in content_lower:
                    has_action_keywords = True
                    logger.debug(f"Found action keyword '{keyword}' in transcript {transcript_id}")

                    # Add to list of found keywords
                    found_action_keywords.append(keyword)

                    # Add to general keywords list
                    if keyword not in transcript_details["keywords"]:
                        transcript_details["keywords"].append(keyword)

                    # Special handling for TB/TeeBee markers
                    if keyword in special_keywords:
                        # Extract context (100 chars before and after)
                        idx = content_lower.find(keyword_lower)
                        start = max(0, idx - 150)
                        end = min(len(content), idx + len(keyword) + 150)

                        # Store context with the TB marker highlighted
                        context_before = content[start:idx]
                        context_after = content[idx+len(keyword):end]
                        tb_context = {
                            "keyword": keyword,
                            "position": idx,
                            "before": context_before,
                            "after": context_after,
                            "full_context": f"{context_before}[{keyword}]{context_after}"
                        }
                        logger.info(f"Found special keyword '{keyword}' with context: {tb_context['full_context']}")

                        # Add marker to transcript for later processing
                        if "extracted_markers" not in transcript:
                            transcript["extracted_markers"] = []
                        transcript["extracted_markers"].append(tb_context)

                        # Add to transcript details
                        transcript_details["context"] = tb_context["full_context"]

                        # Special keywords automatically make this high importance
                        transcript_details["importance_level"] = "high"

                    # Extract context around any action keyword (not just special ones)
                    # This provides better context for all actionable items
                    idx = content_lower.find(keyword_lower)
                    start = max(0, idx - 100)
                    end = min(len(content), idx + len(keyword) + 100)
                    keyword_context = content[start:end]

                    # Only add if not already set by TB/TeeBee marker
                    if not transcript_details["context"]:
                        transcript_details["context"] = keyword_context

                    # For special keywords we continue looking for more keywords
                    if keyword not in special_keywords:
                        # Don't always break on first keyword - look for multiple keywords
                        # if we already have at least 3 keywords, then we can break
                        if len(found_action_keywords) >= 3:
                            break

            # Always log the full content in verbose mode
            logger.debug(f"Transcript {transcript_id} content: {content[:200]}...")

            # Determine importance based on number of action keywords
            if len(found_action_keywords) >= 3 and transcript_details["importance_level"] != "high":
                transcript_details["importance_level"] = "medium-high"

            # Add all found action keywords to the transcript details
            if found_action_keywords:
                transcript_details["action_keywords"] = found_action_keywords

            # Check if transcript is relevant using LLM or keywords
            is_relevant = has_action_keywords or self._check_relevance(transcript)

            if is_relevant:
                logger.info(f"Including relevant transcript: {transcript_id}")
                # Add transcript details for rich Notion entries
                transcript["transcript_details"] = transcript_details
                filtered_transcripts.append(transcript)
            else:
                logger.debug(f"Filtered out irrelevant transcript: {transcript_id}")

        # Archive transcripts with special markers
        self._archive_marked_transcripts(filtered_transcripts)

        return filtered_transcripts

    def _archive_marked_transcripts(self, transcripts: List[Dict[str, Any]]) -> None:
        """
        Archive transcripts that have special TB/TeeBee markers.

        Args:
            transcripts: List of transcript dictionaries
        """
        import os
        import json
        from datetime import datetime
        from pathlib import Path

        # Create an archive directory if it doesn't exist
        archive_dir = Path(self.archive_dir)
        archive_dir.mkdir(exist_ok=True)

        # Process each transcript
        for transcript in transcripts:
            # Only archive transcripts with extracted markers
            if "extracted_markers" in transcript and transcript["extracted_markers"]:
                transcript_id = transcript.get("id", "unknown")

                # Create a dated directory structure
                today = datetime.now().strftime("%Y-%m-%d")
                date_dir = archive_dir / today
                date_dir.mkdir(exist_ok=True)

                # Create filename with timestamp
                timestamp = datetime.now().strftime("%H%M%S")
                filename = f"{timestamp}_{transcript_id}_TB.json"

                # Prepare archive data
                archive_data = {
                    "transcript_id": transcript_id,
                    "content": transcript.get("content", ""),
                    "extracted_markers": transcript.get("extracted_markers", []),
                    "archived_at": datetime.now().isoformat(),
                    "metadata": {k: v for k, v in transcript.items() if k not in ["content", "extracted_markers"]}
                }

                # Write to file
                file_path = date_dir / filename
                try:
                    with open(file_path, 'w') as f:
                        json.dump(archive_data, f, indent=2)
                    logger.info(f"Archived transcript with TB markers to {file_path}")
                except Exception as e:
                    logger.error(f"Failed to archive transcript {transcript_id}: {e}")

    def archive_all_transcripts(self, transcripts: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Archive all transcripts to the file system (not just marked ones).

        This creates a complete transcript library for reference and prevents
        duplicate downloads by tracking which ones have been processed.

        Args:
            transcripts: List of transcript dictionaries

        Returns:
            Dictionary mapping transcript IDs to their archive paths
        """
        import os
        import json
        from datetime import datetime
        from pathlib import Path

        # Create archive directories
        archive_dir = Path(self.archive_dir)
        archive_dir.mkdir(exist_ok=True)

        # Create a transcripts directory for all transcripts
        transcripts_dir = archive_dir / "transcripts"
        transcripts_dir.mkdir(exist_ok=True)

        # Create an index file to track what's been downloaded
        index_file = archive_dir / "transcript_index.json"

        # Load existing index if it exists
        transcript_index = {}
        if index_file.exists():
            try:
                with open(index_file, 'r') as f:
                    transcript_index = json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Could not parse transcript index, recreating")
                transcript_index = {}

        # Track which files we processed in this run
        processed_files = {}

        # Process each transcript
        for transcript in transcripts:
            transcript_id = transcript.get("id", "unknown")

            # Skip if already archived unless force flag is set
            if transcript_id in transcript_index and not getattr(self, 'force_archive', False):
                logger.debug(f"Transcript {transcript_id} already archived, skipping")
                processed_files[transcript_id] = transcript_index[transcript_id]
                continue

            # Create filename based on ID and date
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"{timestamp}_{transcript_id}.json"
            file_path = transcripts_dir / filename

            # Copy transcript details data
            transcript_details = transcript.get("transcript_details", {})

            # Prepare archive data
            archive_data = {
                "transcript_id": transcript_id,
                "content": transcript.get("content", ""),
                "transcript_details": transcript_details,
                "archived_at": datetime.now().isoformat(),
                "metadata": {k: v for k, v in transcript.items()
                          if k not in ["content", "transcript_details"]}
            }

            # Write to file
            try:
                with open(file_path, 'w') as f:
                    json.dump(archive_data, f, indent=2)
                logger.info(f"Archived transcript {transcript_id} to {file_path}")

                # Update index
                transcript_index[transcript_id] = str(file_path)
                processed_files[transcript_id] = str(file_path)
            except Exception as e:
                logger.error(f"Failed to archive transcript {transcript_id}: {e}")

        # Save updated index
        try:
            with open(index_file, 'w') as f:
                json.dump(transcript_index, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save transcript index: {e}")

        return processed_files
    
    def _check_relevance(self, transcript: Dict[str, Any]) -> bool:
        """
        Check if a transcript is relevant for processing.
        
        Args:
            transcript: Transcript dictionary
            
        Returns:
            True if relevant, False otherwise
        """
        # For testing/demo purposes, consider all transcripts relevant
        # In production, this would use the LLM to check relevance
        return True
    
    def generate_summary(self, transcript: Dict[str, Any]) -> str:
        """
        Generate a concise summary of the transcript content.
        
        Args:
            transcript: Transcript dictionary
            
        Returns:
            Summarized text
        """
        content = transcript.get("content", "")
        
        if not content or self.client is None:
            return ""
        
        try:
            if self.llm_provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.llm_model,
                    messages=[
                        {"role": "system", "content": "You are a summarization assistant. Create a concise summary of the following text."},
                        {"role": "user", "content": content}
                    ],
                    max_tokens=150
                )
                return response.choices[0].message.content.strip()
                
            elif self.llm_provider == "anthropic":
                response = self.client.messages.create(
                    model=self.llm_model,
                    max_tokens=150,
                    messages=[
                        {"role": "user", "content": f"Please provide a concise summary of the following text:\n\n{content}"}
                    ]
                )
                return response.content[0].text.strip()
                
            else:
                logger.error(f"Unsupported LLM provider: {self.llm_provider}")
                return ""
                
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return ""
    
    def load_from_path(self, path: str) -> List[Dict[str, Any]]:
        """
        Load transcripts from file or directory.
        
        Args:
            path: Path to transcript file or directory of files
            
        Returns:
            List of transcript dictionaries
        """
        if not Path(path).exists():
            logger.error(f"Path does not exist: {path}")
            return []
            
        transcripts = []
        
        # Handle directory
        if Path(path).is_dir():
            for json_file in glob.glob(os.path.join(path, "*.json")):
                file_transcripts = self._load_transcript_file(json_file)
                transcripts.extend(file_transcripts)
                
        # Handle single file
        elif Path(path).is_file():
            file_transcripts = self._load_transcript_file(path)
            transcripts.extend(file_transcripts)
            
        return transcripts
                
    def _load_transcript_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Load transcripts from a JSON file.
        
        Args:
            file_path: Path to JSON file
            
        Returns:
            List of transcript dictionaries
        """
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            # Handle different file formats
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "transcripts" in data:
                return data["transcripts"]
            elif isinstance(data, dict):
                # Single transcript in file
                return [data]
            else:
                logger.warning(f"Unexpected format in {file_path}")
                return []
                
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading transcript file {file_path}: {e}")
            return []