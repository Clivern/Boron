## Boron

Minimalist Docker Sandbox for Spawning Instant, Disposable Agent Workspaces.

### Build

```bash
docker build -t clivern/boron:v0.1.0 .
```

### Run

Mount a git repository at `/repo`, publish port `8765`, and set the required environment variables:

```bash
docker run -d --name boron \
  -p 8765:8765 \
  -v /path/to/your/repo:/repo \
  -e RUN_ID=your-run-id \
  -e PROXY_URL=http://host.docker.internal:8080/api \
  -e PI_MODEL=openrouter/anthropic/claude-sonnet-4.5 \
  -e RPC_API_KEY=your-secret \
  boron
```

`PROXY_URL` should point at an OpenRouter-compatible proxy. Run [Ting](https://github.com/Clivern/Ting) on the host for that — it sits in front of OpenRouter and injects the API key:

```bash
export ZIEE_MGMT_URL=https://ziee.io
export OPENROUTER_API_KEY=sk-or-v1-...
go run ting.go server -c config.dist.yml
```


### Client

`client.py` authenticates with the bridge, then speaks Pi’s JSONL RPC protocol. It streams assistant text and waits for `agent_settled`.

```bash
# one-shot
RPC_API_KEY=your-secret python3 client.py "Explain this repository"

# explicit host/port/key
python3 client.py \
  --host 127.0.0.1 \
  --port 8765 \
  --api-key your-secret \
  "Fix the failing test"

# interactive REPL
RPC_API_KEY=your-secret python3 client.py

# verbose events (tools, responses, etc.)
RPC_API_KEY=your-secret python3 client.py -v "Summarize recent commits"
```
