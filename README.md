# SKCC Sked Page IRC bridge

This is a small collection of scripts to use the [SKCC Sked page](https://sked.skccgroup.com/) 
with any IRC client.

The SKCC Sked Page is a web based application that allows members of the [Straight Key Century
Club](https://www.skccgroup.com/) to coordinate on-air contacts. Since I always
have an IRC client running anyway (which allows easy access from both PCs and
mobiles), I decided to write a small bridge which translates the messages from
the Sked Page into IRC and vice versa.

# Architecture

 It contains two parts:

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
