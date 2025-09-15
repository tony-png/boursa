#!/usr/bin/env python3
"""
Aggressive test to force rate limit rejections by overwhelming the token bucket.
"""
import asyncio
import aiohttp
import time
import json


async def test_aggressive_rate_limiting():
    """Test with a much higher load to force rate limit rejections."""
    print("Aggressive Rate Limit Test")
    print("=" * 40)
    
    # Test configuration - submit 100 requests rapidly
    api_url = "http://localhost:8000/api/v1/rate-limits/test"  # Use the test endpoint
    num_requests = 100
    
    print(f"Submitting {num_requests} rate limit test requests...")
    print("This should trigger rate limiting since we're overwhelming the token bucket")
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        # Create tasks for all requests
        tasks = []
        
        for i in range(num_requests):
            task = asyncio.create_task(
                session.post(api_url, timeout=aiohttp.ClientTimeout(total=5))
            )
            tasks.append((task, i + 1))
        
        # Submit all requests and collect results
        results = []
        success_count = 0
        rate_limited_count = 0
        error_count = 0
        timeout_count = 0
        
        for task, request_id in tasks:
            try:
                response = await task
                
                if response.status == 200:
                    result = await response.json()
                    if result.get("test") == "PASSED":
                        success_count += 1
                        print(f"Request {request_id:3d}: SUCCESS - Token acquired")
                    elif result.get("test") == "LIMITED":
                        rate_limited_count += 1
                        print(f"Request {request_id:3d}: RATE_LIMITED - {result.get('message', 'No tokens available')}")
                    else:
                        print(f"Request {request_id:3d}: OTHER - {result}")
                elif response.status == 429:
                    rate_limited_count += 1
                    print(f"Request {request_id:3d}: HTTP_429 - Rate limited by middleware")
                else:
                    error_count += 1
                    print(f"Request {request_id:3d}: ERROR - HTTP {response.status}")
                    
            except asyncio.TimeoutError:
                timeout_count += 1
                print(f"Request {request_id:3d}: TIMEOUT")
            except Exception as e:
                error_count += 1
                print(f"Request {request_id:3d}: EXCEPTION - {str(e)}")
    
    total_time = time.time() - start_time
    
    print("\n" + "=" * 50)
    print("AGGRESSIVE TEST RESULTS")
    print("=" * 50)
    
    print(f"Total requests: {num_requests}")
    print(f"Total time: {total_time:.3f}s")
    print(f"Requests per second: {num_requests/total_time:.1f}")
    
    print(f"\nResults breakdown:")
    print(f"  SUCCESS (token acquired): {success_count}")
    print(f"  RATE_LIMITED: {rate_limited_count}")
    print(f"  ERRORS: {error_count}")
    print(f"  TIMEOUTS: {timeout_count}")
    
    # Analysis
    total_limited = rate_limited_count
    expected_limited = max(0, num_requests - 45)  # Should limit after ~45 tokens
    
    print(f"\nRate Limiting Analysis:")
    print(f"  Expected limited (>{45} requests): ~{expected_limited}")
    print(f"  Actually limited: {total_limited}")
    
    if total_limited > 0:
        print(f"\n✅ Rate limiting is working!")
        print(f"   {total_limited}/{num_requests} requests were properly rate limited")
        effectiveness = (total_limited / expected_limited * 100) if expected_limited > 0 else 100
        print(f"   Effectiveness: {effectiveness:.1f}%")
    else:
        print(f"\n❌ Rate limiting may not be working as expected")
        print(f"   All {success_count} requests succeeded")


async def test_rapid_order_creation():
    """Test rapid order creation to see rate limiting in action."""
    print("\n" + "=" * 50)
    print("RAPID ORDER CREATION TEST") 
    print("=" * 50)
    
    # Create a simple order payload
    order_payload = {
        "contract": {
            "symbol": "TEST",
            "sec_type": "STK",
            "exchange": "SMART",
            "currency": "USD"
        },
        "action": "BUY",
        "order_type": "MKT",
        "total_quantity": 100,
        "limit_price": 0.0,
        "aux_price": 0.0,
        "time_in_force": "DAY",
        "outside_rth": False,
        "hidden": False
    }
    
    api_url = "http://localhost:8000/api/v1/orders"
    num_orders = 60  # Submit 60 orders (should exceed 45 token limit)
    
    print(f"Rapidly submitting {num_orders} TEST symbol orders...")
    print("(These will likely fail due to invalid symbol, but should show rate limiting)")
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        
        # Submit all orders as fast as possible
        for i in range(num_orders):
            task = asyncio.create_task(
                session.post(
                    api_url, 
                    json=order_payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                )
            )
            tasks.append((task, i + 1))
        
        # Collect results
        success_count = 0
        rate_limited_count = 0
        service_unavailable_count = 0
        error_count = 0
        timeout_count = 0
        
        for task, order_id in tasks:
            try:
                response = await task
                
                # Check rate limit headers
                remaining = response.headers.get('x-ratelimit-remaining', 'N/A')
                
                if response.status == 201:
                    success_count += 1
                    print(f"Order {order_id:2d}: SUCCESS (tokens remaining: {remaining})")
                elif response.status == 429:
                    rate_limited_count += 1
                    retry_after = response.headers.get('retry-after', 'N/A')
                    print(f"Order {order_id:2d}: RATE_LIMITED (retry_after: {retry_after}s)")
                elif response.status == 503:
                    service_unavailable_count += 1
                    result = await response.json()
                    error_msg = result.get('detail', {}).get('message', 'Service unavailable')
                    print(f"Order {order_id:2d}: SERVICE_UNAVAIL - {error_msg}")
                else:
                    error_count += 1
                    print(f"Order {order_id:2d}: ERROR - HTTP {response.status}")
                    
            except asyncio.TimeoutError:
                timeout_count += 1
                print(f"Order {order_id:2d}: TIMEOUT")
            except Exception as e:
                error_count += 1
                print(f"Order {order_id:2d}: EXCEPTION - {str(e)}")
    
    total_time = time.time() - start_time
    total_limited = rate_limited_count + service_unavailable_count
    
    print(f"\nRapid Order Test Results:")
    print(f"  Total orders: {num_orders}")
    print(f"  Total time: {total_time:.3f}s")
    print(f"  SUCCESS: {success_count}")
    print(f"  RATE_LIMITED: {rate_limited_count}")
    print(f"  SERVICE_UNAVAILABLE: {service_unavailable_count}")
    print(f"  ERRORS: {error_count}")
    print(f"  TIMEOUTS: {timeout_count}")
    
    print(f"\n  Total limited/blocked: {total_limited}/{num_orders}")
    
    if total_limited > 0:
        print(f"  ✅ Rate limiting working for order creation!")
    else:
        print(f"  ⚠️  No orders were rate limited")


if __name__ == "__main__":
    async def main():
        await test_aggressive_rate_limiting()
        await test_rapid_order_creation()
    
    asyncio.run(main())