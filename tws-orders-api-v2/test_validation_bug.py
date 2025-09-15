"""
Quick test to reproduce and analyze the critical validation bug
"""

import requests
import json

# Test data that should FAIL validation but is incorrectly passing
test_data = {
    "contract": {
        "symbol": "AAPL",
        "sec_type": "STK",
        "exchange": "SMART", 
        "currency": "USD"
    },
    "action": "BUY",
    "order_type": "LMT",  # This is a LIMIT order
    "total_quantity": 100.0,
    "time_in_force": "DAY",
    "outside_rth": False,
    "hidden": False
    # NOTE: Missing limit_price - this should FAIL validation!
}

print("Testing CRITICAL validation bug:")
print("Sending limit order WITHOUT limit_price...")
print(f"Test data: {json.dumps(test_data, indent=2)}")

try:
    response = requests.post("http://localhost:8000/api/v1/orders", json=test_data)
    print(f"\nResponse status: {response.status_code}")
    print(f"Response body: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code == 201:
        print("\n🚨 CRITICAL BUG CONFIRMED! 🚨")
        print("Limit order was created WITHOUT a limit price!")
        print("This is a serious validation failure that could cause financial losses!")
    elif response.status_code == 422:
        print("\n✅ Validation working correctly - limit order rejected")
    else:
        print(f"\n❓ Unexpected response: {response.status_code}")
        
except requests.exceptions.ConnectionError:
    print("❌ Cannot connect to API server. Make sure it's running on http://localhost:8000")