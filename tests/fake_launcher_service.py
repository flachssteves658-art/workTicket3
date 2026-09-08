"""Small HTTP service for launcher lifecycle tests; no project imports."""
import http.server
import json
import sys


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        payload = json.dumps({'paths': {'/launcher-test': {}}}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
