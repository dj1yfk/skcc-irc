#!/bin/bash

# Launch SKCC IRC Chat Bridge

screen -d -m -S SKCC /usr/bin/python3 -m miniircd --verbose --listen 127.0.0.1 --ports 6655
# create sub-screen with skcc-irc bridge
screen -r SKCC -X screen src/skcc-irc.py

