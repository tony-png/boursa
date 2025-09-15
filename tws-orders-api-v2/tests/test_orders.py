import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

from app.main import app
from app.models.orders import OrderAction, OrderType, SecurityType, TimeInForce


client = TestClient(app)


class TestOrderEndpoints:
    """Test suite for order management endpoints."""
    
    @pytest.fixture
    def mock_trade(self):
        """Create a mock trade object."""
        trade = MagicMock()
        trade.order.orderId = 1
        trade.order.clientId = 1
        trade.order.permId = 123456
        trade.order.action = "BUY"
        trade.order.orderType = "MKT"
        trade.order.totalQuantity = 100.0
        trade.order.cashQty = None
        trade.order.lmtPrice = None
        trade.order.auxPrice = None
        trade.order.tif = "DAY"
        trade.order.outsideRth = False
        trade.order.hidden = False
        trade.order.goodAfterTime = None
        trade.order.goodTillDate = None
        
        trade.orderStatus.status = "Submitted"
        trade.orderStatus.filled = 0.0
        trade.orderStatus.remaining = 100.0
        trade.orderStatus.avgFillPrice = 0.0
        trade.orderStatus.lastFillPrice = 0.0
        trade.orderStatus.whyHeld = None
        
        trade.contract.symbol = "AAPL"
        trade.contract.secType = "STK"
        trade.contract.exchange = "SMART"
        trade.contract.currency = "USD"
        trade.contract.localSymbol = "AAPL"
        trade.contract.tradingClass = "NMS"
        trade.contract.conId = 265598
        
        trade.fills = []
        trade.log = []
        
        return trade
    
    @pytest.fixture
    def order_request_data(self):
        """Create sample order request data."""
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
    
    @patch('app.services.ib_service.ib_service.create_contract')
    @patch('app.services.ib_service.ib_service.place_order')
    def test_create_order(self, mock_place_order, mock_create_contract, order_request_data, mock_trade):
        """Test creating a new order."""
        # Mock the contract creation
        mock_contract = MagicMock()
        mock_contract.symbol = "AAPL"
        mock_create_contract.return_value = mock_contract
        
        # Mock the order placement
        mock_place_order.return_value = mock_trade
        
        response = client.post("/api/v1/orders", json=order_request_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["order"]["order_id"] == 1
        assert data["order"]["action"] == "BUY"
        assert data["contract"]["symbol"] == "AAPL"
    
    def test_create_order_validation_error(self):
        """Test order creation with validation errors."""
        invalid_data = {
            "contract": {
                "symbol": "",  # Empty symbol should fail validation
                "sec_type": "STK"
            },
            "action": "BUY",
            "order_type": "MKT",
            "total_quantity": -100.0,  # Negative quantity should fail
        }
        
        response = client.post("/api/v1/orders", json=invalid_data)
        assert response.status_code == 422  # Validation error
    
    @patch('app.services.ib_service.ib_service.get_orders')
    def test_get_orders(self, mock_get_orders, mock_trade):
        """Test retrieving all orders."""
        mock_get_orders.return_value = [mock_trade]
        
        response = client.get("/api/v1/orders")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["order"]["order_id"] == 1
    
    @patch('app.services.ib_service.ib_service.get_order')
    def test_get_order_by_id(self, mock_get_order, mock_trade):
        """Test retrieving a specific order by ID."""
        mock_get_order.return_value = mock_trade
        
        response = client.get("/api/v1/orders/1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["order"]["order_id"] == 1
    
    @patch('app.services.ib_service.ib_service.get_order')
    def test_get_order_not_found(self, mock_get_order):
        """Test retrieving a non-existent order."""
        mock_get_order.return_value = None
        
        response = client.get("/api/v1/orders/999")
        
        assert response.status_code == 404
        data = response.json()
        assert "Order 999 not found" in data["detail"]
    
    @patch('app.services.ib_service.ib_service.modify_order')
    def test_modify_order(self, mock_modify_order):
        """Test modifying an existing order."""
        mock_modify_order.return_value = True
        
        modify_data = {
            "total_quantity": 200.0,
            "limit_price": 150.0
        }
        
        response = client.put("/api/v1/orders/1", json=modify_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "Order 1 modified successfully" in data["message"]
    
    @patch('app.services.ib_service.ib_service.modify_order')
    def test_modify_order_failure(self, mock_modify_order):
        """Test order modification failure."""
        mock_modify_order.return_value = False
        
        modify_data = {
            "total_quantity": 200.0
        }
        
        response = client.put("/api/v1/orders/1", json=modify_data)
        
        assert response.status_code == 400
    
    def test_modify_order_no_changes(self):
        """Test order modification with no changes."""
        response = client.put("/api/v1/orders/1", json={})
        
        assert response.status_code == 400
        data = response.json()
        assert "No modifications provided" in data["detail"]
    
    @patch('app.services.ib_service.ib_service.cancel_order')
    def test_cancel_order(self, mock_cancel_order):
        """Test cancelling an order."""
        mock_cancel_order.return_value = True
        
        response = client.delete("/api/v1/orders/1")
        
        assert response.status_code == 200
        data = response.json()
        assert "Order 1 cancellation requested" in data["message"]
    
    @patch('app.services.ib_service.ib_service.cancel_order')
    def test_cancel_order_failure(self, mock_cancel_order):
        """Test order cancellation failure."""
        mock_cancel_order.return_value = False
        
        response = client.delete("/api/v1/orders/1")
        
        assert response.status_code == 400
    
    @patch('app.services.ib_service.ib_service.get_positions')
    def test_get_positions(self, mock_get_positions):
        """Test retrieving positions."""
        mock_position = MagicMock()
        mock_position.account = "DU123456"
        mock_position.contract.symbol = "AAPL"
        mock_position.contract.secType = "STK"
        mock_position.contract.exchange = "SMART"
        mock_position.contract.currency = "USD"
        mock_position.contract.localSymbol = "AAPL"
        mock_position.contract.tradingClass = "NMS"
        mock_position.contract.conId = 265598
        mock_position.position = 100.0
        mock_position.avgCost = 150.0
        
        mock_get_positions.return_value = [mock_position]
        
        response = client.get("/api/v1/positions")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["account"] == "DU123456"
        assert data[0]["position"] == 100.0
    
    @patch('app.services.ib_service.ib_service.get_account_summary')
    def test_get_account_summary(self, mock_get_account_summary):
        """Test retrieving account summary."""
        mock_summary = {
            "NetLiquidation": {
                "value": "100000.00",
                "currency": "USD",
                "account": "DU123456"
            }
        }
        mock_get_account_summary.return_value = mock_summary
        
        response = client.get("/api/v1/account")
        
        assert response.status_code == 200
        data = response.json()
        assert "account_values" in data
        assert "timestamp" in data
    
    @patch('app.services.ib_service.ib_service.create_contract')
    def test_create_order_connection_error(self, mock_create_contract, order_request_data):
        """Test order creation with connection error."""
        mock_create_contract.side_effect = ConnectionError("Connection lost")
        
        response = client.post("/api/v1/orders", json=order_request_data)
        
        assert response.status_code == 503
        data = response.json()
        assert "Connection lost" in data["detail"]