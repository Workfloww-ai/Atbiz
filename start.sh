#!/bin/bash
# Script to start both AT BiZ Backend and Frontend together

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "🚀 Starting AT BiZ System"
echo "=========================================="

# 1. Start Backend
echo "1️⃣ Starting Backend (FastAPI on http://127.0.0.1:8000)..."
cd "$PROJECT_ROOT/atbiz-backend"
PYTHONPATH=. "$PROJECT_ROOT/atbiz-backend/venv/bin/uvicorn" main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# 2. Start Frontend
echo "2️⃣ Starting Frontend (Next.js on http://localhost:3000)..."
cd "$PROJECT_ROOT/atbiz-frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Both services are starting up!"
echo "👉 Frontend URL: http://localhost:3000"
echo "👉 Backend API:  http://127.0.0.1:8001"
echo "👉 Press Ctrl+C anytime to stop both."
echo "=========================================="

# Graceful cleanup on Ctrl+C or kill
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    kill "$BACKEND_PID" 2>/dev/null
    kill "$FRONTEND_PID" 2>/dev/null
    wait "$BACKEND_PID" 2>/dev/null
    wait "$FRONTEND_PID" 2>/dev/null
    echo "👋 Shutdown complete."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

wait
