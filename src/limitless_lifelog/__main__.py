"""
Main entry point for limitless-lifelog.
"""

import argparse
import os
import sys
import datetime
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

from .utils.config import Config
from .utils.state_manager import StateManager
from .limitless.api_client import LimitlessClient
from .transcripts.processor import TranscriptProcessor
from .transcripts.extractor import ItemExtractor
from .transcripts.transformer import DataTransformer
from .notion.client import NotionClient

# Load environment variables
load_dotenv()

def configure_logging(log_level="INFO", log_file=None):
    """Configure logging based on verbosity level."""
    logger.remove()  # Remove default handler
    
    # Add console handler
    logger.add(sys.stderr, level=log_level)
    
    # Add file handler if specified
    if log_file:
        log_path = Path("logs") / log_file
        log_path.parent.mkdir(exist_ok=True)
        logger.add(log_path, rotation="10 MB", retention="1 month", level=log_level)

def main():
    """
    Main entry point for limitless-lifelog.
    """
    parser = argparse.ArgumentParser(
        description="Limitless Lifelog - Process voice transcripts and integrate with Notion"
    )
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Download transcripts without Notion updates"
    )
    parser.add_argument(
        "--process-only",
        action="store_true",
        help="Process existing transcripts without fetching new ones"
    )
    parser.add_argument(
        "--days",
        type=int,
        help="Process logs from the past N days (default: since last run)"
    )
    parser.add_argument(
        "--config",
        help="Specify configuration file path"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed logging"
    )
    parser.add_argument(
        "--show-content",
        action="store_true",
        help="Show full transcript content in logs"
    )
    parser.add_argument(
        "--archive-dir",
        default="./transcripts_archive",
        help="Directory to save archived transcripts (default: ./transcripts_archive)"
    )
    parser.add_argument(
        "--force-archive",
        action="store_true",
        help="Force archiving of transcripts even if they've been downloaded before"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--transcripts-path",
        help="Process transcripts from a specific file or directory"
    )
    parser.add_argument(
        "--llm-provider",
        choices=["openai", "anthropic"],
        help="Specify which LLM provider to use"
    )
    parser.add_argument(
        "--api-url",
        help="Override the Limitless API URL"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)"
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Maximum number of retries for failed requests (default: 3)"
    )
    parser.add_argument(
        "--auth-method",
        choices=["all", "bearer", "api_key"],
        default="all",
        help="Authentication method to use (default: all)"
    )
    parser.add_argument(
        "--assignee",
        default="",
        help="Default assignee for tasks and todos (default is blank)"
    )
    parser.add_argument(
        "--skip-processed",
        action="store_true",
        help="Skip transcripts that have already been processed according to archive index"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock data instead of making API calls"
    )
    parser.add_argument(
        "--keywords-config",
        help="Path to custom keywords configuration file"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = "DEBUG" if args.verbose else "INFO"
    configure_logging(log_level, log_file="lifelog.log")
    
    logger.info("Starting Limitless Lifelog v{}", __import__("limitless_lifelog").__version__)
    
    try:
        # Load configuration
        config = Config(args.config)

        # Override API URL if provided
        if args.api_url:
            config.limitless_api_url = args.api_url
            logger.info(f"Using overridden API URL: {config.limitless_api_url}")

        # Initialize state manager
        state_manager = StateManager()
        last_run_time = state_manager.get_last_run_time()
        
        if args.days:
            # Override last run time if days argument is provided
            last_run_time = datetime.datetime.now() - datetime.timedelta(days=args.days)
            logger.info("Processing transcripts from the past {} days", args.days)
        elif last_run_time:
            logger.info("Processing transcripts since {}", last_run_time)
        else:
            logger.info("No previous run detected, processing all available transcripts")
        
        # Initialize clients and processors
        limitless_client = LimitlessClient(
            api_key=config.limitless_api_key,
            base_url=config.limitless_api_url,
            timeout=args.timeout,
            max_retries=args.retries,
            auth_method=args.auth_method,
            force_mock=args.mock
        )
        notion_client = NotionClient(config.notion_api_key, config.notion_database_ids)

        # Initialize processors with keywords config if provided
        transcript_processor = TranscriptProcessor(
            config.llm_provider,
            config.llm_model,
            keywords_config_path=args.keywords_config
        )
        item_extractor = ItemExtractor(config.llm_provider, config.llm_model)
        data_transformer = DataTransformer(notion_client=notion_client, keywords_config_path=args.keywords_config)
        
        # Get or process transcripts
        transcripts = []
        
        if not args.process_only:
            logger.info("Fetching transcripts from Limitless API")
            transcripts = limitless_client.fetch_transcripts(last_run_time)
            logger.info("Retrieved {} transcripts", len(transcripts))
        
        if args.transcripts_path:
            logger.info("Loading transcripts from {}", args.transcripts_path)
            file_transcripts = transcript_processor.load_from_path(args.transcripts_path)
            transcripts.extend(file_transcripts)
            logger.info("Loaded {} additional transcripts from files", len(file_transcripts))
        
        if not transcripts:
            logger.warning("No transcripts to process")
            return
        
        # Process transcripts
        logger.info("Processing {} transcripts", len(transcripts))

        # Pass archive directory to processor if specified
        if args.archive_dir:
            transcript_processor.set_archive_dir(args.archive_dir)

        # Set force archive flag if specified
        if args.force_archive:
            transcript_processor.force_archive = True

        # Skip already processed transcripts if requested
        if args.skip_processed:
            # Load the transcript index
            from pathlib import Path
            import json

            index_file = Path(args.archive_dir) / "transcript_index.json"
            transcript_index = {}

            if index_file.exists():
                try:
                    with open(index_file, 'r') as f:
                        transcript_index = json.load(f)
                    logger.info(f"Loaded transcript index with {len(transcript_index)} entries")
                except json.JSONDecodeError:
                    logger.error(f"Could not parse transcript index")

            # Filter out already processed transcripts
            original_count = len(transcripts)
            transcripts = [t for t in transcripts if t.get("id", "unknown") not in transcript_index]
            logger.info(f"Filtered out {original_count - len(transcripts)} already processed transcripts")

        # Allow showing full content in logs
        if args.show_content and transcripts:
            for i, transcript in enumerate(transcripts[:5]):  # Show first 5 only to avoid log flooding
                content = transcript.get("content", "")
                if not content and "contents" in transcript:
                    # Extract content from contents array if needed
                    contents = transcript.get("contents", [])
                    if contents and isinstance(contents, list) and len(contents) > 0:
                        content_item = contents[0]
                        if isinstance(content_item, dict) and "content" in content_item:
                            content = content_item["content"]
                        elif isinstance(content_item, str):
                            content = content_item

                logger.info(f"Transcript {i+1} content: {content[:500]}...")
                if i >= 4 and len(transcripts) > 5:
                    logger.info(f"... and {len(transcripts) - 5} more transcripts")

        # Filter transcripts for relevance
        filtered_transcripts = transcript_processor.filter_transcripts(transcripts)
        logger.info("{} transcripts remain after filtering", len(filtered_transcripts))

        # Archive all processed transcripts for future reference
        if not args.dry_run:
            archived_files = transcript_processor.archive_all_transcripts(filtered_transcripts)
            logger.info(f"Archived {len(archived_files)} transcripts to the file system")

        # Extract items
        extracted_items = item_extractor.extract_items(filtered_transcripts)
        logger.info("Extracted {} actionable items", sum(len(items) for items in extracted_items.values()))

        # Transform data for Notion with default assignee if provided
        data_transformer.default_assignee = args.assignee
        notion_data = data_transformer.transform(extracted_items)
        
        # Update Notion if not fetch-only and not dry-run
        if not args.fetch_only and not args.dry_run:
            logger.info("Updating Notion databases")
            result = notion_client.update_databases(notion_data)
            logger.info("Notion update completed: {}", result)
        elif args.dry_run:
            logger.info("Dry run: would update Notion with {} items", 
                      sum(len(items) for items in notion_data.values()))
        
        # Update state with current time
        if not args.dry_run:
            state_manager.set_last_run_time()
            logger.info("Updated last run timestamp")
        
        logger.info("Process completed successfully")
        
    except Exception as e:
        logger.exception(f"Error in execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()