"""
Comprehensive edge case test suite for TWS Orders API v2.
Tests critical edge cases, boundary conditions, and error scenarios.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
import json
import asyncio
from datetime import datetime

from app.main import app
from app.models.orders import OrderAction, OrderType, SecurityType, TimeInForce
from app.services.ib_service import IBService


client = TestClient(app)


class TestOrderCreationEdgeCases:
    """Test edge cases for order creation validation."""
    
    @pytest.fixture
    def base_order_request(self):
        """Base valid order request for testing modifications."""
        return {
            "contract": {
                "symbol": "AAPL",
                "sec_type": "STK",
                "exchange": "SMART",
                "currency": "USD"
            },
            "action": "BUY",
            "order_type": "MKT",
            "total_quantity": 100.0,
            "time_in_force": "DAY",
            "outside_rth": False,
            "hidden": False
        }
    
    def test_empty_symbol_validation(self, base_order_request):
        """Test order creation with empty symbol."""
        base_order_request["contract"]["symbol"] = ""
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
        assert "Symbol cannot be empty" in response.json()["detail"][0]["msg"]
    
    def test_whitespace_only_symbol(self, base_order_request):
        """Test order creation with whitespace-only symbol."""
        base_order_request["contract"]["symbol"] = "   "
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
        assert "Symbol cannot be empty" in response.json()["detail"][0]["msg"]
    
    def test_symbol_case_normalization(self, base_order_request):
        """Test that symbol is normalized to uppercase."""
        base_order_request["contract"]["symbol"] = "aapl"
        # This should pass validation and normalize to AAPL
        with patch('app.services.ib_service.ib_service.create_contract') as mock_create:
            with patch('app.services.ib_service.ib_service.place_order') as mock_place:
                mock_create.return_value = MagicMock()
                mock_place.return_value = MagicMock()
                response = client.post("/api/v1/orders", json=base_order_request)
                # Should not fail validation
                assert response.status_code != 422
    
    def test_very_long_symbol(self, base_order_request):
        """Test order creation with very long symbol."""
        base_order_request["contract"]["symbol"] = "A" * 1000
        response = client.post("/api/v1/orders", json=base_order_request)
        # Should pass validation but may fail in TWS
        assert response.status_code != 422
    
    def test_special_characters_in_symbol(self, base_order_request):
        """Test symbol with special characters."""
        test_symbols = ["$SPY", "BRK.A", "ABC-123", "TEST@SYMBOL", "SYMBOL!"]
        for symbol in test_symbols:
            base_order_request["contract"]["symbol"] = symbol
            response = client.post("/api/v1/orders", json=base_order_request)
            # Should pass validation (TWS will handle validity)
            assert response.status_code != 422
    
    def test_zero_quantity(self, base_order_request):
        """Test order creation with zero quantity."""
        base_order_request["total_quantity"] = 0.0
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
        assert "ensure this value is greater than 0" in str(response.json())
    
    def test_negative_quantity(self, base_order_request):
        """Test order creation with negative quantity."""
        base_order_request["total_quantity"] = -100.0
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
        assert "ensure this value is greater than 0" in str(response.json())
    
    def test_extremely_large_quantity(self, base_order_request):
        """Test order creation with extremely large quantity."""
        base_order_request["total_quantity"] = 1e15  # Very large number
        response = client.post("/api/v1/orders", json=base_order_request)
        # Should pass validation but may have precision issues
        assert response.status_code != 422
    
    def test_precision_quantity(self, base_order_request):
        """Test order creation with high precision quantity."""
        base_order_request["total_quantity"] = 100.123456789
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code != 422
    
    def test_scientific_notation_quantity(self, base_order_request):
        """Test order creation with scientific notation quantity."""
        base_order_request["total_quantity"] = 1.5e2  # 150.0
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code != 422
    
    def test_limit_order_missing_price(self, base_order_request):
        """Test limit order creation without limit price."""
        base_order_request["order_type"] = "LMT"
        # Don't provide limit_price
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
        assert "Limit price is required for LMT orders" in str(response.json())
    
    def test_limit_order_zero_price(self, base_order_request):
        """Test limit order with zero limit price."""
        base_order_request["order_type"] = "LMT"
        base_order_request["limit_price"] = 0.0
        response = client.post("/api/v1/orders", json=base_order_request)
        # Should pass validation (zero is >= 0)
        assert response.status_code != 422
    
    def test_negative_limit_price(self, base_order_request):
        """Test limit order with negative limit price."""
        base_order_request["order_type"] = "LMT"
        base_order_request["limit_price"] = -100.0
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
        assert "ensure this value is greater than or equal to 0" in str(response.json())
    
    def test_stop_order_missing_aux_price(self, base_order_request):
        """Test stop order creation without auxiliary price."""
        base_order_request["order_type"] = "STP"
        # Don't provide aux_price
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
        assert "Auxiliary price (stop price) is required for STP orders" in str(response.json())
    
    def test_stop_limit_order_missing_both_prices(self, base_order_request):
        """Test stop-limit order without both required prices."""
        base_order_request["order_type"] = "STP LMT"
        # Don't provide limit_price or aux_price
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
        response_text = str(response.json())
        # Should fail for limit price first (since validator runs in order)
        assert ("Limit price is required for STP LMT orders" in response_text) or \
               ("Auxiliary price (stop price) is required for STP LMT orders" in response_text)
    
    def test_invalid_enum_values(self, base_order_request):
        """Test order creation with invalid enum values."""
        # Invalid action
        base_order_request["action"] = "INVALID_ACTION"
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
        
        # Reset to valid action
        base_order_request["action"] = "BUY"
        
        # Invalid order type
        base_order_request["order_type"] = "INVALID_TYPE"
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
        
        # Reset to valid order type
        base_order_request["order_type"] = "MKT"
        
        # Invalid security type
        base_order_request["contract"]["sec_type"] = "INVALID_SEC"
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
        
        # Reset to valid sec type
        base_order_request["contract"]["sec_type"] = "STK"
        
        # Invalid time in force
        base_order_request["time_in_force"] = "INVALID_TIF"
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
    
    def test_malformed_json_request(self):
        """Test order creation with malformed JSON."""
        malformed_json = '{"contract": {"symbol": "AAPL", "sec_type": "STK"}, "action": "BUY", "order_type": "MKT", "total_quantity": 100.0, "time_in_force": "DAY"'  # Missing closing brace
        
        response = client.post(
            "/api/v1/orders",
            data=malformed_json,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
    
    def test_missing_required_fields(self):
        """Test order creation with missing required fields."""
        incomplete_requests = [
            {},  # Empty request
            {"contract": {"symbol": "AAPL"}},  # Missing most fields
            {"contract": {"symbol": "AAPL", "sec_type": "STK"}, "action": "BUY"},  # Missing order_type, quantity
        ]
        
        for incomplete_request in incomplete_requests:
            response = client.post("/api/v1/orders", json=incomplete_request)
            assert response.status_code == 422
    
    def test_null_values_in_required_fields(self, base_order_request):
        """Test order creation with null values in required fields."""
        base_order_request["action"] = None
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
        
        # Reset and test another field
        base_order_request["action"] = "BUY"
        base_order_request["total_quantity"] = None
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 422
    
    @patch('app.services.ib_service.ib_service.is_emergency_breaker_active')
    def test_emergency_breaker_blocks_order_creation(self, mock_breaker, base_order_request):
        """Test that emergency breaker blocks order creation."""
        mock_breaker.return_value = True
        
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 503
        assert "Emergency breaker is active" in response.json()["detail"]
    
    def test_unicode_characters_in_fields(self, base_order_request):
        """Test handling of Unicode characters in string fields."""
        base_order_request["contract"]["symbol"] = "AAPL™"
        response = client.post("/api/v1/orders", json=base_order_request)
        # Should pass validation
        assert response.status_code != 422
        
        base_order_request["contract"]["exchange"] = "SMART™"
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code != 422
    
    def test_extremely_long_string_fields(self, base_order_request):
        """Test with extremely long string values."""
        long_string = "A" * 10000
        
        base_order_request["contract"]["exchange"] = long_string
        response = client.post("/api/v1/orders", json=base_order_request)
        # Should pass validation but may cause issues downstream
        assert response.status_code != 422
    
    def test_date_time_field_formats(self, base_order_request):
        """Test various date/time formats in good_after_time and good_till_date."""
        test_dates = [
            "20240101 09:30:00",  # Valid format
            "2024-01-01 09:30:00",  # Invalid format (dashes)
            "20240101",  # Missing time
            "invalid_date",  # Completely invalid
            "",  # Empty string
        ]
        
        for test_date in test_dates:
            base_order_request["good_after_time"] = test_date
            response = client.post("/api/v1/orders", json=base_order_request)
            # All should pass validation (TWS will validate format)
            assert response.status_code != 422
            
            base_order_request["good_till_date"] = test_date
            response = client.post("/api/v1/orders", json=base_order_request)
            assert response.status_code != 422
    
    @patch('app.services.ib_service.ib_service.create_contract')
    def test_contract_creation_failure(self, mock_create_contract, base_order_request):
        """Test order creation when contract creation fails."""
        mock_create_contract.side_effect = ValueError("Invalid contract")
        
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 400
        assert "Invalid contract" in response.json()["detail"]
    
    @patch('app.services.ib_service.ib_service.create_contract')
    def test_tws_connection_error_during_order_creation(self, mock_create_contract, base_order_request):
        """Test order creation when TWS connection is lost."""
        mock_create_contract.side_effect = ConnectionError("Connection lost")
        
        response = client.post("/api/v1/orders", json=base_order_request)
        assert response.status_code == 503
        assert "Connection lost" in response.json()["detail"]


class TestOrderRetrievalEdgeCases:
    """Test edge cases for order retrieval operations."""
    
    def test_get_order_with_negative_id(self):
        """Test retrieving order with negative ID."""
        response = client.get("/api/v1/orders/-1")
        assert response.status_code in [400, 422, 404]  # Various valid error codes
    
    def test_get_order_with_zero_id(self):
        """Test retrieving order with zero ID."""
        response = client.get("/api/v1/orders/0")
        # Zero might be valid in some contexts
        assert response.status_code in [200, 404]
    
    def test_get_order_with_very_large_id(self):
        """Test retrieving order with very large ID."""
        response = client.get("/api/v1/orders/999999999999")
        assert response.status_code in [200, 404]
    
    def test_get_order_with_string_id(self):
        """Test retrieving order with string ID."""
        response = client.get("/api/v1/orders/abc")
        assert response.status_code == 422  # FastAPI validation error
    
    def test_get_order_with_float_id(self):
        """Test retrieving order with float ID."""
        response = client.get("/api/v1/orders/1.5")
        assert response.status_code == 422
    
    @patch('app.services.ib_service.ib_service.get_order')
    def test_get_order_tws_connection_error(self, mock_get_order):
        """Test order retrieval when TWS connection is lost."""
        mock_get_order.side_effect = ConnectionError("Connection lost")
        
        response = client.get("/api/v1/orders/1")
        assert response.status_code == 503
        assert "Connection lost" in response.json()["detail"]
    
    @patch('app.services.ib_service.ib_service.get_orders')
    def test_get_orders_empty_list(self, mock_get_orders):
        """Test retrieving orders when no orders exist."""
        mock_get_orders.return_value = []
        
        response = client.get("/api/v1/orders")
        assert response.status_code == 200
        assert response.json() == []
    
    @patch('app.services.ib_service.ib_service.get_all_open_orders')
    def test_get_all_orders_empty_list(self, mock_get_all_orders):
        """Test retrieving all orders when no orders exist."""
        mock_get_all_orders.return_value = []
        
        response = client.get("/api/v1/orders/all")
        assert response.status_code == 200
        assert response.json() == []
    
    @patch('app.services.ib_service.ib_service.get_all_open_orders')
    def test_get_all_orders_tws_error(self, mock_get_all_orders):
        """Test get all orders with TWS error."""
        mock_get_all_orders.side_effect = Exception("TWS error")
        
        response = client.get("/api/v1/orders/all")
        assert response.status_code == 500
        assert "Failed to retrieve all orders" in response.json()["detail"]


class TestOrderModificationEdgeCases:
    """Test edge cases for order modification operations."""
    
    def test_modify_nonexistent_order(self):
        """Test modifying a non-existent order."""
        modify_data = {"total_quantity": 200.0}
        
        response = client.put("/api/v1/orders/999999", json=modify_data)
        assert response.status_code in [400, 404]
    
    def test_modify_order_empty_payload(self):
        """Test modifying order with empty payload."""
        response = client.put("/api/v1/orders/1", json={})
        assert response.status_code == 400
        assert "No modifications provided" in response.json()["detail"]
    
    def test_modify_order_invalid_quantities(self):
        """Test modifying order with invalid quantities."""
        invalid_modifications = [
            {"total_quantity": 0.0},
            {"total_quantity": -100.0},
            {"limit_price": -50.0},
            {"aux_price": -25.0},
        ]
        
        for modification in invalid_modifications:
            response = client.put("/api/v1/orders/1", json=modification)
            assert response.status_code == 422
    
    def test_modify_order_null_values(self):
        """Test modifying order with null values."""
        modify_data = {
            "total_quantity": None,
            "limit_price": None
        }
        
        response = client.put("/api/v1/orders/1", json=modify_data)
        # Null values should be ignored (not included in modifications)
        assert response.status_code == 400  # No modifications provided
    
    def test_modify_order_invalid_enum_values(self):
        """Test modifying order with invalid enum values."""
        modify_data = {"time_in_force": "INVALID_TIF"}
        
        response = client.put("/api/v1/orders/1", json=modify_data)
        assert response.status_code == 422
    
    @patch('app.services.ib_service.ib_service.modify_order')
    def test_modify_order_service_failure(self, mock_modify_order):
        """Test order modification when service returns failure."""
        mock_modify_order.return_value = False
        
        modify_data = {"total_quantity": 200.0}
        response = client.put("/api/v1/orders/1", json=modify_data)
        assert response.status_code == 400
        assert "Failed to modify order 1" in response.json()["detail"]
    
    @patch('app.services.ib_service.ib_service.modify_order')
    def test_modify_order_not_found_exception(self, mock_modify_order):
        """Test order modification when order is not found."""
        mock_modify_order.side_effect = ValueError("Order not found")
        
        modify_data = {"total_quantity": 200.0}
        response = client.put("/api/v1/orders/1", json=modify_data)
        assert response.status_code == 404
        assert "Order not found" in response.json()["detail"]
    
    @patch('app.services.ib_service.ib_service.modify_order')
    def test_modify_order_connection_error(self, mock_modify_order):
        """Test order modification with connection error."""
        mock_modify_order.side_effect = ConnectionError("Connection lost")
        
        modify_data = {"total_quantity": 200.0}
        response = client.put("/api/v1/orders/1", json=modify_data)
        assert response.status_code == 503
        assert "Connection lost" in response.json()["detail"]


class TestOrderCancellationEdgeCases:
    """Test edge cases for order cancellation operations."""
    
    @patch('app.services.ib_service.ib_service.cancel_order')
    def test_cancel_nonexistent_order(self, mock_cancel_order):
        """Test cancelling a non-existent order."""
        mock_cancel_order.return_value = False
        
        response = client.delete("/api/v1/orders/999999")
        assert response.status_code == 400
        assert "Failed to cancel order 999999" in response.json()["detail"]
    
    @patch('app.services.ib_service.ib_service.cancel_order')
    def test_cancel_order_connection_error(self, mock_cancel_order):
        """Test order cancellation with connection error."""
        mock_cancel_order.side_effect = ConnectionError("Connection lost")
        
        response = client.delete("/api/v1/orders/1")
        assert response.status_code == 503
        assert "Connection lost" in response.json()["detail"]
    
    @patch('app.services.ib_service.ib_service.cancel_all_open_orders')
    def test_cancel_all_orders_empty_list(self, mock_cancel_all):
        """Test cancelling all orders when no orders exist."""
        mock_cancel_all.return_value = {
            "message": "No open orders found",
            "cancelled": [],
            "failed": []
        }
        
        response = client.delete("/api/v1/orders/cancel-all")
        assert response.status_code == 200
        data = response.json()
        assert "No open orders found" in data["message"]
        assert data["cancelled"] == []
        assert data["failed"] == []
    
    @patch('app.services.ib_service.ib_service.cancel_all_open_orders')
    def test_cancel_all_orders_mixed_results(self, mock_cancel_all):
        """Test cancelling all orders with mixed success/failure."""
        mock_cancel_all.return_value = {
            "message": "Cancelled 2 orders, 1 failed",
            "cancelled": [
                {"order_id": 1, "client_id": 0, "symbol": "AAPL"},
                {"order_id": 2, "client_id": 0, "symbol": "GOOGL"}
            ],
            "failed": [
                {"order_id": 3, "client_id": 0, "reason": "Order already filled"}
            ]
        }
        
        response = client.delete("/api/v1/orders/cancel-all")
        assert response.status_code == 200
        data = response.json()
        assert len(data["cancelled"]) == 2
        assert len(data["failed"]) == 1
    
    @patch('app.services.ib_service.ib_service.cancel_all_open_orders')
    def test_cancel_all_orders_service_error(self, mock_cancel_all):
        """Test cancel all orders with service error."""
        mock_cancel_all.side_effect = ConnectionError("Connection lost")
        
        response = client.delete("/api/v1/orders/cancel-all")
        assert response.status_code == 503
        assert "Connection lost" in response.json()["detail"]


class TestPositionsAndAccountEdgeCases:
    """Test edge cases for positions and account data retrieval."""
    
    @patch('app.services.ib_service.ib_service.get_positions')
    def test_get_positions_empty_list(self, mock_get_positions):
        """Test retrieving positions when no positions exist."""
        mock_get_positions.return_value = []
        
        response = client.get("/api/v1/positions")
        assert response.status_code == 200
        assert response.json() == []
    
    @patch('app.services.ib_service.ib_service.get_positions')
    def test_get_positions_connection_error(self, mock_get_positions):
        """Test positions retrieval with connection error."""
        mock_get_positions.side_effect = ConnectionError("Connection lost")
        
        response = client.get("/api/v1/positions")
        assert response.status_code == 503
        assert "Connection lost" in response.json()["detail"]
    
    @patch('app.services.ib_service.ib_service.get_account_summary')
    def test_get_account_summary_empty_data(self, mock_get_account_summary):
        """Test retrieving account summary with empty data."""
        mock_get_account_summary.return_value = {}
        
        response = client.get("/api/v1/account")
        assert response.status_code == 200
        data = response.json()
        assert data["account_values"] == {}
        assert "timestamp" in data
    
    @patch('app.services.ib_service.ib_service.get_account_summary')
    def test_get_account_summary_connection_error(self, mock_get_account_summary):
        """Test account summary retrieval with connection error."""
        mock_get_account_summary.side_effect = ConnectionError("Connection lost")
        
        response = client.get("/api/v1/account")
        assert response.status_code == 503
        assert "Connection lost" in response.json()["detail"]


class TestEmergencyBreakerEdgeCases:
    """Test edge cases for emergency breaker functionality."""
    
    def test_trigger_emergency_breaker_no_reason(self):
        """Test triggering emergency breaker without reason."""
        response = client.post("/api/v1/emergency/breaker/trigger")
        assert response.status_code == 200
        data = response.json()
        assert "Emergency breaker activated" in data["message"]
    
    def test_trigger_emergency_breaker_with_reason(self):
        """Test triggering emergency breaker with reason."""
        reason = "Test trigger"
        response = client.post(f"/api/v1/emergency/breaker/trigger?reason={reason}")
        assert response.status_code == 200
        data = response.json()
        assert reason in data.get("reason", "")
    
    def test_reset_emergency_breaker(self):
        """Test resetting emergency breaker."""
        response = client.post("/api/v1/emergency/breaker/reset")
        assert response.status_code == 200
        data = response.json()
        assert "reset" in data["message"].lower() or "not active" in data["message"]
    
    def test_get_emergency_breaker_status(self):
        """Test getting emergency breaker status."""
        response = client.get("/api/v1/emergency/breaker/status")
        assert response.status_code == 200
        data = response.json()
        assert "active" in data
        assert "tws_connected" in data
        assert "message" in data
    
    def test_test_emergency_breaker(self):
        """Test emergency breaker test endpoint."""
        response = client.post("/api/v1/emergency/breaker/test")
        assert response.status_code == 200
        data = response.json()
        assert "test" in data
        assert data["test"] in ["PASSED", "WARNING"]
        assert "breaker_active" in data


class TestGeneralEdgeCases:
    """Test general edge cases and error conditions."""
    
    def test_invalid_http_methods(self):
        """Test endpoints with wrong HTTP methods."""
        # GET on POST endpoint
        response = client.get("/api/v1/orders")
        assert response.status_code == 200  # This is actually valid
        
        # POST on GET endpoint
        response = client.post("/api/v1/positions")
        assert response.status_code == 405  # Method not allowed
        
        # PUT on non-modifiable endpoint
        response = client.put("/api/v1/positions")
        assert response.status_code == 405
    
    def test_nonexistent_endpoints(self):
        """Test requests to non-existent endpoints."""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404
        
        response = client.post("/api/v1/invalid/endpoint")
        assert response.status_code == 404
    
    def test_malformed_request_headers(self):
        """Test requests with malformed headers."""
        # Invalid Content-Type
        response = client.post(
            "/api/v1/orders",
            data="invalid data",
            headers={"Content-Type": "application/xml"}
        )
        assert response.status_code == 422
    
    def test_large_request_payload(self):
        """Test with extremely large request payload."""
        large_payload = {
            "contract": {
                "symbol": "AAPL",
                "sec_type": "STK",
                "exchange": "SMART",
                "currency": "USD"
            },
            "action": "BUY",
            "order_type": "MKT",
            "total_quantity": 100.0,
            "time_in_force": "DAY",
            "outside_rth": False,
            "hidden": False,
            "large_field": "A" * 1000000  # 1MB of data
        }
        
        response = client.post("/api/v1/orders", json=large_payload)
        # Should handle large payloads gracefully
        assert response.status_code in [200, 201, 413, 422]
    
    def test_concurrent_requests(self):
        """Test concurrent requests to the same endpoint."""
        import threading
        import time
        
        results = []
        
        def make_request():
            response = client.get("/health")
            results.append(response.status_code)
        
        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should succeed
        assert all(status == 200 for status in results)
        assert len(results) == 10
    
    def test_health_endpoint_edge_cases(self):
        """Test health endpoint with various TWS connection states."""
        # Test normal case first
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "tws_connected" in data
        assert "version" in data
        
        # Test with query parameters (should be ignored)
        response = client.get("/health?param=value")
        assert response.status_code == 200
    
    def test_root_endpoint_edge_cases(self):
        """Test root endpoint edge cases."""
        # Normal request
        response = client.get("/")
        assert response.status_code == 200
        
        # With query parameters (should be ignored)
        response = client.get("/?test=value")
        assert response.status_code == 200
        
        # POST to root (should fail)
        response = client.post("/")
        assert response.status_code == 405