#!/usr/bin/env python3
"""
Test script to check Limitless API connectivity and available lifelogs
"""

import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_limitless_api():
    """Test the Limitless API and list available lifelogs"""
    
    # Get API key
    api_key = os.environ.get("LIMITLESS_API_KEY", "")
    
    if not api_key:
        print("ERROR: No LIMITLESS_API_KEY found in environment")
        return
    
    print(f"Using API key: {api_key[:10]}...{api_key[-4:]}")
    
    # Test both endpoints
    print("Testing both v1/lifelogs and v1/transcripts endpoints...")
    
    # Test the v1/lifelogs endpoint
    url = "https://api.limitless.ai/v1/lifelogs"
    
    headers = {
        "X-API-Key": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # First, list all lifelogs without date filter
    print("\n1. Testing list all lifelogs...")
    params = {
        "limit": 10,
        "direction": "desc"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            lifelogs = data.get("lifelogs", [])
            print(f"Found {len(lifelogs)} lifelogs")
            
            # Show dates of lifelogs
            print("\nLifelog dates:")
            for log in lifelogs:
                start_time = log.get('startTime', 'Unknown')
                log_id = log.get('id', 'Unknown')
                title = log.get('title', 'No title')
                print(f"  - {start_time}: {title} (ID: {log_id})")
                
            # Check cursor for pagination
            cursor = data.get("cursor")
            if cursor:
                print(f"\nMore logs available. Next cursor: {cursor}")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")
    
    # Test with specific date
    print("\n2. Testing with specific date (yesterday)...")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    params = {
        "date": yesterday,
        "limit": 10
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            lifelogs = data.get("lifelogs", [])
            print(f"Found {len(lifelogs)} lifelogs for {yesterday}")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")
    
    # Test fetching a specific lifelog
    print("\n3. Testing get specific lifelog...")
    if 'lifelogs' in locals() and lifelogs:
        test_id = lifelogs[0].get('id')
        if test_id:
            url = f"https://api.limitless.ai/v1/lifelogs/{test_id}"
            
            try:
                response = requests.get(url, headers=headers, timeout=30)
                print(f"Response status: {response.status_code}")
                
                if response.status_code == 200:
                    lifelog = response.json()
                    print(f"Successfully fetched lifelog {test_id}")
                    print(f"Title: {lifelog.get('title', 'No title')}")
                    print(f"Has markdown: {'markdown' in lifelog}")
                    if 'markdown' in lifelog:
                        print(f"Markdown length: {len(lifelog['markdown'])} chars")
                else:
                    print(f"Error: {response.text}")
                    
            except Exception as e:
                print(f"Exception: {e}")

    # Also test the transcripts endpoint
    print("\n4. Testing v1/transcripts endpoint...")
    url = "https://api.limitless.ai/v1/transcripts"
    
    params = {
        "limit": 10
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            transcripts = data.get("transcripts", data.get("data", []))
            print(f"Found {len(transcripts) if isinstance(transcripts, list) else 'unknown'} transcripts")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_limitless_api()