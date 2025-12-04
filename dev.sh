#!/bin/bash

#backend
echo "starting backend"
source venv/bin/activate

cd backend || exit

uvicorn main:app --reload &
BACKEND_PID=$!

#frontend

echo "starting frontend"
cd ../frontend/openkaraoke || exit
npm run dev &
FRONTEND_PID=$!

trap "echo Stopping...; kill $BACKEND_PID $FRONTEND_PID" EXIT

wait