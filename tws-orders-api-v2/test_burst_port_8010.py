#!/usr/bin/env python3
"""
Quick burst test specifically for port 8010 to demonstrate rate limiting.
"""
import asyncio
import aiohttp
import time


async def rapid_requests_test():
    """Send rapid requests to demonstrate rate limiting."""
    print("Rate Limiting Demonstration - Port 8010")
    print("=" * 50)
    
    api_url = "http://localhost:8010/api/v1/rate-limits/status"
    num_requests = 50
    
    print(f"Sending {num_requests} rapid status requests...")
    print("Watching token consumption in real-time...")
    
    async with aiohttp.ClientSession() as session:
        for batch in range(5):  # 5 batches of 10 requests each
            batch_start = time.time()
            print(f"\nBatch {batch + 1}:")
            
            # Send 10 requests in this batch
            tasks = []
            for i in range(10):
                task = session.get(api_url)
                tasks.append(task)
            
            # Execute batch
            responses = await asyncio.gather(*tasks)
            
            # Check responses and token consumption
            remaining_tokens = []
            for i, response in enumerate(responses):
                if response.status == 200:
                    data = await response.json()
                    tokens = data.get('message_rate_limit', {}).get('remaining_tokens', 'N/A')
                    remaining_tokens.append(tokens)
                    
                    # Show rate limit headers
                    rate_headers = {
                        'limit': response.headers.get('x-ratelimit-limit', 'N/A'),
                        'remaining': response.headers.get('x-ratelimit-remaining', 'N/A'),
                        'reset': response.headers.get('x-ratelimit-reset', 'N/A'),
                    }
                    
                    print(f"  Request {i+1:2d}: Tokens={tokens:5.1f}, Headers: limit={rate_headers['limit']}, remaining={rate_headers['remaining']}")
            
            batch_time = time.time() - batch_start
            print(f"  Batch completed in {batch_time:.3f}s")
            
            # Wait a bit between batches to see token refill
            if batch < 4:  # Don't wait after last batch
                print("  Waiting 1s for token refill...")
                await asyncio.sleep(1.0)


async def order_burst_test():
    """Test order creation burst to trigger rate limits."""
    print("\n" + "=" * 50)
    print("Order Creation Burst Test")
    print("=" * 50)
    
    # Test order payload
    order_payload = {
        "contract": {
            "symbol": "AAPL",
            "sec_type": "STK", 
            "exchange": "SMART",
            "currency": "USD"
        },
        "action": "BUY",
        "order_type": "LMT",  # Use limit orders to avoid immediate execution
        "total_quantity": 100,
        "limit_price": 1.00,  # Very low price to avoid execution
        "aux_price": 0.0,
        "time_in_force": "DAY",
        "outside_rth": False,
        "hidden": False
    }
    
    api_url = "http://localhost:8010/api/v1/orders"
    num_orders = 30  # Submit 30 orders rapidly
    
    print(f"Submitting {num_orders} limit orders rapidly...")
    print("(Low price to avoid execution, will be cancelled)")
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        # Submit all orders concurrently
        tasks = []
        for i in range(num_orders):
            task = session.post(
                api_url,
                json=order_payload,
                timeout=aiohttp.ClientTimeout(total=15)
            )
            tasks.append((task, i + 1))
        
        # Process results
        success_count = 0
        rate_limited_count = 0
        error_count = 0
        timeout_count = 0
        
        response_times = []
        
        for task, order_id in tasks:
            order_start = time.time()
            try:
                response = await task
                response_time = time.time() - order_start
                response_times.append(response_time)
                
                # Get rate limit headers
                remaining = response.headers.get('x-ratelimit-remaining', 'N/A')
                orders_total = response.headers.get('x-ratelimit-orders-total', 'N/A')
                
                if response.status == 201:
                    success_count += 1
                    result = await response.json()
                    tws_id = result.get('order', {}).get('order_id', 'N/A')
                    print(f"Order {order_id:2d}: SUCCESS (TWS: {tws_id}, {response_time:.3f}s, tokens: {remaining}, active: {orders_total})")
                    
                elif response.status == 429:
                    rate_limited_count += 1
                    retry_after = response.headers.get('retry-after', 'N/A')
                    print(f"Order {order_id:2d}: RATE_LIMITED (retry: {retry_after}s, {response_time:.3f}s)")
                    
                elif response.status == 503:
                    rate_limited_count += 1
                    result = await response.json()
                    error_detail = result.get('detail', {})
                    if isinstance(error_detail, dict):
                        msg = error_detail.get('message', 'Service unavailable')
                    else:
                        msg = str(error_detail)
                    print(f"Order {order_id:2d}: SERVICE_UNAVAIL ({msg}, {response_time:.3f}s)")
                    
                else:
                    error_count += 1
                    print(f"Order {order_id:2d}: ERROR (HTTP {response.status}, {response_time:.3f}s)")
                    
            except asyncio.TimeoutError:
                timeout_count += 1
                print(f"Order {order_id:2d}: TIMEOUT")
            except Exception as e:
                error_count += 1
                print(f"Order {order_id:2d}: EXCEPTION - {str(e)}")
    
    total_time = time.time() - start_time
    total_blocked = rate_limited_count
    
    print(f"\nOrder Burst Results:")
    print(f"  Total orders: {num_orders}")
    print(f"  Total time: {total_time:.3f}s")
    print(f"  SUCCESS: {success_count}")
    print(f"  RATE_LIMITED: {rate_limited_count}")
    print(f"  ERRORS: {error_count}")
    print(f"  TIMEOUTS: {timeout_count}")
    
    if response_times:
        print(f"  Avg response time: {sum(response_times)/len(response_times):.3f}s")
        print(f"  Min response time: {min(response_times):.3f}s")
        print(f"  Max response time: {max(response_times):.3f}s")
    
    print(f"\nRate Limiting Analysis:")
    expected_limited = max(0, num_orders - 45)
    print(f"  Expected limited (>{45} requests): ~{expected_limited}")
    print(f"  Actually limited/blocked: {total_blocked}")
    
    if total_blocked > 0 or (success_count > 0 and max(response_times) > min(response_times) * 3):
        print(f"  Rate limiting effectiveness: WORKING")
        if total_blocked > 0:
            print(f"    {total_blocked} requests were properly limited")
        if response_times:
            spread = max(response_times) / min(response_times) if min(response_times) > 0 else 1
            if spread > 3:
                print(f"    Response time spread indicates queuing: {spread:.1f}x")
    else:
        print(f"  Rate limiting effectiveness: UNCLEAR")


if __name__ == "__main__":
    async def main():
        await rapid_requests_test()
        await order_burst_test()
    
    asyncio.run(main())