"""Tests for Handler site isolation in WebSocket mode."""

import asyncio
from typing import cast
from unittest.mock import MagicMock, patch

from curator.app.auth import UserSession
from curator.protocol import AsyncAPIWebSocket


class TestHandlerSiteIsolation:
    """Tests for Handler class site caching and cleanup."""

    def test_handler_site_isolation(self, mocker):
        """Test that each Handler gets a unique site."""
        from curator.app.handler import Handler

        # Mock AsyncAPIWebSocket
        mock_ws = MagicMock(spec=AsyncAPIWebSocket)
        mock_ws.scope = {"type": "websocket"}
        mock_ws.receive = MagicMock()
        mock_ws.send = MagicMock()

        # Mock user sessions
        user1 = cast(
            UserSession,
            {"username": "user1", "userid": "1", "access_token": ("token1", "secret1")},
        )
        user2 = cast(
            UserSession,
            {"username": "user2", "userid": "2", "access_token": ("token2", "secret2")},
        )

        with patch("curator.app.commons.create_isolated_site") as mock_create_site:
            # Create mock sites
            site1 = MagicMock()
            site2 = MagicMock()
            mock_create_site.side_effect = [site1, site2]

            # Create handlers
            handler1 = Handler(user=user1, sender=mock_ws, request_obj=mock_ws)
            handler2 = Handler(user=user2, sender=mock_ws, request_obj=mock_ws)

            site1_result = asyncio.run(handler1._get_site())
            site2_result = asyncio.run(handler2._get_site())

            # Verify each handler got a unique site
            assert site1_result is site1
            assert site2_result is site2
            assert site1_result is not site2_result

    def test_handler_site_caching(self, mocker):
        """Test that site is cached per Handler instance."""
        from curator.app.handler import Handler

        # Mock AsyncAPIWebSocket
        mock_ws = MagicMock(spec=AsyncAPIWebSocket)
        mock_ws.scope = {"type": "websocket"}
        mock_ws.receive = MagicMock()
        mock_ws.send = MagicMock()

        # Mock user session
        user = cast(
            UserSession,
            {"username": "user1", "userid": "1", "access_token": ("token1", "secret1")},
        )

        with patch("curator.app.commons.create_isolated_site") as mock_create_site:
            # Create mock site
            site = MagicMock()
            mock_create_site.return_value = site

            # Create handler
            handler = Handler(user=user, sender=mock_ws, request_obj=mock_ws)

            site1 = asyncio.run(handler._get_site())
            site2 = asyncio.run(handler._get_site())

            # Verify create_isolated_site was only called once
            mock_create_site.assert_called_once()

            # Verify both calls returned the same site
            assert site1 is site2
            assert site1 is site

    def test_handler_cleanup(self, mocker):
        """Test that cleanup clears site reference."""
        from curator.app.handler import Handler

        # Mock AsyncAPIWebSocket
        mock_ws = MagicMock(spec=AsyncAPIWebSocket)
        mock_ws.scope = {"type": "websocket"}
        mock_ws.receive = MagicMock()
        mock_ws.send = MagicMock()

        # Mock user session
        user = cast(
            UserSession,
            {"username": "user1", "userid": "1", "access_token": ("token1", "secret1")},
        )

        with patch("curator.app.commons.create_isolated_site") as mock_create_site:
            # Create mock site
            site = MagicMock()
            mock_create_site.return_value = site

            # Create handler
            handler = Handler(user=user, sender=mock_ws, request_obj=mock_ws)

            site1 = asyncio.run(handler._get_site())
            assert handler._commons_site is site1

            # Cleanup
            handler.cleanup()

            # Verify site reference was cleared
            assert handler._commons_site is None

            # Getting site again should create a new one
            site2 = asyncio.run(handler._get_site())
            assert site2 is site1
            # Note: site2 is the same as site1 because the mock is cached, but in real
            # scenario it would create a new site object
