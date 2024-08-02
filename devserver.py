#!/usr/bin/python3

import http.server
import json
import os
import os.path

# watchdog for file changes
# TODO: implement
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# jinja2 template
from jinja2 import Environment, PackageLoader, select_autoescape
env = None  # lazy loading

# verbalator imports; this should be elsewhere
import ollama  # local ollama
import verbalator.common
import verbalator.samples

PORT = 9871


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
    return self.WrapperHandler()

  def do_POST(self):
    if self.path == '/query':
      content_length = int(self.headers['Content-Length'])
      post_data = self.rfile.read(content_length)
      data = json.loads(post_data.decode('utf-8'))

      prompt = verbalator.common.PROMPTS[data.get('prompt')]
      entry = data.get('entry')
      model = data.get('model', 'phi3:3.8b')

      if not prompt:
        self.send_error(400, "No prompt provided")
        return

      # TODO: don't concatenate prompt + entry
      response = ollama.generate_text(prompt + "\n\n" + entry, model)

      self.send_response(200)
      self.send_header('Content-type', 'application/json')
      self.send_header('Access-Control-Allow-Origin', '*')  # CORS header
      self.end_headers()
      self.wfile.write(json.dumps({"response": response}).encode())
    else:
      self.send_error(404, "Not Found")


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

  def WrapperHandler(self):
    # a misnomer.  will handle _env other than verbalator ... later
    global env
    if not env:
      env = Environment(loader=PackageLoader("verbalator"),
                        autoescape=select_autoescape())
    template = env.get_template("index.html")  # TODO: multiple pages
    html = template.render(prompts=verbalator.common.PROMPTS,
        samples=verbalator.samples.ALL_SAMPLES)
    response = bytes(html, "utf-8")
    self.send_response(200)
    self.send_header("Content-type", "text/html; charset=utf-8")
    self.send_header("Content-length", len(response))
    self.end_headers()
    self.wfile.write(response)



def run(server_class=http.server.HTTPServer, handler_class=InboundRequest):
  server_address = ('', PORT)
  httpd = server_class(server_address, handler_class)
  httpd.serve_forever()


if __name__ == "__main__":
  run()
