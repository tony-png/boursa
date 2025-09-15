#!/usr/bin/env python3
"""
Test script to demonstrate rate limiting functionality.
"""
import asyncio
import time
from app.utils.rate_limiter import TWSRateLimiter


async def test_token_bucket():
    """Test token bucket rate limiter."""
    print("Testing Token Bucket Rate Limiter (45 tokens/sec)")
    print("=" * 50)
    
    # Create rate limiter with small bucket for testing
    rate_limiter = TWSRateLimiter(
        message_rate_limit=5,  # 5 tokens/sec for easy testing
        max_orders_per_contract=3  # 3 orders per contract for testing
    )
    
    # Test 1: Rapid token acquisition
    print("\n1. Testing rapid token acquisition (should succeed initially, then fail)")
    start_time = time.time()
    successful_acquires = 0
    failed_acquires = 0
    
    for i in range(10):  # Try to acquire 10 tokens rapidly
        if await rate_limiter.token_bucket.acquire(1):
            successful_acquires += 1
            print(f"   Token {i+1}: OK Acquired")
        else:
            failed_acquires += 1
            print(f"   Token {i+1}: FAILED (bucket empty)")
    
    elapsed = time.time() - start_time
    print(f"   Results: {successful_acquires} successful, {failed_acquires} failed in {elapsed:.3f}s")
    
    # Test 2: Wait for token refill
    print("\n2. Testing token refill (waiting for tokens to replenish)")
    print("   Waiting 2 seconds for tokens to refill...")
    await asyncio.sleep(2.0)
    
    status = await rate_limiter.token_bucket.get_status()
    print(f"   After waiting: {status.remaining_tokens:.1f} tokens available")
    
    # Test 3: Order placement rate limiting
    print("\n3. Testing order placement limits")
    symbol = "AAPL"
    action = "BUY"
    
    for i in range(5):  # Try to place 5 orders for same contract
        can_place, reason = await rate_limiter.can_place_order(symbol, action)
        if can_place:
            success = await rate_limiter.place_order_with_rate_limit(symbol, action)
            print(f"   Order {i+1}: OK Placed (Active orders: {await rate_limiter.order_tracker.get_active_count(symbol, action)})")
        else:
            print(f"   Order {i+1}: REJECTED - {reason}")
    
    # Test 4: Order completion
    print("\n4. Testing order completion (freeing slots)")
    await rate_limiter.order_completed(symbol, action)
    await rate_limiter.order_completed(symbol, action)
    print(f"   After completing 2 orders: {await rate_limiter.order_tracker.get_active_count(symbol, action)} active orders")
    
    # Test 5: Comprehensive status
    print("\n5. Final status")
    status = await rate_limiter.get_comprehensive_status()
    print(f"   Message rate limit: {status['message_rate_limit']['remaining_tokens']:.1f}/{status['message_rate_limit']['max_tokens']} tokens")
    print(f"   Active orders: {status['active_orders']['total_tracked']}/{status['active_orders']['max_per_contract']} per contract")
    print(f"   Queue size: {status['queue_status']['current_size']}/{status['queue_status']['max_size']}")


async def test_burst_requests():
    """Test handling of burst requests."""
    print("\n\nTesting Burst Request Handling")
    print("=" * 50)
    
    rate_limiter = TWSRateLimiter(message_rate_limit=10)  # 10 tokens/sec
    
    # Simulate burst of 20 requests
    print("\n1. Simulating burst of 20 requests (10 token limit)")
    start_time = time.time()
    
    tasks = []
    for i in range(20):
        task = rate_limiter.token_bucket.acquire(1)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    successful = sum(results)
    elapsed = time.time() - start_time
    
    print(f"   Results: {successful}/20 requests succeeded immediately in {elapsed:.3f}s")
    
    # Test waiting for tokens with timeout
    print("\n2. Testing wait-for-tokens with timeout")
    wait_start = time.time()
    success = await rate_limiter.token_bucket.wait_for_tokens(1, timeout=2.0)
    wait_time = time.time() - wait_start
    
    print(f"   Token acquired after waiting: {success} (wait time: {wait_time:.3f}s)")


if __name__ == "__main__":
    print("TWS API Rate Limiting Test Suite")
    print("================================")
    
    async def main():
        await test_token_bucket()
        await test_burst_requests()
        print("\nRate limiting tests completed successfully!")
    
    asyncio.run(main())