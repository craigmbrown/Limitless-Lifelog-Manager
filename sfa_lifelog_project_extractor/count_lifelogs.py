#!/usr/bin/env python3
"""Count available lifelogs without processing them"""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent / '.env')

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent / "Limitless-Lifelog-Manager" / "src"))

from limitless_lifelog.limitless.api_client import LimitlessClient
from limitless_lifelog.utils.config import Config

def count_available_lifelogs(days_back=30):
    """Count available lifelogs for the past N days"""
    try:
        # Initialize config and client
        config = Config()
        client = LimitlessClient(
            api_key=config.limitless_api_key or os.environ.get("LIMITLESS_API_KEY", ""),
            base_url=config.limitless_api_url
        )
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        print(f"Searching for lifelogs from {start_date.date()} to {end_date.date()}")
        print(f"Checking past {days_back} days...\n")
        
        # Fetch all transcripts
        all_transcripts = client.fetch_transcripts(
            since_time=start_date,
            max_results=1000
        )
        
        # Count by date
        transcripts_by_date = {}
        for transcript in all_transcripts:
            # Get timestamp
            timestamp = (transcript.get('startTime') or 
                        transcript.get('timestamp') or 
                        transcript.get('created_at') or
                        transcript.get('endTime', ''))
            
            if timestamp:
                try:
                    # Parse timestamp
                    if isinstance(timestamp, str):
                        timestamp = timestamp.replace('Z', '+00:00')
                        if timestamp.endswith('+00:00+00:00'):
                            timestamp = timestamp[:-6]
                        trans_datetime = datetime.fromisoformat(timestamp)
                    else:
                        trans_datetime = datetime.fromtimestamp(timestamp)
                    
                    date_str = trans_datetime.strftime("%Y-%m-%d")
                    if date_str not in transcripts_by_date:
                        transcripts_by_date[date_str] = []
                    transcripts_by_date[date_str].append(transcript.get('id', 'unknown'))
                except Exception as e:
                    print(f"Warning: Could not parse timestamp: {timestamp}")
        
        # Display results
        print(f"Total transcripts found: {len(all_transcripts)}")
        print(f"Dates with transcripts: {len(transcripts_by_date)}\n")
        
        # Create summary table
        print("=" * 50)
        print("DATE SUMMARY")
        print("=" * 50)
        print(f"{'Date':<15} {'Count':<10} {'Status'}")
        print("-" * 50)
        
        # Show all days in range
        current = start_date.date()
        total_days_with_data = 0
        
        while current <= end_date.date():
            date_str = current.strftime("%Y-%m-%d")
            count = len(transcripts_by_date.get(date_str, []))
            if count > 0:
                total_days_with_data += 1
                status = "✓ Has data"
            else:
                status = "✗ No data"
            print(f"{date_str:<15} {count:<10} {status}")
            current += timedelta(days=1)
        
        print("-" * 50)
        print(f"Days with data: {total_days_with_data}/{days_back}")
        print(f"Total transcripts: {len(all_transcripts)}")
        print("=" * 50)
        
        return len(all_transcripts), transcripts_by_date
        
    except Exception as e:
        print(f"Error counting lifelogs: {e}")
        return 0, {}

if __name__ == "__main__":
    # Check for days argument
    days = 30
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            print("Usage: python count_lifelogs.py [days_back]")
            sys.exit(1)
    
    count, dates = count_available_lifelogs(days)