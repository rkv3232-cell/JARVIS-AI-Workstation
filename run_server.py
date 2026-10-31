import sys
import socket
import uvicorn

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from backend.main import app

def run():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 8000))
    sock.setblocking(False)
    sock.listen(100)
    print("[JARVIS-APEX] Server listening with non-blocking SO_REUSEADDR on port 8000")
    config = uvicorn.Config(app, log_level="info")
    server = uvicorn.Server(config)
    server.run(sockets=[sock])

if __name__ == "__main__":
    run()
