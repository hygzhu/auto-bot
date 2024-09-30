#!/bin/sh

SLEEP_DURATION=5

./stop.sh $1

sleep "$SLEEP_DURATION"

./start.sh $1