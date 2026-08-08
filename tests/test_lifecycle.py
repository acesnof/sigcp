import unittest

import main


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += float(seconds)


class BrowserLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.shutdowns = []
        self.lifecycle = main.BrowserLifecycle(
            lambda: self.shutdowns.append("shutdown"),
            stale_after=10,
            close_grace=2,
            clock=self.clock,
        )

    def test_closing_the_last_tab_stops_after_the_refresh_grace_period(self):
        self.lifecycle.signal("tab-1", "heartbeat")
        self.lifecycle.signal("tab-1", "close")
        self.clock.advance(1.9)
        self.assertFalse(self.lifecycle.poll())
        self.assertEqual([], self.shutdowns)
        self.clock.advance(0.2)
        self.assertTrue(self.lifecycle.poll())
        self.assertEqual(["shutdown"], self.shutdowns)

    def test_refresh_or_another_tab_cancels_shutdown(self):
        self.lifecycle.signal("old-page", "heartbeat")
        self.lifecycle.signal("old-page", "close")
        self.clock.advance(0.5)
        self.lifecycle.signal("refreshed-page", "heartbeat")
        self.clock.advance(3)
        self.assertFalse(self.lifecycle.poll())
        self.assertEqual([], self.shutdowns)

        self.lifecycle.signal("second-tab", "heartbeat")
        self.lifecycle.signal("refreshed-page", "close")
        self.clock.advance(3)
        self.assertFalse(self.lifecycle.poll())
        self.assertEqual([], self.shutdowns)

    def test_missing_heartbeats_eventually_stop_a_seen_browser(self):
        self.lifecycle.signal("crashed-tab", "heartbeat")
        self.clock.advance(11)
        self.assertFalse(self.lifecycle.poll())
        self.clock.advance(2.1)
        self.assertTrue(self.lifecycle.poll())
        self.assertEqual(["shutdown"], self.shutdowns)

    def test_server_without_any_browser_does_not_stop_itself(self):
        self.clock.advance(999)
        self.assertFalse(self.lifecycle.poll())
        self.assertEqual([], self.shutdowns)


if __name__ == "__main__":
    unittest.main()
