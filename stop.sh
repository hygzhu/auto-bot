#!/bin/sh

echo "Trying to stop"

pkill -9 -f autobot

echo "Killed, ps output"

ps -ef | grep python3.12

for f in output.log*; do mv "$f" "$(echo "$f" | sed s/output/old_output/)"; done