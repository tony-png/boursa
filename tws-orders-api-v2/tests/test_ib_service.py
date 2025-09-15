import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from app.services.ib_service import IBService
from app.config import settings


class TestIBService:
    """Test suite for the IB service."""
    
    @pytest.fixture
    def ib_service(self):
        """Create an IB service instance for testing."""
        return IBService()
    
    @pytest.fixture
    def mock_ib(self):
        """Create a mock IB instance."""
        mock_ib = MagicMock()
        mock_ib.connectAsync = AsyncMock()
        mock_ib.isConnected.return_value = True
        mock_ib.qualifyContractsAsync = AsyncMock()
        mock_ib.placeOrder = MagicMock()
        mock_ib.cancelOrder = MagicMock()
        mock_ib.trades.return_value = []
        mock_ib.positions.return_value = []
        mock_ib.accountSummary.return_value = []
        mock_ib.disconnect = MagicMock()
        mock_ib.orderStatusEvent = MagicMock()
        mock_ib.execDetailsEvent = MagicMock()
        return mock_ib
    
    @pytest.mark.asyncio
    async def test_connect_success(self, ib_service, mock_ib):
        """Test successful connection to TWS."""
        ib_service.ib = mock_ib
        
        result = await ib_service.connect()
        
        assert result is True
        assert ib_service._is_connected is True
        mock_ib.connectAsync.assert_called_once_with(
            host=settings.tws_host,
            port=settings.tws_port,
            clientId=settings.client_id,
            timeout=settings.connection_timeout
        )
    
    @pytest.mark.asyncio
    async def test_connect_failure(self, ib_service, mock_ib):
        """Test connection failure to TWS."""
        ib_service.ib = mock_ib
        mock_ib.connectAsync.side_effect = Exception("Connection failed")
        
        result = await ib_service.connect()
        
        assert result is False
        assert ib_service._is_connected is False
    
    @pytest.mark.asyncio
    async def test_disconnect(self, ib_service, mock_ib):
        """Test disconnection from TWS."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        
        await ib_service.disconnect()
        
        assert ib_service._is_connected is False
        mock_ib.disconnect.assert_called_once()
    
    def test_is_connected(self, ib_service, mock_ib):
        """Test connection status check."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        
        assert ib_service.is_connected() is True
        
        ib_service._is_connected = False
        assert ib_service.is_connected() is False
    
    @pytest.mark.asyncio
    async def test_ensure_connected_already_connected(self, ib_service, mock_ib):
        """Test ensure_connected when already connected."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        
        # Should not raise an exception
        await ib_service.ensure_connected()
    
    @pytest.mark.asyncio
    async def test_ensure_connected_reconnect_success(self, ib_service, mock_ib):
        """Test ensure_connected with successful reconnection."""
        ib_service.ib = mock_ib
        ib_service._is_connected = False
        mock_ib.isConnected.return_value = False
        
        with patch.object(ib_service, 'connect', return_value=True) as mock_connect:
            await ib_service.ensure_connected()
            mock_connect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_ensure_connected_reconnect_failure(self, ib_service, mock_ib):
        """Test ensure_connected with failed reconnection."""
        ib_service.ib = mock_ib
        ib_service._is_connected = False
        mock_ib.isConnected.return_value = False
        
        with patch.object(ib_service, 'connect', return_value=False) as mock_connect:
            with pytest.raises(ConnectionError):
                await ib_service.ensure_connected()
    
    @pytest.mark.asyncio
    async def test_create_contract_success(self, ib_service, mock_ib):
        """Test successful contract creation."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        
        mock_contract = MagicMock()
        mock_contract.symbol = "AAPL"
        mock_ib.qualifyContractsAsync.return_value = [mock_contract]
        
        result = await ib_service.create_contract("AAPL")
        
        assert result == mock_contract
        mock_ib.qualifyContractsAsync.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_contract_no_qualified(self, ib_service, mock_ib):
        """Test contract creation with no qualified contracts."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        mock_ib.qualifyContractsAsync.return_value = []
        
        with pytest.raises(ValueError, match="Could not qualify contract"):
            await ib_service.create_contract("INVALID")
    
    @pytest.mark.asyncio
    async def test_place_order(self, ib_service, mock_ib):
        """Test placing an order."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        
        mock_contract = MagicMock()
        mock_order = MagicMock()
        mock_order.orderId = 1
        mock_trade = MagicMock()
        
        mock_ib.placeOrder.return_value = mock_trade
        
        result = await ib_service.place_order(mock_contract, mock_order)
        
        assert result == mock_trade
        mock_ib.placeOrder.assert_called_once_with(mock_contract, mock_order)
    
    @pytest.mark.asyncio
    async def test_cancel_order(self, ib_service, mock_ib):
        """Test cancelling an order."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        
        # Mock get_order to return a trade object
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1
        mock_trade.orderStatus.status = "PreSubmitted"
        
        with patch.object(ib_service, 'get_order', return_value=mock_trade) as mock_get_order:
            result = await ib_service.cancel_order(1)
        
        assert result is True
        mock_get_order.assert_called_once_with(1)
        mock_ib.cancelOrder.assert_called_once_with(mock_trade.order)
    
    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, ib_service, mock_ib):
        """Test order cancellation failure."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        mock_ib.cancelOrder.side_effect = Exception("Cancel failed")
        
        result = await ib_service.cancel_order(1)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_orders(self, ib_service, mock_ib):
        """Test retrieving orders."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        
        mock_trades = [MagicMock(), MagicMock()]
        mock_ib.trades.return_value = mock_trades
        
        result = await ib_service.get_orders()
        
        assert result == mock_trades
        mock_ib.trades.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_order(self, ib_service, mock_ib):
        """Test retrieving a specific order."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1
        mock_ib.trades.return_value = [mock_trade]
        
        result = await ib_service.get_order(1)
        
        assert result == mock_trade
    
    @pytest.mark.asyncio
    async def test_get_order_not_found(self, ib_service, mock_ib):
        """Test retrieving a non-existent order."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        mock_ib.trades.return_value = []
        
        result = await ib_service.get_order(999)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_positions(self, ib_service, mock_ib):
        """Test retrieving positions."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        
        mock_positions = [MagicMock(), MagicMock()]
        mock_ib.positions.return_value = mock_positions
        
        result = await ib_service.get_positions()
        
        assert result == mock_positions
        mock_ib.positions.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_account_summary(self, ib_service, mock_ib):
        """Test retrieving account summary."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        
        mock_account_value = MagicMock()
        mock_account_value.tag = "NetLiquidation"
        mock_account_value.value = "100000.00"
        mock_account_value.currency = "USD"
        mock_account_value.account = "DU123456"
        
        mock_ib.accountSummary.return_value = [mock_account_value]
        
        result = await ib_service.get_account_summary()
        
        assert "NetLiquidation" in result
        assert result["NetLiquidation"]["value"] == "100000.00"
        assert result["NetLiquidation"]["currency"] == "USD"
    
    @pytest.mark.asyncio
    async def test_modify_order_success(self, ib_service, mock_ib):
        """Test successful order modification."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1
        mock_trade.order.totalQuantity = 100
        mock_trade.contract = MagicMock()
        mock_ib.trades.return_value = [mock_trade]
        
        result = await ib_service.modify_order(1, totalQuantity=200)
        
        assert result is True
        assert mock_trade.order.totalQuantity == 200
        mock_ib.placeOrder.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_modify_order_not_found(self, ib_service, mock_ib):
        """Test order modification with non-existent order."""
        ib_service.ib = mock_ib
        ib_service._is_connected = True
        mock_ib.isConnected.return_value = True
        mock_ib.trades.return_value = []
        
        with pytest.raises(ValueError, match="Order 999 not found"):
            await ib_service.modify_order(999, totalQuantity=200)
    
    def test_on_order_status(self, ib_service):
        """Test order status event handler."""
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1
        mock_trade.orderStatus.status = "Filled"
        
        # Should not raise an exception
        ib_service._on_order_status(mock_trade)
    
    def test_on_execution(self, ib_service):
        """Test execution event handler."""
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1
        
        mock_fill = MagicMock()
        mock_fill.execution.shares = 100
        mock_fill.execution.price = 150.0
        
        # Should not raise an exception
        ib_service._on_execution(mock_trade, mock_fill)