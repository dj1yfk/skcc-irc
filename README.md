# SKCC Sked Page IRC bridge

This is a small collection of scripts to use the [SKCC Sked page](https://sked.skccgroup.com/) 
with any IRC client. It contains two parts:

* `skcc-wsclient.py`: Websocket client that connects to the SKCC chat server
  and translates the messages to a local Redis pub/sub server.

* `skcc-ircclient.py`: Subscribes to the messages on Redis and launches a 
  IRC connection to a local server for every user on the Sked page. Messages
  from the IRC channel are received and sent back to the Websocket via Redis.

## Usage

TODO

## Requirements

* Python 3

* A Redis and and a IRC server
