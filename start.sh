#!/bin/sh

# Sleep duration in seconds
SLEEP_DURATION=5

echo "Trying to start up"
# ignore any HUP signals we receive (even though we shouldn't get any regardless)
trap '' HUP
. dev_env/bin/activate
echo "Run"
nohup python3.12 autobot_farm.py -c $1.json 2> /dev/null &

while true; do
    # Use the find command to search for files matching the pattern
    if ! find . -type f -iname "output.$1.log*" -print -quit | grep -q .; then
        echo "No files found matching pattern Sleeping for $SLEEP_DURATION seconds..."
        sleep "$SLEEP_DURATION"
    else
        echo "Files found matching pattern"
        output_file=$(find . -type f -iname "output.log*" )
        echo "Tailing"
        tail -f $output_file
        break
    fi
done
