#!/bin/bash

echo "Starting bots..."

python3.10 claude.py &
PID1=$!

python3.10 gemini.py &
PID2=$!

python3.10 grok.py &
PID3=$!

python3.10 chatgpt.py &
PID4=$!

python3.10 mimo.py &
PID5=$!

python3.10 nemo.py &
PID6=$!

python3.10 glm.py &
PID7=$!

python3.10 kimi.py &
PID8=$!

trap "echo 'Stopping all bots.'; kill $PID1 $PID2 $PID3 $PID4 $PID5 $PID6 $PID7 $PID8 2>/dev/null; exit" SIGINT

echo "All bots launched. Press Ctrl+C to stop."

wait
