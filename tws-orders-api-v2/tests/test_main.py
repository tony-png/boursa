import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app


client = TestClient(app)


class TestMainEndpoints:
    """Test suite for main application endpoints."""
    
    def test_root_endpoint(self):
        """Test the root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "docs" in data
        assert data["message"] == "Welcome to TWS Orders API v2"
    
    @patch('app.services.ib_service.ib_service.is_connected')
    def test_health_check_connected(self, mock_is_connected):
        """Test health check when TWS is connected."""
        mock_is_connected.return_value = True
        
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["tws_connected"] is True
        assert "version" in data
    
    @patch('app.services.ib_service.ib_service.is_connected')
    def test_health_check_disconnected(self, mock_is_connected):
        """Test health check when TWS is disconnected."""
        mock_is_connected.return_value = False
        
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "degraded"
        assert data["tws_connected"] is False
        assert "version" in data
    
    def test_docs_endpoint(self):
        """Test that docs endpoint is accessible."""
        response = client.get("/docs")
        assert response.status_code == 200
    
    def test_redoc_endpoint(self):
        """Test that redoc endpoint is accessible."""
        response = client.get("/redoc")
        assert response.status_code == 200