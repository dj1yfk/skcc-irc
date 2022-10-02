#!/usr/bin/python3

import threading
import redis
import socket
import time
import json
import select
import re
import os
import logging
from datetime import datetime
from websocket import create_connection


def main_ws():
    logging.info("Starting main_ws thread\n")
    ws = create_connection("wss://sked.skccgroup.com/sked")

    r = redis.Redis(host='localhost', port=6379)
    p = r.pubsub(ignore_subscribe_messages=True)
    p.subscribe('skcc-up')

    def rx_thread():
        while True:
            result = ws.recv()
            logging.debug("Received '{}'".format(result))
            r.publish("skcc-down", result)
            # ugly hack: after user joins, delay further messages, so the IRC
            # client can join
            if result.find("add-user") > 0: 
                logging.debug("Add user - delaying 2 seconds.")
                time.sleep(2)
        ws.close()

    thread = threading.Thread(target=rx_thread)
    thread.daemon = True
    thread.start()

    while True:
        message = p.get_message()
        if message:
            ws.send(message['data'])
        time.sleep(1)


# IRC class that spawns new irc clients for each visitor of the chat
def main_irc():
    users = dict()
    mycall = "dj5cw"        # nick on Chat
    mypw   = "skcc"         # password 

    with open(os.environ['HOME'] + "/.config/skcc-irc/config.json") as f:
        s = f.read()
    cfg = json.loads(s)

    if "mycall" in cfg:
        mycall = cfg['mycall']
    if "mypw" in cfg:
        mypw = cfg['mypw']

    logging.info("main_irc thread starting. mycall = {}\n".format(mycall))

    r = redis.Redis(host='localhost', port=6379)
    p = r.pubsub(ignore_subscribe_messages=True)
    p.subscribe('skcc-down')

    # individual IRC client that belongs to "call"
    def irc_client(call, status, info):
        messages = dict()
        r = redis.Redis(host='localhost', port=6379)
        p = r.pubsub(ignore_subscribe_messages=True)
        p.subscribe('skcc-down')
        logging.info("I am IRC client for {}, starting to listen for Redis messages.\n".format(call))

        # IRC does not allow nick names starting with a number, so prefix it
        # with _. Do the same for the user's *own* call.
        if call[0].isnumeric() or call.lower() == mycall.lower():
            nick = "_" + call
        else:
            nick = call

        logging.info("I am the IRC client for {} (nickname {}), starting to listen for Redis messages.\n".format(call, nick))

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("localhost", 6655))
        client.send(bytes('NICK ' + nick + '\r\n', encoding='utf8'))
        client.send(bytes('USER ' + call + ' 0 * :' + info + '\r\n', encoding='utf8'))
        client.send(bytes('JOIN #skcc\r\n',encoding='utf8'))
        if status != "":
            client.send(bytes('PRIVMSG #skcc :\x01ACTION ' + status + '\x01\r\n', encoding='utf8'))

        if call == "skcc":
            client.send(bytes('TOPIC #skcc :SKCC Sked Page <-> IRC bridge\r\n', encoding='utf8'));

        client.setblocking(0)
        while True:
            # read redis msg coming from chat server
            message = p.get_message()
            if message:
                obj = json.loads(message['data'])
                logging.debug(call + ":" + repr(obj))
                if 'remove-user' in obj and obj['remove-user'] == call:
                    logging.info(call + ": remove-user")
                    del users[call]
                    return

                # {"msgs":[false,0,[[2142129,1659775906,"VK4HQ",null,"VK2DVA - Hi Colin"]]]}
                # {"msgs":[false,0,[[2142163,1659787973,"JR2IUB",null,"MNI TNX TO ALL.  Lots of JA stations are QRV on skcc area on 20m.  Have a great day. 73,  Take"]]]}
                if 'msgs' in obj:
                    # single message: Print in channel if it matches our
                    # callsign of this IRC client instance
                    if len(obj['msgs'][2]) == 1:
                        if obj['msgs'][2][0][2] == call:
                            client.send(bytes('PRIVMSG #skcc :' + obj['msgs'][2][0][4] + '\r\n', encoding='utf8'))
                            # save message under its ID (in case it will be edited or deleted later)
                            messages[obj['msgs'][2][0][0]] = obj['msgs'][2][0][4]
                        # the person who speaks is not in the channel (should
                        # not happen, but occasionally does!), so let 'skcc'
                        # user say it
                        elif (obj['msgs'][2][0][2] not in users) and (call == 'skcc'):
                            client.send(bytes('PRIVMSG #skcc :' + obj['msgs'][2][0][2] + ': ' + obj['msgs'][2][0][4] + '\r\n', encoding='utf8'))
                    # multiple messages (happens when you join): Print last 10 in all channel as "skcc" user in correct order
                    elif call == 'skcc':
                        for i in reversed(range(0, 10)):
                            dt = datetime.utcfromtimestamp(int(obj['msgs'][2][i][1]))
                            ts = dt.strftime("%H:%M:%S")
                            client.send(bytes('PRIVMSG #skcc :' + ts + " " + obj['msgs'][2][i][2] + ': ' + obj['msgs'][2][i][4] + '\r\n', encoding='utf8'))
                if 'status' in obj and obj['status'][0] == call and obj['status'][1] != "":
                    client.send(bytes('PRIVMSG #skcc :\x01ACTION ' + obj['status'][1] + '\x01\r\n', encoding='utf8'))
                if 'logged-in' in obj and call == "skcc":
                    client.send(bytes('PRIVMSG #skcc :Logged in: ' + str(obj['logged-in']) + '\r\n', encoding='utf8'))
                if 'memberlookup-info' in obj and call == "skcc":
                    client.send(bytes('PRIVMSG #skcc :Lookup: ' + str(obj['memberlookup-info']) + '\r\n', encoding='utf8'))
                # {'update': [2152078, 'new message']}
                if 'update' in obj and obj['update'][0] in messages:
                    client.send(bytes('PRIVMSG #skcc :<update> ' + messages[obj[0]] + '\r\n', encoding='utf8'))


            time.sleep(1)

            # read messages from IRC server
            ready = select.select([client], [], [], 0.1)
            if ready[0]:
                data = client.recv(2048).decode('utf8')
                lines = data.split('\r\n')
                for line in lines:
                    logging.debug("RX from IRC server (client {}): {}".format(call, line))
                    # reply to a PING message sent from the server
                    if line[0:4] == "PING":
                        client.send(bytes("PONG " + line.split()[1] + "\r\n", encoding='utf8'))
                        logging.debug(call + ': PONG')
                    # If we receive a direct message, forward it appropriately
                    # NQ8T:b':so5cw!fabian@127.0.0.1 PRIVMSG nq8t :test'
                    if line.find("PRIVMSG " + nick.lower() + " :") != -1:
                        rxmsg = line.split("PRIVMSG " + nick.lower() + " :")[1]
                        logging.debug(call + " received direct message :" + rxmsg)
                    # If we send something to the channel, forward it, but only
                    # if we're "skcc". Messages starting with ! will be handled
                    # as commands (e.g. to change the status, log in, etc.
                    # :DJ5CW!DJ5CW@127.0.0.1 PRIVMSG #skcc :buongiorno Raz
                    # {"msg":["DJ5CW","buongiorno Raz"]}
                    m = re.match(":" + mycall + "!.* PRIVMSG #skcc :(.*)", line, re.IGNORECASE)
                    if m and call == "skcc":
                        txmsg = m.groups(0)[0]
                        if txmsg[0] == "!":     # text command

                            if ' ' in txmsg:
                                cmd, param = txmsg.split(" ", 1)
                            else:
                                cmd = txmsg
                                param = ""

                            if cmd == "!login":
                                # tx: # {"login":{"callsign":"DJ5CW","password":"..."}}
                                # rx: {"logged-in":["DJ5CW","3873-881923",true,false,"Coffee & CW - 10123.4 kHz","Fabian","1982T","Munich","GER","Fed. Rep. of Germany",true]}
                                # tx: {"ready":1}
                                # tx: {"get-verified-status":1}  # needed??
                                r.publish('skcc-up', '{"login":{"callsign": "'+ mycall +'","password":"' + param + '"}}')
                            elif cmd == "!lookup":
                                r.publish('skcc-up', '{"memberlookup":"' + param +'"}')
                            elif cmd == "!logout":
                                r.publish('skcc-up', '{"logout":1}')
                            elif cmd == "!status":
                                r.publish('skcc-up', '{"status":"' + param + '"}')
                            elif cmd == "!ready":
                                r.publish('skcc-up', '{"ready": 1}')
                            elif cmd == "!back":
                                r.publish('skcc-up', '{"back": 1}')
                            elif cmd == "!away":
                                r.publish('skcc-up', '{"away": 1}')
                            elif cmd == "!active":
                                r.publish('skcc-up', '{"active": 1}')
                            else:
                                logging.warning("{}: Unknown command: {}".format(call, txmsg))

                            # for good measure, indicate that we're still active
                            r.publish('skcc-up', '{"active": 1}')
                        
                        else:   # normal message
                            r.publish('skcc-up', '{"msg":["DJ5CW","' + txmsg + '"]}')
                            r.publish('skcc-up', '{"active": 1}')

    # launch "skcc" user client who will do stuff such as setting the channel topic
    # and receive messages sent in the channel that will be forwarded to the
    # websocket
    skccu = threading.Thread(target=irc_client, args=('skcc', '', 'SKCC bot', ))
    skccu.daemon = True
    skccu.start()

    # log in
    r.publish('skcc-up', '{"login":{"callsign": "'+ mycall.upper() +'","password":"' + mypw + '"}}')

    time.sleep(0.5)

    # send indication to chat server that we are ready - this will return the
    # message history and the current users
    r.publish('skcc-up', '{"ready": 1}')

    # tell the server we don't want to get PMs (not implemented yet in this
    # IRC bridge)
    r.publish('skcc-up', '{"allow-pms":false}')

    # Main loop of IRC client. We wait for messages and launch new IRC
    # clients if someone joins.
    while True:
        time.sleep(0.5)
        message = p.get_message()
        if message:
#            logging.debug("Users online now: {}".format(repr(users)))
            obj = json.loads(message['data'])

            if 'add-users' in obj:
                # check if these users already have a client
                au = obj['add-users']
                for u in au:
                    # each user is an array like this:
                    # ["YL3JD","14.049",1,"Hanz","21931T","Ikskile","LAT","Latvia",true]
                    call = u[0]
                    status = u[1]
                    info = u[3]+" "+u[4]+" "+u[5]+" "+u[6]
                    if call in users:
                        logging.warning("User {} already exists.\n".format(call))
                        del users[call]
                    logging.info("Creating new user {}.\n".format(call))
                    users[call] = threading.Thread(target=irc_client, args=(call, status, info, ))
                    users[call].daemon = True
                    users[call].start()
            if 'add-user' in obj:
                # check if these users already have a client
                u = obj['add-user']
                call = u[0]
                status = u[1]
                info = u[3]+" "+u[4]+" "+u[5]+" "+u[6]
                if call in users:
                    logging.warning("User {} already exists.\n".format(call))
                    del users[call]

                logging.info("Creating new user {}.\n".format(call))
                users[call] = threading.Thread(target=irc_client, args=(call, status, info, ))
                users[call].daemon = True
                users[call].start()


if __name__ == "__main__":
    try:
        logging.basicConfig(encoding='utf-8', level=logging.DEBUG)

        # start websocket main thread
        wst = threading.Thread(target=main_ws)
        wst.daemon = True
        wst.start()

        time.sleep(5)

        # start IRC main thread
        irt = threading.Thread(target=main_irc)
        irt.daemon = True
        irt.start()

        while True:
            time.sleep(1000)

    except Exception as e:
        print(e)
