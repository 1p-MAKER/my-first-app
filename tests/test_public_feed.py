import io
import json
import os
import unittest
from email.message import Message
from unittest.mock import patch
import verify_public_feed as verify


class PublicFeedTests(unittest.TestCase):
    @patch.dict(os.environ, {'PAGE_URL': 'https://example.com/news/'})
    @patch('verify_public_feed.time.sleep')
    @patch('verify_public_feed.Path.read_text', return_value='[{"uid":"new"}]')
    @patch('verify_public_feed.urllib.request.urlopen')
    def test_requires_current_json_and_mime(self, opener, read, sleep):
        for mime, data, passes in [('application/json', [{'uid': 'new'}], True),
                                    ('application/json', [{'uid': 'old'}], False),
                                    ('text/html', [{'uid': 'new'}], False)]:
            opener.reset_mock()
            def open_response(*args, **kwargs):
                stream = io.BytesIO(json.dumps(data).encode())
                stream.headers = Message()
                stream.headers['Content-Type'] = mime
                return stream
            opener.side_effect = open_response
            if passes:
                verify.main()
                self.assertEqual(opener.call_count, 1)
            else:
                with self.assertRaises(RuntimeError):
                    verify.main()
                self.assertEqual(opener.call_count, 6)
