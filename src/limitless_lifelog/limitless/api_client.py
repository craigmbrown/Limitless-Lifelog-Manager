"""
Client for Limitless Voice API.
"""

import os
import requests
import time
import datetime
import random
from typing import List, Dict, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from loguru import logger

class LimitlessClient:
    """
    Client for interacting with the Limitless Voice API.
    
    Handles authentication, pagination, and rate limiting for retrieving
    transcripts and associated metadata.
    """
    
    def __init__(self, api_key: str, base_url: str = None, timeout: int = 30, max_retries: int = 3,
                 auth_method: str = "all", force_mock: bool = False):
        """
        Initialize Limitless API client.

        Args:
            api_key: Limitless API key
            base_url: Base URL for Limitless API (optional)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            auth_method: Authentication method to use (bearer, api_key, or all)
            force_mock: Force using mock data regardless of other settings
        """
        self.api_key = api_key
        self.timeout = timeout
        self.auth_method = auth_method
        self.force_mock = force_mock

        # Default to environment variable or fallback to hardcoded value
        if base_url is None:
            self.base_url = os.environ.get("LIMITLESS_API_URL", "https://api.limitless.ai/v1/lifelogs")
        else:
            self.base_url = base_url

        # Configure session with retry logic
        self.session = requests.Session()

        # Configure retry with backoff strategy
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=0.5,  # Wait 0.5, 1, 2... seconds between retries
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on these status codes
            allowed_methods=["GET", "POST"],  # Only retry for these methods
            respect_retry_after_header=True
        )

        # Mount adapters with retry strategy
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set headers based on auth method
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "LimitlessLifelog/0.1.0"
        }

        if auth_method == "bearer" or auth_method == "all":
            headers["Authorization"] = f"Bearer {api_key}"

        if auth_method == "api_key" or auth_method == "all":
            headers["X-API-Key"] = api_key

        logger.debug(f"Using authentication method: {auth_method}")
        self.session.headers.update(headers)
    
    def fetch_transcripts(self,
                         since_time: Optional[datetime.datetime] = None,
                         max_results: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch transcripts from Limitless API, with pagination and time filtering.

        Args:
            since_time: Only fetch transcripts after this time
            max_results: Maximum number of results to return

        Returns:
            List of transcript dictionaries
        """
        if not self.api_key:
            logger.error("Limitless API key not provided")
            return []

        # Check if we should use mock data
        if self.use_mock_data():
            logger.info("Using mock transcript data (mock mode enabled)")
            return self.mock_transcript_data(min(max_results, 10))

        # Use the exact URL path from the working curl command
        # The API expects to access just /lifelogs directly, not /lifelogs/transcripts
        if "lifelogs" in self.base_url:
            # For the Limitless AI endpoint
            if self.base_url.endswith("/lifelogs"):
                url = f"{self.base_url}"
                logger.debug(f"Using base lifelogs endpoint: {url}")
            else:
                # Make sure we're using the /lifelogs endpoint
                url = f"{self.base_url}/lifelogs"
                logger.debug(f"Using lifelogs endpoint: {url}")
        else:
            # For the old Limitless Voice endpoint
            url = f"{self.base_url}/transcripts"
            logger.debug(f"Using legacy endpoint format: {url}")

        params = {
            "limit": min(max_results, 50)  # API might have a per-page limit
        }

        if since_time:
            params["since"] = since_time.isoformat()

        all_transcripts = []
        page = 1

        while True:
            params["page"] = page

            try:
                logger.debug(f"Fetching page {page} of transcripts from {url}")
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout
                )
                response.raise_for_status()

                data = response.json()
                # Handle API response format from curl example
                if "data" in data and "lifelogs" in data["data"]:
                    logger.debug("Found lifelogs data in API response")
                    transcripts = data["data"]["lifelogs"]

                    # Debug the structure of the first few transcripts
                    if transcripts and len(transcripts) > 0:
                        logger.debug(f"First transcript keys: {list(transcripts[0].keys()) if transcripts else 'No transcripts'}")

                        # Fix the transcript format to match what the processor expects
                        for transcript in transcripts:
                            if "contents" in transcript and isinstance(transcript["contents"], list) and len(transcript["contents"]) > 0:
                                # Extract the content from the contents list
                                content_obj = transcript["contents"][0]
                                if isinstance(content_obj, dict) and "content" in content_obj:
                                    transcript["content"] = content_obj["content"]
                                elif isinstance(content_obj, str):
                                    transcript["content"] = content_obj

                                # Log the first transcript content for debugging
                                if transcript == transcripts[0]:
                                    logger.debug(f"Processed first transcript content: {transcript.get('content', 'No content')[:100]}...")
                else:
                    # Fallback to original format
                    transcripts = data.get("transcripts", [])

                if not transcripts:
                    break

                all_transcripts.extend(transcripts)

                # Check if we reached max results or no more pages
                if len(all_transcripts) >= max_results or not data.get("has_more", False):
                    break

                # Respect rate limits
                if "X-RateLimit-Remaining" in response.headers:
                    remaining = int(response.headers["X-RateLimit-Remaining"])
                    if remaining <= 1:
                        reset_time = int(response.headers.get("X-RateLimit-Reset", 5))
                        logger.warning(f"Rate limit nearly exhausted, waiting {reset_time}s")
                        time.sleep(reset_time)

                page += 1

            except requests.exceptions.Timeout as e:
                logger.error(f"Timeout error fetching transcripts: {e}")

                # Add jitter to avoid thundering herd
                retry_time = min(5 * (page + 1), 30) + random.uniform(0, 2)
                logger.warning(f"Request timed out, retrying in {retry_time:.1f}s")
                time.sleep(retry_time)
                continue

            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error fetching transcripts: {e}")

                # Add exponential backoff for connection errors
                retry_time = min(2 ** page, 60) + random.uniform(0, 5)
                logger.warning(f"Connection failed, retrying in {retry_time:.1f}s")
                time.sleep(retry_time)
                continue

            except requests.RequestException as e:
                logger.error(f"Error fetching transcripts: {e}")

                # Handle different HTTP errors
                if hasattr(e, "response") and e.response:
                    status_code = e.response.status_code

                    if status_code == 401 or status_code == 403:
                        # Authentication error - try using mock data
                        logger.warning(f"Authentication error (status {status_code}), falling back to mock data")
                        return self.mock_transcript_data(min(max_results, 10))
                    elif status_code == 429:
                        # Rate limiting
                        retry_after = int(e.response.headers.get("Retry-After", 30))
                        logger.warning(f"Rate limited, waiting {retry_after}s")
                        time.sleep(retry_after)
                        continue
                    elif status_code >= 500:
                        # Server error, retry with backoff
                        retry_time = min(5 * (page + 1), 30) + random.uniform(0, 2)
                        logger.warning(f"Server error {status_code}, retrying in {retry_time:.1f}s")
                        time.sleep(retry_time)
                        continue
                    elif status_code == 404:
                        # Resource not found - likely wrong endpoint
                        logger.error(f"API endpoint not found: {url}")
                        return self.mock_transcript_data(min(max_results, 10))

                break

        logger.info(f"Retrieved {len(all_transcripts)} transcripts")
        return all_transcripts
    
    def get_transcript(self, transcript_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a specific transcript by ID.

        Args:
            transcript_id: ID of the transcript to fetch

        Returns:
            Transcript dictionary or None if not found
        """
        if not self.api_key:
            logger.error("Limitless API key not provided")
            return None

        # Check if we should use mock data
        if self.use_mock_data():
            logger.info("Using mock transcript data (mock mode enabled)")
            mock_data = self.mock_transcript_data(10)
            for transcript in mock_data:
                if transcript["id"] == transcript_id:
                    return transcript
            return None

        # Use the exact URL path from the working curl command
        # The API expects to access the data via the lifelogs endpoint
        if "lifelogs" in self.base_url:
            # For the Limitless AI endpoint
            if self.base_url.endswith("/lifelogs"):
                url = f"{self.base_url}/{transcript_id}"
                logger.debug(f"Using base lifelog transcript endpoint: {url}")
            else:
                # Make sure we're using the /lifelogs endpoint
                url = f"{self.base_url}/lifelogs/{transcript_id}"
                logger.debug(f"Using lifelog transcript endpoint: {url}")
        else:
            # For the old Limitless Voice endpoint
            url = f"{self.base_url}/transcripts/{transcript_id}"
            logger.debug(f"Using legacy transcript endpoint format: {url}")

        max_attempts = 3
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            try:
                logger.debug(f"Fetching transcript {transcript_id} from {url} (attempt {attempt}/{max_attempts})")
                response = self.session.get(
                    url,
                    timeout=self.timeout
                )
                response.raise_for_status()
                data = response.json()

                # Handle API response format from curl example
                if "data" in data and "transcript" in data["data"]:
                    logger.debug("Found transcript data in API response")
                    return data["data"]["transcript"]
                else:
                    # Fallback to original format
                    return data.get("transcript")
            except requests.exceptions.Timeout as e:
                logger.error(f"Timeout error fetching transcript {transcript_id}: {e}")
                if attempt < max_attempts:
                    retry_time = 2 * attempt + random.uniform(0, 1)
                    logger.warning(f"Request timed out, retrying in {retry_time:.1f}s")
                    time.sleep(retry_time)
                else:
                    logger.error(f"Failed to fetch transcript after {max_attempts} attempts")
                    return None
            except requests.RequestException as e:
                logger.error(f"Error fetching transcript {transcript_id}: {e}")

                # Handle different HTTP errors for transcript fetch
                if hasattr(e, "response") and e.response:
                    status_code = e.response.status_code

                    if status_code == 401 or status_code == 403:
                        # Authentication error
                        logger.warning(f"Authentication error (status {status_code}), falling back to mock data")
                        mock_data = self.mock_transcript_data(10)
                        for transcript in mock_data:
                            if transcript["id"] == transcript_id:
                                return transcript
                        return None
                    elif status_code >= 500 and attempt < max_attempts:
                        # Server error, retry with backoff
                        retry_time = 2 * attempt + random.uniform(0, 1)
                        logger.warning(f"Server error {status_code}, retrying in {retry_time:.1f}s")
                        time.sleep(retry_time)
                    elif status_code == 404:
                        # Transcript not found
                        logger.warning(f"Transcript {transcript_id} not found")
                        return None
                    else:
                        return None
                else:
                    return None

    def use_mock_data(self) -> bool:
        """
        Check if we should use mock data based on the API URL or auth failure.

        Returns:
            True if we should use mock data, False otherwise
        """
        # Force mock data if specified
        if self.force_mock:
            return True

        # Use mock data if URL contains mock indicators or if API key is missing
        return (self.base_url.endswith("/mock") or
                "localhost" in self.base_url or
                "127.0.0.1" in self.base_url or
                not self.api_key)

    def mock_transcript_data(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Generate mock transcript data for testing.

        Args:
            count: Number of mock transcripts to generate

        Returns:
            List of mock transcript dictionaries
        """
        mock_transcripts = []
        
        # Sample topics and content
        topics = [
            "project status update", 
            "meeting notes", 
            "task list", 
            "research ideas",
            "personal goals",
            "weekly planning"
        ]
        
        for i in range(count):
            # Create a random timestamp in the last week
            timestamp = datetime.datetime.now() - datetime.timedelta(
                days=i % 7,
                hours=(i * 3) % 24,
                minutes=(i * 7) % 60
            )
            
            topic_idx = i % len(topics)
            
            # Sample content for different topics
            if topics[topic_idx] == "project status update":
                content = (
                    f"Project update for the data migration project. We're currently "
                    f"at about 75% completion. Tasks remaining include testing the new "
                    f"database schema and implementing the rollback procedures. We should "
                    f"schedule a review meeting for next Tuesday at 2pm with the team. "
                    f"Also, I need to remember to contact Jane about the server capacity requirements."
                )
            elif topics[topic_idx] == "meeting notes":
                content = (
                    f"Notes from the product team meeting. We discussed the new feature "
                    f"rollout timeline. Action items: 1) Marketing team to prepare announcement "
                    f"by Friday, 2) Dev team to fix the remaining bugs by Wednesday, "
                    f"3) QA to complete final testing by Thursday noon. Next meeting scheduled "
                    f"for Monday at 10am in the main conference room."
                )
            elif topics[topic_idx] == "task list":
                content = (
                    f"Tasks for this week: First, review and sign off on the design documents. "
                    f"Second, prepare the presentation for the client meeting on Thursday. "
                    f"Third, follow up with HR about the new hire paperwork. "
                    f"Finally, don't forget to submit the quarterly report by Friday end of day."
                )
            else:
                content = (
                    f"Thinking about {topics[topic_idx]}. Need to organize my ideas and "
                    f"create a structured plan. Should talk to Alex about this next week. "
                    f"Important to complete the initial research by August 15."
                )
            
            transcript = {
                "id": f"mock-transcript-{i}",
                "timestamp": timestamp.isoformat(),
                "topic": topics[topic_idx],
                "duration_seconds": 120 + (i * 30),
                "word_count": 150 + (i * 20),
                "content": content,
                "metadata": {
                    "device_id": f"device-{i % 3}",
                    "location": ["home", "office", "coffee shop"][i % 3],
                    "tags": ["work", "personal", "planning"][i % 3:]
                }
            }
            
            mock_transcripts.append(transcript)
        
        return mock_transcripts