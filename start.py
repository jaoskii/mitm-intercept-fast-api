import subprocess
import sys
import os
import signal
import time

processes = []

def signal_handler(sig, frame):
    print(f"\n[Manager] Received signal {sig}. Terminating child processes...")
    for p in processes:
        if p.poll() is None:
            print(f"[Manager] Terminating process {p.pid}...")
            p.terminate()
            
    # Wait a moment for clean exit
    time.sleep(1)
    
    # Force kill if still running
    for p in processes:
        if p.poll() is None:
            print(f"[Manager] Force killing process {p.pid}...")
            p.kill()
            
    print("[Manager] Cleanup complete. Exiting.")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    print("[Manager] Starting Mitmproxy Interceptor Workspace...")
    
    # 1. Start FastAPI Dashboard App
    fastapi_cmd = [
        "uvicorn", 
        "app.main:app", 
        "--host", "0.0.0.0", 
        "--port", "8000",
        "--log-level", "info"
    ]
    print(f"[Manager] Launching FastAPI Dashboard: {' '.join(fastapi_cmd)}")
    try:
        fastapi_proc = subprocess.Popen(
            fastapi_cmd, 
            stdout=sys.stdout, 
            stderr=sys.stderr
        )
        processes.append(fastapi_proc)
    except Exception as e:
        print(f"[Manager] Error launching FastAPI: {e}")
        sys.exit(1)

    # Give FastAPI a moment to start up and initialize the database
    time.sleep(2)

    # 2. Start Mitmproxy (mitmdump)
    # We load our addon script in proxy/addon.py
    mitm_cmd = [
        "mitmdump",
        "-s", "proxy/addon.py",
        "--listen-host", "0.0.0.0",
        "--listen-port", "8080"
    ]
    print(f"[Manager] Launching Mitmproxy Dump: {' '.join(mitm_cmd)}")
    try:
        mitm_proc = subprocess.Popen(
            mitm_cmd,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        processes.append(mitm_proc)
    except Exception as e:
        print(f"[Manager] Error launching Mitmproxy: {e}")
        fastapi_proc.terminate()
        sys.exit(1)

    print("[Manager] Services running. FastAPI at port 8000, Mitmproxy at port 8080.")

    # 3. Supervise processes
    while True:
        time.sleep(1)
        
        # Check if any process terminated
        for p in processes:
            ret_code = p.poll()
            if ret_code is not None:
                print(f"[Manager] Child process {p.pid} exited with code {ret_code}. Shutting down manager...")
                signal_handler(signal.SIGTERM, None)

if __name__ == "__main__":
    main()
