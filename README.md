# Mitmproxy Interceptor with FastAPI Dashboard

A containerized traffic interception setup combining the power of **mitmproxy** (`mitmdump`) with an interactive, real-time **FastAPI** dashboard. It allows you to dynamically configure and toggle interception rules, rewrite requests/responses, mock APIs, inject delays, and monitor live traffic flows.

## Features

- **Dynamic Interception Actions**:
  - **Mock Response**: Immediately return custom status codes, headers, and body content without hitting the upstream server.
  - **Modify Request Headers**: Add or override headers sent to the destination server.
  - **Modify Response Headers**: Add or override headers returned to the client.
  - **Rewrite Response Body**: Perform string search-and-replace transformations on the fly.
  - **Network Latency Simulation**: Pause requests for a specified number of seconds to test timeout behaviors.
- **WebSocket Logs Stream**: View real-time traffic feed in a sleek dashboard, highlighting which requests were intercepted by which rules.
- **Persistent Storage**: Interception rules and generated CA certificates are kept inside Docker volumes.
- **Certificate Access**: Direct UI links to download the mitmproxy CA certificate for HTTPS interception.

---

## Getting Started

### Prerequisites

- [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/) installed on your machine.

### Running with Docker Compose

To build and launch the container with persistent volumes, simply run:

```bash
docker-compose up --build
```

This starts:
- **FastAPI Dashboard UI**: `http://localhost:8000`
- **Mitmproxy Listener**: `http://localhost:8080` (proxy port)

> [!NOTE]
> Rules and CA certificates are stored in persistent Docker volumes (`proxy-data` and `proxy-certs`). This ensures that your configured interception rules are saved and the generated mitmproxy CA certificate remains identical across container rebuilds or restarts (so you do not have to reinstall or trust a new certificate on your client devices every time).


### Running with Docker CLI (Fallback)

If you prefer to run it using the standard Docker command line, execute:

```bash
# Build the image
docker build -t mitmproxy-fastapi .

# Run the container mapping ports 8000 and 8080
docker run -d --name mitmproxy-interceptor -p 8000:8000 -p 8080:8080 mitmproxy-fastapi
```

---

## Intercepting and Configuring Rules

### Step 1: Trust the CA Certificate (Required for HTTPS)

To intercept HTTPS traffic:
1. Open the dashboard at `http://localhost:8000`.
2. Click **Download CA Cert** in the upper right.
3. Trust the downloaded `mitmproxy-ca-cert.pem` on your machine/browser/device.
   - *For MacOS*: Double click the file to open Keychain Access, locate `mitmproxy`, double-click it, expand **Trust**, and change "When using this certificate" to **Always Trust**.
   - *For mobile simulators or browsers*: Consult standard mitmproxy guides or follow the certificate installation settings on your client.

### Step 2: Configure Rule in Dashboard

1. Navigate to the dashboard at `http://localhost:8000`.
2. Click **Add Intercept Rule**.
3. Configure the match conditions:
   - **Method**: E.g., `GET`, `POST`, or `ALL`.
   - **URL Pattern**: A substring that must match the request URL (e.g., `api/users` or `httpbin.org`).
4. Select an action (e.g., **Mock Response** with a status of `503` and body `{"error": "Service Outage"}`).
5. Click **Save Rule**. Make sure it is toggled **Active**.

### Step 3: Direct Client Traffic

Configure your HTTP client (or terminal curl, browser, system settings) to route traffic through the proxy at `http://localhost:8080`.

#### Test with Curl

Run curl requests specifying the proxy address:

```bash
# Bypass Rule (will display standard response and log to dashboard)
curl -x http://localhost:8080 http://httpbin.org/get

# Match Mock Rule (returns mocked status/body instantly and logs to dashboard)
curl -x http://localhost:8080 http://httpbin.org/api/users
```

---

## Project Structure

- `app/main.py`: FastAPI server containing database connections, HTTP logs receivers, WebSockets manager, and file routes.
- `app/db.py`: Database helper using standard SQLite to handle CRUD operations on rules and historical logs.
- `app/templates/index.html`: Responsive administration dashboard.
- `app/static/`: Stylesheet and javascript logic controlling rule toggles and live websocket records rendering.
- `proxy/addon.py`: The python intercept script loaded by `mitmdump` to process, rewrite, and report flows.
- `start.py`: System process manager executing both FastAPI and mitmdump processes concurrently.
