#!/usr/bin/env python3
"""Debug Limitless API to understand pagination and date filtering"""

import os
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent / '.env')

def debug_limitless_api():
    """Test Limitless API directly"""
    api_key = os.environ.get("LIMITLESS_API_KEY")
    if not api_key:
        print("Error: LIMITLESS_API_KEY not found")
        return
    
    base_url = "https://api.limitless.ai/v1/lifelogs"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-API-Key": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    print("Testing Limitless API...")
    print("=" * 60)
    
    # Test 1: Basic request
    print("\n1. Basic request (no parameters):")
    response = requests.get(base_url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        logs = data.get("data", {}).get("lifelogs", [])
        print(f"   Status: {response.status_code}")
        print(f"   Total logs returned: {len(logs)}")
        print(f"   Has more: {data.get('has_more', 'N/A')}")
        if logs:
            print(f"   First log date: {logs[0].get('startTime', 'N/A')}")
            print(f"   Last log date: {logs[-1].get('startTime', 'N/A')}")
    else:
        print(f"   Error: {response.status_code} - {response.text}")
    
    # Test 2: With since parameter
    print("\n2. With 'since' parameter (5 days ago):")
    since_date = (datetime.now() - timedelta(days=5)).isoformat()
    params = {"since": since_date}
    response = requests.get(base_url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        logs = data.get("data", {}).get("lifelogs", [])
        print(f"   Status: {response.status_code}")
        print(f"   Since date: {since_date}")
        print(f"   Total logs returned: {len(logs)}")
        print(f"   Request URL: {response.url}")
    else:
        print(f"   Error: {response.status_code} - {response.text}")
    
    # Test 3: With limit parameter
    print("\n3. With 'limit' parameter:")
    for limit in [10, 50, 100]:
        params = {"limit": limit}
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            logs = data.get("data", {}).get("lifelogs", [])
            print(f"   Limit={limit}: Got {len(logs)} logs")
        else:
            print(f"   Limit={limit}: Error {response.status_code}")
    
    # Test 4: Different pagination approaches
    print("\n4. Testing pagination approaches:")
    
    # 4a. Using offset
    print("   4a. Using offset parameter:")
    for offset in [0, 25, 50]:
        params = {"limit": 25, "offset": offset}
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            logs = data.get("data", {}).get("lifelogs", [])
            print(f"      Offset={offset}: Got {len(logs)} logs")
        else:
            print(f"      Offset={offset}: Error {response.status_code}")
    
    # 4b. Using cursor/after
    print("   4b. Using cursor-based pagination:")
    all_logs = []
    cursor = None
    for i in range(3):
        params = {"limit": 25}
        if cursor:
            params["after"] = cursor
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            logs = data.get("data", {}).get("lifelogs", [])
            all_logs.extend(logs)
            print(f"      Request {i+1}: Got {len(logs)} logs")
            # Try to find cursor in response
            cursor = data.get("next_cursor") or data.get("cursor") or (logs[-1].get("id") if logs else None)
            if not logs:
                break
        else:
            print(f"      Request {i+1}: Error {response.status_code}")
            break
    
    print(f"   Total logs from cursor pagination: {len(all_logs)}")
    
    # 4c. Original page-based approach
    print("   4c. Page-based pagination:")
    all_logs = []
    page = 1
    while page <= 5:
        params = {"limit": 50, "page": page}
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            logs = data.get("data", {}).get("lifelogs", [])
            all_logs.extend(logs)
            print(f"      Page {page}: Got {len(logs)} logs")
            if not logs or not data.get("has_more", False):
                print("      No more pages")
                break
        else:
            print(f"      Page {page}: Error {response.status_code}")
            break
        page += 1
    
    print(f"   Total logs from page pagination: {len(all_logs)}")
    
    # Test 5: Check unique logs and date ranges with offset
    print("\n5. Checking unique logs with offset:")
    all_unique_logs = {}
    total_fetched = 0
    
    for offset in range(0, 200, 25):  # Fetch up to 200 logs
        params = {"limit": 25, "offset": offset}
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            logs = data.get("data", {}).get("lifelogs", [])
            if not logs:
                print(f"   No more logs at offset {offset}")
                break
            
            for log in logs:
                log_id = log.get("id")
                if log_id and log_id not in all_unique_logs:
                    all_unique_logs[log_id] = log
                    
            total_fetched += len(logs)
            print(f"   Offset {offset}: Fetched {len(logs)} logs, {len(all_unique_logs)} unique so far")
        else:
            print(f"   Offset {offset}: Error {response.status_code}")
            break
    
    # Analyze unique logs by date
    if all_unique_logs:
        print(f"\n   Total unique logs: {len(all_unique_logs)}")
        print(f"   Total fetched (including duplicates): {total_fetched}")
        
        dates = {}
        for log_id, log in all_unique_logs.items():
            start_time = log.get("startTime")
            if start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace("Z", "+00:00").rstrip("+00:00"))
                    date_str = dt.strftime("%Y-%m-%d")
                    dates[date_str] = dates.get(date_str, 0) + 1
                except:
                    pass
        
        print("\n   Unique logs by date:")
        for date in sorted(dates.keys(), reverse=True):
            print(f"   {date}: {dates[date]} logs")

if __name__ == "__main__":
    debug_limitless_api()