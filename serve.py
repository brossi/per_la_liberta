"""Local development server for the bilingual edition."""

import functools
import http.server
import os
from pathlib import Path


def main():
    docs_dir = Path(__file__).parent / "docs"
    port = int(os.environ.get("PORT", 8000))

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(docs_dir))
    server = http.server.HTTPServer(("", port), handler)

    print(f"Serving docs/ at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
