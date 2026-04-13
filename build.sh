#!/bin/bash
# Build script for Render deployment
set -e

echo "=== Building frontend ==="
cd frontend
npm install
npm run build
cd ..

echo "=== Installing backend dependencies ==="
pip install -r backend/requirements.txt

echo "=== Build complete ==="
