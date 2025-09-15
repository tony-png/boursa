#!/usr/bin/env python3
"""
Test script to submit 50 orders simultaneously to test rate limiting.
"""
import asyncio
import aiohttp
import time
import json
from datetime import datetime


async def create_order_payload(symbol: str, action: str, quantity: float, order_type: str = "MKT"):
    """Create a test order payload."""
    return {
        "contract": {
            "symbol": symbol,
            "sec_type": "STK",
            "exchange": "SMART", 
            "currency": "USD"
        },
        "action": action,
        "order_type": order_type,
        "total_quantity": quantity,
        "limit_price": 0.0 if order_type == "MKT" else 100.0,
        "aux_price": 0.0,
        "time_in_force": "DAY",
        "outside_rth": False,
        "hidden": False
    }


async def submit_single_order(session: aiohttp.ClientSession, url: str, order_data: dict, order_id: int):
    """Submit a single order and return the result."""
    start_time = time.time()
    
    try:
        async with session.post(url, json=order_data, timeout=aiohttp.ClientTimeout(total=60)) as response:
            elapsed = time.time() - start_time
            
            # Get rate limit headers
            rate_headers = {
                'limit': response.headers.get('x-ratelimit-limit', 'N/A'),
                'remaining': response.headers.get('x-ratelimit-remaining', 'N/A'), 
                'reset': response.headers.get('x-ratelimit-reset', 'N/A'),
                'orders_max': response.headers.get('x-ratelimit-orders-max', 'N/A'),
                'orders_total': response.headers.get('x-ratelimit-orders-total', 'N/A')
            }
            
            if response.status == 201:
                # Order created successfully
                result = await response.json()
                return {
                    'order_id': order_id,
                    'status': 'SUCCESS',
                    'response_time': elapsed,
                    'http_status': response.status,
                    'rate_headers': rate_headers,
                    'tws_order_id': result.get('order', {}).get('order_id', 'N/A')
                }
            elif response.status == 429:
                # Rate limited
                result = await response.json()
                retry_after = response.headers.get('retry-after', 'N/A')
                return {
                    'order_id': order_id,
                    'status': 'RATE_LIMITED',
                    'response_time': elapsed,
                    'http_status': response.status,
                    'rate_headers': rate_headers,
                    'retry_after': retry_after,
                    'error': result.get('message', 'Rate limit exceeded')
                }
            elif response.status == 503:
                # Service unavailable (connection issues or emergency breaker)
                result = await response.json()
                return {
                    'order_id': order_id,
                    'status': 'SERVICE_UNAVAILABLE',
                    'response_time': elapsed,
                    'http_status': response.status,
                    'rate_headers': rate_headers,
                    'error': result.get('detail', {}).get('message', 'Service unavailable')
                }
            else:
                # Other error
                try:
                    result = await response.json()
                    error_msg = result.get('detail', {}).get('message', f'HTTP {response.status}')
                except:
                    error_msg = f'HTTP {response.status}'
                
                return {
                    'order_id': order_id,
                    'status': 'ERROR',
                    'response_time': elapsed,
                    'http_status': response.status,
                    'rate_headers': rate_headers,
                    'error': error_msg
                }
                
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        return {
            'order_id': order_id,
            'status': 'TIMEOUT',
            'response_time': elapsed,
            'http_status': None,
            'rate_headers': {},
            'error': 'Request timeout'
        }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            'order_id': order_id,
            'status': 'EXCEPTION',
            'response_time': elapsed,
            'http_status': None,
            'rate_headers': {},
            'error': str(e)
        }


async def test_burst_orders():
    """Test submitting 50 orders simultaneously."""
    print("TWS API Rate Limiting Burst Test")
    print("=" * 50)
    print(f"Test started at: {datetime.now().isoformat()}")
    
    # Configuration
    api_url = "http://localhost:8000/api/v1/orders"
    num_orders = 50
    
    # Create test orders for different symbols to avoid contract limits
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX', 'CRM', 'ORCL']
    
    print(f"\nSubmitting {num_orders} orders simultaneously...")
    print(f"API URL: {api_url}")
    print(f"Symbols: {', '.join(symbols)}")
    
    # Prepare orders
    orders = []
    for i in range(num_orders):
        symbol = symbols[i % len(symbols)]  # Rotate through symbols
        action = 'BUY' if i % 2 == 0 else 'SELL'
        quantity = 100 + (i * 10)  # Vary quantities
        
        order_data = await create_order_payload(symbol, action, quantity)
        orders.append((order_data, i + 1))
    
    print(f"Created {len(orders)} test orders")
    
    # Submit all orders concurrently
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        # Create tasks for all orders
        tasks = [
            submit_single_order(session, api_url, order_data, order_id)
            for order_data, order_id in orders
        ]
        
        print(f"\nSubmitting all {num_orders} orders concurrently...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    total_elapsed = time.time() - start_time
    
    # Process results
    success_count = 0
    rate_limited_count = 0
    error_count = 0
    timeout_count = 0
    service_unavailable_count = 0
    
    response_times = []
    rate_limit_data = []
    
    print(f"\nResults (Total time: {total_elapsed:.3f}s):")
    print("-" * 80)
    
    for result in results:
        if isinstance(result, Exception):
            print(f"Order EXCEPTION: {result}")
            error_count += 1
            continue
        
        response_times.append(result['response_time'])
        
        status = result['status']
        order_id = result['order_id']
        response_time = result['response_time']
        
        if status == 'SUCCESS':
            success_count += 1
            tws_order_id = result.get('tws_order_id', 'N/A')
            print(f"Order {order_id:2d}: SUCCESS (TWS ID: {tws_order_id}, {response_time:.3f}s)")
            
        elif status == 'RATE_LIMITED':
            rate_limited_count += 1
            retry_after = result.get('retry_after', 'N/A')
            print(f"Order {order_id:2d}: RATE_LIMITED (retry_after: {retry_after}s, {response_time:.3f}s)")
            
        elif status == 'SERVICE_UNAVAILABLE':
            service_unavailable_count += 1
            error = result.get('error', 'Unknown')
            print(f"Order {order_id:2d}: SERVICE_UNAVAILABLE ({error}, {response_time:.3f}s)")
            
        elif status == 'TIMEOUT':
            timeout_count += 1
            print(f"Order {order_id:2d}: TIMEOUT ({response_time:.3f}s)")
            
        else:
            error_count += 1
            error = result.get('error', 'Unknown')
            http_status = result.get('http_status', 'N/A')
            print(f"Order {order_id:2d}: ERROR (HTTP {http_status}: {error}, {response_time:.3f}s)")
        
        # Collect rate limit data
        rate_headers = result.get('rate_headers', {})
        if rate_headers:
            rate_limit_data.append(rate_headers)
    
    # Summary statistics
    print("\n" + "=" * 50)
    print("SUMMARY STATISTICS")
    print("=" * 50)
    
    print(f"Total orders submitted: {num_orders}")
    print(f"Total execution time: {total_elapsed:.3f}s")
    print(f"Average response time: {sum(response_times)/len(response_times):.3f}s")
    print(f"Min response time: {min(response_times):.3f}s")
    print(f"Max response time: {max(response_times):.3f}s")
    
    print(f"\nResults breakdown:")
    print(f"  SUCCESS: {success_count} ({success_count/num_orders*100:.1f}%)")
    print(f"  RATE_LIMITED: {rate_limited_count} ({rate_limited_count/num_orders*100:.1f}%)")
    print(f"  SERVICE_UNAVAILABLE: {service_unavailable_count} ({service_unavailable_count/num_orders*100:.1f}%)")
    print(f"  TIMEOUT: {timeout_count} ({timeout_count/num_orders*100:.1f}%)")
    print(f"  ERROR: {error_count} ({error_count/num_orders*100:.1f}%)")
    
    # Rate limiting analysis
    if rate_limit_data:
        print(f"\nRate Limiting Analysis:")
        first_headers = rate_limit_data[0]
        last_headers = rate_limit_data[-1] if len(rate_limit_data) > 1 else first_headers
        
        print(f"  Rate limit (messages/sec): {first_headers.get('limit', 'N/A')}")
        print(f"  Initial remaining tokens: {first_headers.get('remaining', 'N/A')}")
        print(f"  Final remaining tokens: {last_headers.get('remaining', 'N/A')}")
        print(f"  Order limit per contract: {first_headers.get('orders_max', 'N/A')}")
        print(f"  Total active orders tracked: {last_headers.get('orders_total', 'N/A')}")
    
    # Rate limiting effectiveness
    expected_rate_limited = max(0, num_orders - 45)  # Should rate limit after 45 messages
    actual_limited = rate_limited_count + service_unavailable_count
    
    print(f"\nRate Limiting Effectiveness:")
    print(f"  Expected rate limited (>45 msgs): {expected_rate_limited}")
    print(f"  Actually limited/blocked: {actual_limited}")
    print(f"  Rate limiting working: {'YES' if actual_limited >= expected_rate_limited else 'NO'}")
    
    if rate_limited_count > 0 or service_unavailable_count > 0:
        print(f"\n✅ Rate limiting is working correctly!")
        print(f"   {actual_limited}/{num_orders} requests were properly limited/queued")
    else:
        print(f"\n⚠️  No requests were rate limited")
        print(f"   This might indicate rate limiting is disabled or limits are too high")
    
    return {
        'total_orders': num_orders,
        'success': success_count,
        'rate_limited': rate_limited_count,
        'service_unavailable': service_unavailable_count,
        'errors': error_count,
        'timeouts': timeout_count,
        'total_time': total_elapsed,
        'avg_response_time': sum(response_times)/len(response_times) if response_times else 0
    }


if __name__ == "__main__":
    asyncio.run(test_burst_orders())