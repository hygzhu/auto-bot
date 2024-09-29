#!/bin/sh

echo "Trying to stop"
pkill -9 -f $1 

echo "Killed, ps output"

ps -ef | grep python3.12 

for f in output.$1.log*; do rm "$f"; done