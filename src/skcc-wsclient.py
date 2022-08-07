#!/usr/bin/python3

from websocket import create_connection
import threading
import redis
import time


def main():
    ws = create_connection("wss://sked.skccgroup.com/sked")

    r = redis.Redis(host='localhost', port=6379)
    p = r.pubsub(ignore_subscribe_messages=True)
    p.subscribe('skcc-up')

    def rx_thread():
        while True:
            result = ws.recv()
            print("Received '{}'".format(result))
            r.publish("skcc-down", result)
            # ugly hack: after user joins, delay further messages, so the IRC
            # client can join
            if result.find("add-user") > 0: 
                print("DELAY 2s")
                time.sleep(2)
        ws.close()

    thread = threading.Thread(target=rx_thread)
    thread.daemon = True
    thread.start()

    ws.send('{"ready":1}')

    while True:
        message = p.get_message()
        if message:
            ws.send(message['data'])
        time.sleep(1)



if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)
