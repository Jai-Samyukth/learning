#!/usr/bin/env python3
"""
Test script to verify parallel processing of chat requests.
This script simulates multiple concurrent users sending messages simultaneously
to verify that all users get responses at virtually the same time.
"""

import asyncio
import aiohttp
import time
from typing import List, Dict

# Test configuration
BASE_URL = "http://localhost:8000"
CHAT_ENDPOINT = f"{BASE_URL}/api/chat/"
NUM_CONCURRENT_USERS = 10
TEST_MESSAGE = "What is the main topic of this document?"

async def send_chat_message(session: aiohttp.ClientSession, user_id: int) -> Dict:
    """Send a chat message and measure response time"""
    start_time = time.time()
    
    # Create unique headers to simulate different users
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': f'TestUser-{user_id}',
        'X-Forwarded-For': f'192.168.1.{user_id}'  # Simulate different IPs
    }
    
    payload = {
        "message": f"{TEST_MESSAGE} (User {user_id})"
    }
    
    try:
        async with session.post(CHAT_ENDPOINT, json=payload, headers=headers) as response:
            end_time = time.time()
            response_time = end_time - start_time
            
            if response.status == 200:
                data = await response.json()
                return {
                    'user_id': user_id,
                    'status': 'success',
                    'response_time': response_time,
                    'start_time': start_time,
                    'end_time': end_time,
                    'response_length': len(data.get('response', ''))
                }
            else:
                return {
                    'user_id': user_id,
                    'status': 'error',
                    'response_time': response_time,
                    'error': f"HTTP {response.status}",
                    'start_time': start_time,
                    'end_time': end_time
                }
    except Exception as e:
        end_time = time.time()
        return {
            'user_id': user_id,
            'status': 'error',
            'response_time': end_time - start_time,
            'error': str(e),
            'start_time': start_time,
            'end_time': end_time
        }

async def test_parallel_processing():
    """Test parallel processing with multiple concurrent users"""
    print(f"🚀 Testing parallel processing with {NUM_CONCURRENT_USERS} concurrent users...")
    print(f"📡 Target endpoint: {CHAT_ENDPOINT}")
    print(f"💬 Test message: {TEST_MESSAGE}")
    print("-" * 60)
    
    # Create HTTP session with connection pooling
    connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
    timeout = aiohttp.ClientTimeout(total=120)  # 2 minute timeout
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Record overall start time
        overall_start = time.time()
        
        # Create tasks for all users simultaneously
        tasks = [
            send_chat_message(session, user_id) 
            for user_id in range(1, NUM_CONCURRENT_USERS + 1)
        ]
        
        # Execute all tasks concurrently
        print(f"⏱️  Starting {NUM_CONCURRENT_USERS} concurrent requests at {time.strftime('%H:%M:%S')}...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        overall_end = time.time()
        overall_duration = overall_end - overall_start
        
        # Analyze results
        successful_results = [r for r in results if isinstance(r, dict) and r.get('status') == 'success']
        failed_results = [r for r in results if isinstance(r, dict) and r.get('status') == 'error']
        exceptions = [r for r in results if isinstance(r, Exception)]
        
        print(f"✅ Completed in {overall_duration:.2f} seconds")
        print("-" * 60)
        
        # Success/failure summary
        print(f"📊 RESULTS SUMMARY:")
        print(f"   ✅ Successful: {len(successful_results)}")
        print(f"   ❌ Failed: {len(failed_results)}")
        print(f"   💥 Exceptions: {len(exceptions)}")
        print()
        
        if successful_results:
            # Response time analysis
            response_times = [r['response_time'] for r in successful_results]
            start_times = [r['start_time'] for r in successful_results]
            end_times = [r['end_time'] for r in successful_results]
            
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            avg_response_time = sum(response_times) / len(response_times)
            
            # Calculate time spread (how close together responses arrived)
            time_spread = max(end_times) - min(end_times)
            
            print(f"⚡ PERFORMANCE METRICS:")
            print(f"   🏃 Fastest response: {min_response_time:.2f}s (User {successful_results[response_times.index(min_response_time)]['user_id']})")
            print(f"   🐌 Slowest response: {max_response_time:.2f}s (User {successful_results[response_times.index(max_response_time)]['user_id']})")
            print(f"   📈 Average response: {avg_response_time:.2f}s")
            print(f"   🎯 Response spread: {time_spread:.2f}s")
            print()
            
            # Parallel processing assessment
            if time_spread < 2.0:  # If all responses came within 2 seconds of each other
                print("🎉 EXCELLENT! True parallel processing achieved!")
                print("   All users received responses within 2 seconds of each other.")
            elif time_spread < 5.0:
                print("✅ GOOD! Mostly parallel processing achieved!")
                print(f"   All users received responses within {time_spread:.1f} seconds of each other.")
            else:
                print("⚠️  NEEDS IMPROVEMENT! Sequential processing detected!")
                print(f"   Response spread of {time_spread:.1f}s indicates sequential processing.")
            
            print()
            print("📋 DETAILED RESULTS:")
            for result in sorted(successful_results, key=lambda x: x['user_id']):
                print(f"   User {result['user_id']:2d}: {result['response_time']:5.2f}s | Response: {result['response_length']} chars")
        
        # Show errors if any
        if failed_results or exceptions:
            print()
            print("❌ ERRORS:")
            for result in failed_results:
                print(f"   User {result['user_id']}: {result['error']}")
            for i, exc in enumerate(exceptions):
                print(f"   Exception {i+1}: {exc}")

if __name__ == "__main__":
    print("🧪 Parallel Processing Test for Learning App Backend")
    print("=" * 60)
    
    try:
        asyncio.run(test_parallel_processing())
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
    
    print("\n" + "=" * 60)
    print("🏁 Test completed!")
