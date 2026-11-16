"""Launch Sley's offline local weaving adapter."""
import argparse
import webbrowser
import sys

from .server import make_server


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "compare":
        from .compare import main as compare
        return compare(sys.argv[2:])
    parser = argparse.ArgumentParser(description="Open Sley's local weaving adapter", epilog="For change-aware planning and WIF export, run: python -m sley compare --help")
    parser.add_argument("--port", type=int, default=0, help="localhost port; zero chooses a free port")
    parser.add_argument("--no-browser", action="store_true", help="print the URL without opening a browser")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be from 0 through 65535")
    try:
        server = make_server(args.port)
    except OSError as error:
        parser.exit(2, f"sley: cannot open localhost server: {error}\n")
    print(f"Sley: {server.expected_origin}/\nPress Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(server.expected_origin + "/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.calculator.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
