#!/usr/bin/env python3
"""
Start Inspector Gadget web server.

Usage:
    python3 start_inspector.py          # Start on port 7771
    python3 start_inspector.py --port 8080  # Custom port

The server will be accessible at:
    Local:  http://localhost:7771
    Public: https://miamibadvice.com (via Cloudflare tunnel)
"""

import argparse
import sys
from pathlib import Path

# Ensure inspector package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(description="Inspector Gadget — Web Server")
    parser.add_argument("--port", type=int, default=7771, help="Port (default: 7771)")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    args = parser.parse_args()

    print(f"🔍 Inspector Gadget starting on http://{args.host}:{args.port}")
    print(f"   Public URL: https://miamibadvice.com")
    print(f"   Press Ctrl+C to stop\n")

    import uvicorn
    from inspector.api import app
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
