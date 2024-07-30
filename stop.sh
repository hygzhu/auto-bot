#!/bin/sh

echo "Trying to stop"

pkill -9 -f autobot

echo "Killed, ps output"

ps -ef | grep python3.12