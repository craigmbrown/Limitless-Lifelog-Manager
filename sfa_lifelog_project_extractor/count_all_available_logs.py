#!/usr/bin/env python3
"""Count all available logs - both from API and local archives"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent / '.env')

def count_all_available_logs():
    """Count logs from both API and local archives"""
    
    print("LIFELOG AVAILABILITY REPORT")
    print("=" * 60)
    
    # 1. Check API
    print("\n1. FROM LIMITLESS API:")
    print("-" * 40)
    
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "Limitless-Lifelog-Manager" / "src"))
        from limitless_lifelog.limitless.api_client import LimitlessClient
        from limitless_lifelog.utils.config import Config
        
        config = Config()
        client = LimitlessClient(
            api_key=config.limitless_api_key or os.environ.get("LIMITLESS_API_KEY", ""),
            base_url=config.limitless_api_url
        )
        
        # Fetch from API
        all_transcripts = client.fetch_transcripts(
            since_time=datetime.now() - timedelta(days=30),
            max_results=1000
        )
        
        # Count by date
        api_dates = {}
        for transcript in all_transcripts:
            timestamp = (transcript.get('startTime') or 
                        transcript.get('timestamp') or 
                        transcript.get('created_at') or
                        transcript.get('endTime', ''))
            
            if timestamp:
                try:
                    if isinstance(timestamp, str):
                        timestamp = timestamp.replace('Z', '+00:00')
                        if timestamp.endswith('+00:00+00:00'):
                            timestamp = timestamp[:-6]
                        trans_datetime = datetime.fromisoformat(timestamp)
                    else:
                        trans_datetime = datetime.fromtimestamp(timestamp)
                    
                    date_str = trans_datetime.strftime("%Y-%m-%d")
                    api_dates[date_str] = api_dates.get(date_str, 0) + 1
                except:
                    pass
        
        print(f"Total from API: {len(all_transcripts)} transcripts")
        for date in sorted(api_dates.keys(), reverse=True):
            print(f"  {date}: {api_dates[date]} transcripts")
            
    except Exception as e:
        print(f"Error accessing API: {e}")
    
    # 2. Check local archives
    print("\n2. FROM LOCAL ARCHIVES:")
    print("-" * 40)
    
    archive_paths = [
        Path("/home/craigmbrown/Project/Limitless-Lifelog-Manager/output"),
        Path("/home/craigmbrown/Project/limitless-lifelog/transcripts_archive"),
        Path("/home/craigmbrown/Project/Limitless-Lifelog-Manager/transcripts_archive")
    ]
    
    local_dates = {}
    total_local = 0
    
    for archive_path in archive_paths:
        if archive_path.exists():
            print(f"\nChecking: {archive_path}")
            
            # Look for date directories
            for date_dir in sorted(archive_path.glob("20*"), reverse=True):
                if date_dir.is_dir():
                    date_str = date_dir.name
                    
                    # Count transcript files
                    transcript_count = 0
                    transcript_dir = date_dir / "transcripts"
                    if transcript_dir.exists():
                        transcript_count = len(list(transcript_dir.glob("transcript-*.md")))
                    else:
                        # Check direct transcript files
                        transcript_count = len(list(date_dir.glob("transcript-*.md")))
                    
                    if transcript_count > 0:
                        local_dates[date_str] = local_dates.get(date_str, 0) + transcript_count
                        total_local += transcript_count
                        print(f"  {date_str}: {transcript_count} transcripts")
    
    # 3. Summary
    print("\n3. COMBINED SUMMARY:")
    print("=" * 60)
    
    all_dates = set(api_dates.keys()) | set(local_dates.keys())
    
    print(f"{'Date':<15} {'API':<10} {'Local':<10} {'Total':<10}")
    print("-" * 45)
    
    for date in sorted(all_dates, reverse=True):
        api_count = api_dates.get(date, 0)
        local_count = local_dates.get(date, 0)
        total = api_count + local_count
        print(f"{date:<15} {api_count:<10} {local_count:<10} {total:<10}")
    
    print("-" * 45)
    print(f"{'TOTAL':<15} {len(all_transcripts):<10} {total_local:<10} {len(all_transcripts) + total_local:<10}")
    
    print("\n4. ANALYSIS:")
    print("-" * 40)
    print(f"Days with data: {len(all_dates)}")
    print(f"Date range: {min(all_dates)} to {max(all_dates)}")
    print("\nNOTE: The Limitless API currently only returns the most recent 25 transcripts.")
    print("Historical data is available in local archives from previous extractions.")

if __name__ == "__main__":
    count_all_available_logs()