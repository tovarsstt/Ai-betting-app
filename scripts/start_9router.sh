#!/bin/bash
# Start 9Router LLM proxy with RTK compression
PORT=20128

# Kill anything already on the port
existing=$(lsof -ti:$PORT 2>/dev/null)
if [ -n "$existing" ]; then
  echo "Killing stale process on port $PORT (PID: $existing)"
  kill $existing
  sleep 1
fi

cd ~/.claude/9router
PORT=$PORT NEXT_PUBLIC_BASE_URL=http://localhost:$PORT npm run dev &
echo "9Router started at http://localhost:$PORT (PID: $!)"
echo "Point Claude Code at http://localhost:$PORT to enable multi-provider routing + RTK compression"
