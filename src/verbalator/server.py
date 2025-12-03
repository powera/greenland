#!/usr/bin/python3
"""HTTP server for handling LLM generation requests."""

import http.server
import json
import os
import sys

from dataclasses import asdict
from typing import Dict, Tuple, Any, Optional
from jinja2 import Environment, PackageLoader, select_autoescape

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients import anthropic_client, openai_client, ollama_client
import constants
import util.flesch_kincaid as fk
import verbalator.common
import verbalator.prompt_builder
import verbalator.samples

PORT = 9871


class GenerationHandler:
    """Handles text generation requests using different LLM clients."""

    @staticmethod
    def generate_text(
        prompt: str, entry: Optional[str], model: str = "phi3:3.8b"
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate text using specified model and track usage.

        Args:
            prompt: The generation prompt
            entry: Optional additional context
            model: Model identifier to use

        Returns:
            Tuple of (generated_text, usage_info)
        """
        if model == "gpt4o-mini":
            return openai_client.generate_text(prompt, entry)
        elif model == "claude3-haiku":
            return anthropic_client.generate_text(prompt, entry)
        else:
            # Use Ollama client with combined prompt
            full_prompt = f"{prompt}\n\n{entry}" if entry else prompt
            response, usage = ollama_client.generate_text(full_prompt, model)
            return response, asdict(usage)


class RequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the server."""

    def __init__(self, *args, **kwargs):
        self.jinja_env = None
        super().__init__(*args, **kwargs)

    @property
    def template_env(self) -> Environment:
        """Lazy loading of Jinja environment."""
        if not self.jinja_env:
            self.jinja_env = Environment(
                loader=PackageLoader("verbalator"), autoescape=select_autoescape()
            )
        return self.jinja_env

    def do_GET(self) -> None:
        """Handle GET requests."""
        handlers = {
            "/favicon.ico": self._serve_favicon,
            "/images/": self._serve_static,
            "/css/": self._serve_static,
            "/js/": self._serve_static,
        }

        # Find matching handler based on path prefix
        handler = next(
            (handlers[prefix] for prefix in handlers if self.path.startswith(prefix)),
            self._serve_template,
        )
        handler()

    def do_POST(self) -> None:
        """Handle POST requests."""
        if self.path == "/query":
            self._handle_generation_request()
        else:
            self.send_error(404, "Not Found")

    def _get_normalized_path(self) -> str:
        """Get normalized file path from request path."""
        # Remove query parameters if any
        path = self.path.split("?")[0]
        # Convert URL path to filesystem path
        normalized_path = os.path.normpath(path.lstrip("/"))
        # Ensure the path doesn't try to access parent directories
        if normalized_path.startswith("..") or "/../" in normalized_path:
            raise ValueError("Invalid path")
        return normalized_path

    def _serve_static(self) -> None:
        """Serve static files."""
        normalized_path = self._get_normalized_path()
        path = os.path.join(constants.VERBALATOR_HTML_DIR, normalized_path)
        with open(path, mode="rb") as f:
            response = f.read()

        content_types = {
            "/images/": ("image/png", {"Cache-control": "public, max-age=3600"}),
            "/css/": ("text/css", {}),
            "/js/": ("text/javascript", {}),
            "default": ("text/html; charset=utf-8", {}),
        }

        # Get content type and extra headers based on path prefix
        content_type, extra_headers = next(
            (content_types[prefix] for prefix in content_types if self.path.startswith(prefix)),
            content_types["default"],
        )

        self._send_response(response, content_type, extra_headers)

    def _serve_favicon(self) -> None:
        """Serve favicon.ico."""
        path = os.path.join(constants.VERBALATOR_HTML_DIR, "favicon.ico")
        with open(path, mode="rb") as f:
            response = f.read()
        self._send_response(response, "image/x-icon")

    def _serve_template(self) -> None:
        """Serve template-rendered pages."""
        template = self.template_env.get_template("index.html")
        html = template.render(
            prompts=verbalator.common.PROMPTS, samples=verbalator.samples.ALL_SAMPLES
        )
        self._send_response(bytes(html, "utf-8"), "text/html; charset=utf-8")

    def _handle_generation_request(self) -> None:
        """Handle text generation requests."""
        try:
            # Parse request data
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            # Extract parameters
            prompt = verbalator.prompt_builder.build(data.get("prompt"), data)
            if not prompt:
                raise ValueError("No prompt provided")

            # Generate response
            response, usage = GenerationHandler.generate_text(
                prompt=prompt, entry=data.get("entry"), model=data.get("model", "phi3:3.8b")
            )

            # Calculate reading level
            reading_level = fk.flesch_kincaid_grade(response)

            # Send response
            self._send_json_response(
                {"response": response, "usage": usage, "reading_level": reading_level}
            )

        except (ValueError, KeyError) as e:
            self.send_error(400, str(e))
        except Exception as e:
            self.send_error(500, str(e))

    def _send_response(
        self, content: bytes, content_type: str, extra_headers: Dict[str, str] = None
    ) -> None:
        """Send HTTP response with headers."""
        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.send_header("Content-length", len(content))

        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)

        self.end_headers()
        self.wfile.write(content)

    def _send_json_response(self, data: Dict) -> None:
        """Send JSON response with CORS headers."""
        response = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-length", len(response))
        self.end_headers()
        self.wfile.write(response)


def run(server_class=http.server.HTTPServer, handler_class=RequestHandler) -> None:
    """Run the HTTP server."""
    server_address = ("", PORT)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()


if __name__ == "__main__":
    run()
