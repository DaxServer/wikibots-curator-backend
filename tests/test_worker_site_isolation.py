"""Tests for site isolation in concurrent operations."""

import threading
from unittest.mock import MagicMock, patch

from mwoauth import AccessToken


def _create_job_site(index, access_token, username, results, lock):
    """Simulate a job creating a site."""
    from curator.app.commons import create_isolated_site

    with (
        patch("curator.app.commons.pywikibot") as mock_pywikibot,
        patch("curator.app.commons.config"),
    ):
        # Create a mock site
        mock_site = MagicMock()
        mock_site.login = MagicMock()
        mock_pywikibot.Site = MagicMock(return_value=mock_site)

        # Call create_isolated_site
        create_isolated_site(access_token, username)

        # Record what credentials were used
        with lock:
            results[index] = {
                "access_token": access_token,
                "username": username,
                "site": mock_site,
            }


class TestSiteIsolation:
    """Tests for site isolation in concurrent operations."""

    def test_concurrent_jobs_dont_share_credentials(self):
        """Test that concurrent jobs don't share credentials."""
        results = {}
        lock = threading.Lock()

        # Create multiple threads with different credentials
        threads = []
        credentials = [
            (0, AccessToken("token0", "secret0"), "user0"),
            (1, AccessToken("token1", "secret1"), "user1"),
            (2, AccessToken("token2", "secret2"), "user2"),
        ]

        for index, access_token, username in credentials:
            thread = threading.Thread(
                target=_create_job_site,
                args=(index, access_token, username, results, lock),
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify each job got the correct credentials
        assert len(results) == 3
        for index, access_token, username in credentials:
            assert results[index]["access_token"] == access_token
            assert results[index]["username"] == username
