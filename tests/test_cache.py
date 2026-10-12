import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pc_monitor as monitor


class CacheTests(unittest.TestCase):
    def test_http_failure_is_not_success(self):
        tv = monitor.SmallTV('invalid.example')
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError('503')
        with patch.object(tv, 'get', return_value=response):
            with self.assertRaises(requests.HTTPError):
                tv.delete_image('pcmon_test.jpg')

    def test_cleanup_preserves_failures_and_foreign_files(self):
        tv = Mock()
        tv.delete_image.side_effect = [requests.Timeout(), Mock()]
        state = {'frames': [{'filename': x} for x in ['pcmon_a.jpg', 'photo.jpg', 'pcmon_b.jpg']]}
        with patch.object(monitor, 'save_state') as save:
            monitor.cleanup(tv, state)
        self.assertEqual([x['filename'] for x in state['frames']], ['pcmon_a.jpg', 'photo.jpg'])
        save.assert_called_once_with(state)
        self.assertEqual(tv.delete_image.call_count, 2)

    def test_trim_failure_terminates_and_keeps_retry_state(self):
        tv = Mock()
        tv.delete_image.side_effect = requests.ConnectionError()
        state = {'frames': [{'filename': 'pcmon_a.jpg'}, {'filename': 'pcmon_b.jpg'}]}
        with patch.object(monitor, 'save_state'):
            monitor.trim_cache(tv, state, 1)
        self.assertEqual(len(state['frames']), 2)
        self.assertEqual(tv.delete_image.call_count, 2)

    def test_trim_removes_only_needed_owned_entries(self):
        state = {'frames': [{'filename': x} for x in ['photo.jpg', 'pcmon_a.jpg', 'pcmon_b.jpg']]}
        tv = Mock()
        with patch.object(monitor, 'save_state'):
            monitor.trim_cache(tv, state, 2)
        self.assertEqual([x['filename'] for x in state['frames']], ['photo.jpg', 'pcmon_b.jpg'])
        tv.delete_image.assert_called_once_with('pcmon_a.jpg')

    def test_paths_and_foreign_names_never_reach_network(self):
        tv = monitor.SmallTV('invalid.example')
        with patch.object(tv, 'get') as get:
            for name in ('photo.jpg', 'pcmon_../../photo.jpg', 'pcmon_a/b.jpg', None):
                with self.assertRaises(ValueError):
                    tv.delete_image(name)
        get.assert_not_called()
