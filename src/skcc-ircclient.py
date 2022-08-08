#!/usr/bin/python3

import threading
import redis
import socket
import time
import json
import select
import re



def main():
    users = dict()
    mynick = "so5cw"        # nickname on IRC that will be forwarded to SKCC chat
    mycall = "DJ5CW"        # nick on Chat

    r = redis.Redis(host='localhost', port=6379)
    p = r.pubsub(ignore_subscribe_messages=True)
    p.subscribe('skcc-down')

    def irc_client(call, status, info):
        r = redis.Redis(host='localhost', port=6379)
        p = r.pubsub(ignore_subscribe_messages=True)
        p.subscribe('skcc-down')
        print("I am IRC client for {}, starting to listen for Redis messages.\n".format(call))

        # IRC does not allow nick names starting with a number, so prefix it
        # with _
        if call[0].isnumeric():
            call = "_" + call

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("localhost", 6655))
        client.send(bytes('NICK ' + call + '\r\n', encoding='utf8'))
        client.send(bytes('USER ' + call + ' 0 * :' + info + '\r\n', encoding='utf8'))
        client.send(bytes('JOIN #skcc\r\n',encoding='utf8'))
        if status != "":
            client.send(bytes('PRIVMSG #skcc :\x01ACTION ' + status + '\x01\r\n', encoding='utf8'))
        client.setblocking(0)
        while True:
            # read redis msg
            message = p.get_message()
            if message:
                obj = json.loads(message['data'])
                print(call + ":" + repr(obj))
                if 'remove-user' in obj and obj['remove-user'] == call:
                    print("I must die now")
                    return

                # {"msgs":[false,0,[[2142129,1659775906,"VK4HQ",null,"VK2DVA - Hi Colin"]]]}
                # {"msgs":[false,0,[[2142163,1659787973,"JR2IUB",null,"MNI TNX TO ALL.  Lots of JA stations are QRV on skcc area on 20m.  Have a great day. 73,  Take"]]]}
                if 'msgs' in obj:
                    for i in range(0, len(obj['msgs'][2])):
                        if obj['msgs'][2][i][2] == call:
                            client.send(bytes('PRIVMSG #skcc :' + obj['msgs'][2][i][4] + '\r\n', encoding='utf8'))
                if 'status' in obj and obj['status'][0] == call and obj['status'][1] != "":
                    client.send(bytes('PRIVMSG #skcc :\x01ACTION ' + obj['status'][1] + '\x01\r\n', encoding='utf8'))
                if 'logged-in' in obj and call == "skcc":
                    client.send(bytes('PRIVMSG #skcc :Logged in: ' + str(obj['logged-in']) + '\r\n', encoding='utf8'))
                if 'memberlookup-info' in obj and call == "skcc":
                    client.send(bytes('PRIVMSG #skcc :Lookup: ' + str(obj['memberlookup-info']) + '\r\n', encoding='utf8'))

            time.sleep(0.2)

            # read from IRC server
            ready = select.select([client], [], [], 0.1)
            if ready[0]:
                data = client.recv(2048).decode('utf8')
                lines = data.split('\r\n')
                for line in lines:
                    print(call + ':' +line)
                    # reply to a PING message sent from the server
                    if line[0:4] == "PING":
                        client.send(bytes("PONG " + line.split()[1] + "\r\n", encoding='utf8'))
                        print(call + 'PONG !!!')
                    # If we receive a direct message, forward it appropriately
                    # NQ8T:b':so5cw!fabian@127.0.0.1 PRIVMSG nq8t :test'
                    if line.find("PRIVMSG " + call.lower() + " :") != -1:
                        rxmsg = line.split("PRIVMSG " + call.lower() + " :")[1]
                        print(call + " received direct message :" + rxmsg)
                    # If we send something to the channel, forward it, but only
                    # if we're "skcc". Messages starting with ! will be handled
                    # as commands (e.g. to change the status, log in, etc.
                    # :DJ5CW!DJ5CW@127.0.0.1 PRIVMSG #skcc :buongiorno Raz
                    # {"msg":["DJ5CW","buongiorno Raz"]}
                    m = re.match(":" + mynick + "!.* PRIVMSG #skcc :(.*)", line)
                    if m and call == "skcc":
                        txmsg = m.groups(0)[0]
                        if txmsg[0] == "!":     # text command
                            cmd, param = txmsg.split(" ", 1)
                            if cmd == "!status":
                                pass
                            elif cmd == "!login":
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
                            else:
                                print("Unknown command")
                        
                        else:   # normal message
                            r.publish('skcc-up', '{"msg":["DJ5CW","' + txmsg + '"]}')

    # launch "skcc" user client who will do stuff such as setting the channel topic
    # and receive messages sent in the channel that will be forwarded to the
    # websocket
    skccu = threading.Thread(target=irc_client, args=('skcc', '', 'SKCC bot', ))
    skccu.daemon = True
    skccu.start()

    while True:
        time.sleep(0.5)
        message = p.get_message()
        if message:
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
                        print("User {} already exists.\n".format(call))
                        del users[call]
                    print("Creating new user {}.\n".format(call))
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
                    print("User {} already exists.\n".format(call))
                    del users[call]

                print("Creating new user {}.\n".format(call))
                users[call] = threading.Thread(target=irc_client, args=(call, status, info, ))
                users[call].daemon = True
                users[call].start()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)
