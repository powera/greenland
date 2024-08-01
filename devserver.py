#!/usr/bin/python3

import http.server
import os
import os.path

# watchdog for file changes
# TODO: implement
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

HTML_WRAPPER = b"""
<html>
  <head>
    <title>DEVSERVER</title>
    <link rel="stylesheet" type="text/css" href="/css/main.css" />
    <link rel="stylesheet" type="text/css" href="/css/wiki.css" />
    <script lang="javascript" src="/js/main.js"></script>
  </head>
  <body><div class="terminal">%s</div></body>
</html>
"""


class InboundRequest(http.server.BaseHTTPRequestHandler):

  def do_GET(self):
    if self.path == "/favicon.ico":
      return self.FaviconHandler()
    if self.path.startswith("/images/"):
      return self.StaticHandler()
    if self.path.startswith("/css/"):
      return self.StaticHandler()
    if self.path.startswith("/js/"):
      return self.StaticHandler()
    # the fallback handler is the "jinja2" handler for the domain
    return domains.serve(self)

  def StaticHandler(self):
    # Handle a request for a static file.
    path = os.path.join("public_html" + self.path)
    with open(path, mode='rb') as f:
      response = f.read()

    self.send_response(200)
    if self.path.startswith("/images/"):
      self.send_header("Content-type", "image/png")
      self.send_header("Cache-control", "public, max-age=3600")
    elif self.path.startswith("/css/"):
      self.send_header("Content-type", "text/css")
    elif self.path.startswith("/js/"):
      self.send_header("Content-type", "text/javascript")
    else:
      self.send_header("Content-type", "text/html; charset=utf-8")
    self.send_header("Content-length", len(response))
    self.end_headers()
    self.wfile.write(response)

  def FaviconHandler(self):
    path = "public_html/favicon.ico"
    with open(path, mode='rb') as f:
      response = f.read()
    self.send_response(200)
    self.send_header("Content-type", "image/x-icon")
    self.send_header("Content-length", len(response))
    self.end_headers()
    self.wfile.write(response)


def run(server_class=http.server.HTTPServer, handler_class=InboundRequest):
  server_address = ('', 14001)
  httpd = server_class(server_address, handler_class)
  httpd.serve_forever()


if __name__ == "__main__":
  run()
