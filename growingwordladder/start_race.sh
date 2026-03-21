#!/bin/bash

echo "🚀 Deploying the bot swarm..."

# Start each bot in the background and save its Process ID (PID)
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

# Catch Ctrl+C to cleanly kill all background bots
trap "echo -e '\n🛑 Halting the race... Killing all bots.'; kill $PID1 $PID2 $PID3 $PID4 $PID5 2>/dev/null; exit" SIGINT

echo "✅ All bots are live and connected! (Press Ctrl+C to stop them)"

# Keep the script running until all background jobs finish
wait