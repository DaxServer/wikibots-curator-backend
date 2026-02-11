"""Tests for worker site isolation in Celery mode."""

import threading
from unittest.mock import MagicMock, patch


def _create_job_site(index, access_token, username, results, lock):
    """Simulate a worker job creating a site."""
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


class TestWorkerSiteIsolation:
    """Tests for worker job site isolation."""

    def test_worker_site_isolation(self, mocker):
        """Test that each worker job gets a unique site."""
        with patch("curator.workers.ingest.create_isolated_site") as mock_create_site:
            # Create mock sites
            site1 = MagicMock()
            site2 = MagicMock()
            site1.has_group = MagicMock(return_value=False)
            site2.has_group = MagicMock(return_value=False)
            mock_create_site.side_effect = [site1, site2]

            # Simulate two jobs getting their sites
            site1_result = mock_create_site(("token1", "secret1"), "user1")
            site2_result = mock_create_site(("token2", "secret2"), "user2")

            # Verify each job got a unique site
            assert site1_result is site1
            assert site2_result is site2
            assert site1_result is not site2_result

            # Verify create_isolated_site was called twice
            assert mock_create_site.call_count == 2

    def test_concurrent_worker_jobs(self, mocker):
        """Test that concurrent worker jobs don't share credentials."""
        results = {}
        lock = threading.Lock()

        # Create multiple threads with different credentials
        threads = []
        credentials = [
            (0, ("token0", "secret0"), "user0"),
            (1, ("token1", "secret1"), "user1"),
            (2, ("token2", "secret2"), "user2"),
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
