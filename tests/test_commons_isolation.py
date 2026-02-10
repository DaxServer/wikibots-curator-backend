"""Tests for site isolation and thread safety."""

import threading
from unittest.mock import MagicMock, patch

from curator.app.commons import IsolatedSite, create_isolated_site


class TestSiteIsolation:
    """Tests for proper site isolation between threads."""

    def test_isolated_site_wrapper(self):
        """Test that create_isolated_site returns an IsolatedSite wrapper."""
        site = create_isolated_site(("token", "secret"), "user")
        assert isinstance(site, IsolatedSite)
        assert site.access_token == ("token", "secret")
        assert site.username == "user"

    def test_run_sync_sets_context(self):
        """Test that run_sync sets up the context before calling the function."""
        with (
            patch("curator.app.commons.pywikibot") as mock_pywikibot,
            patch("curator.app.commons.config") as mock_config,
            patch("curator.app.commons.OAUTH_KEY", "test_key"),
            patch("curator.app.commons.OAUTH_SECRET", "test_secret"),
        ):
            # Setup mock config
            mock_config.authenticate = {}
            mock_config.usernames = {"commons": {"commons": "old_user"}}

            # Setup mock site
            mock_site_obj = MagicMock()
            mock_pywikibot.Site.return_value = mock_site_obj

            site = create_isolated_site(("new_token", "new_secret"), "new_user")

            result = site.run_sync(
                self._verify_sync_context,
                "foo",
                mock_config=mock_config,
                mock_site_obj=mock_site_obj,
            )

            assert result == "result_foo"
            mock_pywikibot.Site.assert_called_once_with(
                "commons", "commons", user="new_user"
            )
            mock_site_obj.login.assert_called_once()

    def _verify_sync_context(self, s, arg1, mock_config, mock_site_obj):
        # Verify config is set inside the function
        assert mock_config.authenticate["commons.wikimedia.org"] == (
            "test_key",
            "test_secret",
            "new_token",
            "new_secret",
        )
        assert mock_config.usernames["commons"]["commons"] == "new_user"
        assert s == mock_site_obj
        return f"result_{arg1}"

    def test_no_credential_leakage_between_threads(self):
        """Test that credentials don't leak between concurrent site usage."""
        # Use real ThreadLocalDict logic
        from curator.app.thread_utils import ThreadLocalDict

        mock_config = MagicMock()
        # Initialize with ThreadLocalDict to simulate the patched state
        mock_config.authenticate = ThreadLocalDict({})
        mock_config.usernames = {"commons": {"commons": "default"}}
        mock_config.put_throttle = 100

        results = {}
        lock = threading.Lock()

        context = LeakageTestContext(mock_config, results, lock)

        # Patch globally for all threads
        with (
            patch("curator.app.commons.pywikibot") as mock_pywikibot,
            patch("curator.app.commons.config", mock_config),
            patch("curator.app.commons.OAUTH_KEY", "key"),
            patch("curator.app.commons.OAUTH_SECRET", "secret"),
        ):
            mock_pywikibot.Site.side_effect = _mock_site_factory

            threads = []
            creds = [
                (0, ("t0", "s0"), "u0"),
                (1, ("t1", "s1"), "u1"),
                (2, ("t2", "s2"), "u2"),
            ]

            for idx, token, user in creds:
                t = threading.Thread(target=context.run_thread, args=(idx, token, user))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            assert len(results) == 3
            for i in range(3):
                # Auth must be correct for this thread
                assert results[i]["auth"] == ("key", "secret") + creds[i][1]
                # Site user must be correct
                assert results[i]["site_user"] == creds[i][2]


class LeakageTestContext:
    def __init__(self, mock_config, results, lock):
        self.mock_config = mock_config
        self.results = results
        self.lock = lock

    def run_thread(self, index, access_token, username):
        site = create_isolated_site(access_token, username)
        site.run_sync(self.capture_config, index)

    def capture_config(self, s, index):
        import time

        time.sleep(0.05)  # Encourage race conditions

        with self.lock:
            self.results[index] = {
                "auth": self.mock_config.authenticate.get("commons.wikimedia.org"),
                "site_user": s.user_arg,
            }


def _mock_site_factory(fam, code, user):
    m = MagicMock()
    m.user_arg = user
    m.login = MagicMock()
    return m
