#!/usr/bin/python3

import threading
import redis
import socket
import time
import json
import select

def main():
    users = dict()

    r = redis.Redis(host='localhost', port=6379)
    p = r.pubsub(ignore_subscribe_messages=True)
    p.subscribe('skcc-down')


    def irc_client(call, status):
        r = redis.Redis(host='localhost', port=6379)
        p = r.pubsub(ignore_subscribe_messages=True)
        p.subscribe('skcc-down')
        print("I am IRC client for {}, starting to listen for Redis messages.\n".format(call))

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("localhost", 6655))
        client.send(bytes('NICK ' + call + '\r\n', encoding='utf8'))
        client.send(bytes('USER ' + call + ' 0 * :' + 'SKCC nerd' + '\r\n', encoding='utf8'))
        client.send(bytes('JOIN #skcc\r\n',encoding='utf8'))
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

                if 'status' in obj and obj['status'][0] == call:
                    client.send(bytes('PRIVMSG #skcc :\x01ACTION ' + obj['status'][1] + '\x01\r\n', encoding='utf8'))

            time.sleep(0.2)
            # read from IRC server. only handle pings
            ready = select.select([client], [], [], 0.1)
            if ready[0]:
                data = client.recv(2048).decode('utf8')
                lines = data.split('\r\n')
                for line in lines:
                    print(call + ':' +line)
                    if line[0:4] == "PING":
                        client.send(bytes("PONG " + line.split()[1] + "\r\n", encoding='utf8'))
                        print(call + 'PONG !!!')
                    # NQ8T:b':so5cw!fabian@127.0.0.1 PRIVMSG nq8t :test'
                    if line.find("PRIVMSG " + call.lower() + " :") != -1:
                        rxmsg = line.split("PRIVMSG " + call.lower() + " :")[1]
                        print(call + " received direct message :" + rxmsg)


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
                    if call in users:
                        print("User {} already exists.\n".format(call))
                        del users[call]
                    print("Creating new user {}.\n".format(call))
                    users[call] = threading.Thread(target=irc_client, args=(call, status, ))
                    users[call].daemon = True
                    users[call].start()
            if 'add-user' in obj:
                # check if these users already have a client
                u = obj['add-user']
                call = u[0]
                status = u[1]
                if call in users:
                    print("User {} already exists.\n".format(call))
                    del users[call]

                print("Creating new user {}.\n".format(call))
                users[call] = threading.Thread(target=irc_client, args=(call, status, ))
                users[call].daemon = True
                users[call].start()



#    def rx_thread():
#        while True:
#            result = ws.recv()
#            print("Received '{}'".format(result))
#            r.publish("skcc-down", result)
#        ws.close()
#
#    thread = threading.Thread(target=rx_thread)
#   thread.daemon = True
#    thread.start()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)
