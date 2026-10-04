"""python -m src.web  →  http://localhost:8000"""
import argparse
import webbrowser

import uvicorn

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--no-browser", action="store_true")
args = parser.parse_args()
if not args.no_browser:
    webbrowser.open(f"http://localhost:{args.port}")
uvicorn.run("src.web.server:app", host="127.0.0.1", port=args.port)
