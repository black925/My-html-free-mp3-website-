import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from server import download_url_to_file


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'hello downloader')

    def log_message(self, format, *args):
        return


class DownloadUrlToFileTests(unittest.TestCase):
    def test_downloads_a_public_url_to_disk(self):
        server = HTTPServer(('127.0.0.1', 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = os.path.join(tmpdir, 'downloaded.txt')
                result = download_url_to_file(f'http://127.0.0.1:{port}/sample', output_path)
                self.assertTrue(result)
                with open(output_path, 'rb') as handle:
                    self.assertEqual(handle.read(), b'hello downloader')
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
