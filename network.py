"""
Based on: https://github.com/oaubert/python-vlc/tree/master/examples/video_sync
"""

import os
import platform
import socket
import threading
import sys
import logging
from concurrent import futures
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logger.setLevel(logging.DEBUG)

# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)


class Server:
    """Data sender server"""

    def __init__(self, host, port, media_player):

        self.media_player = media_player
        # Create a TCP/IP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Bind the socket to the port
        logger.info("Server started on %s port %s", host, port)
        self.sock.bind((host, port))


        # Listen for incoming connections
        self.sock.listen(5)

        self.clients = set()
        listener_thread = threading.Thread(target=self.listen_for_clients, args=())
        listener_thread.daemon = True
        listener_thread.start()

    def listen_for_clients(self):
        logger.info("Now listening for clients")
        t = threading.Thread(target=self.data_sender, args=())
        t.daemon = True
        t.start()

        while True:
            client, _ = self.sock.accept()
            logger.info("Accepted Connection from: %s", client)
            self.clients.add(client)

    def data_sender(self):
        while True:
            data = '{},'.format(self.media_player.vlc_player.get_time())

            with futures.ThreadPoolExecutor(max_workers=5) as ex:
                for client in self.clients:
                    ex.submit(self.sendall, client, data.encode())
            time.sleep(0.01)

    def sendall(self, client, data):
        """Wraps socket module's `sendall` function"""
        try:
            client.sendall(data)
        except socket.error:
            logger.exception("Connection to client: %s was broken!", client)
            client.close()
            self.clients.remove(client)


class Client:
    """Data receiver client"""

    def __init__(self, address, port, media_player):
        self.media_player = media_player

        # Create a TCP/IP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Connect the socket to the port where the server is listening
        logger.info("Connecting to %s port %s", address, port)
        self.sock.connect((address, port))

        thread = threading.Thread(target=self.data_receiver, args=())
        thread.daemon = True
        thread.start()

    def data_receiver(self):
        """Handles receiving, parsing, and queueing data"""
        logger.info("New data receiver thread started.")

        try:
            while True:
                data = self.sock.recv(4096)
                if data:
                    data = data.decode()
                    pos = data.split(',')[-2]
                    self.media_player.server_time = int(pos)

        except:
            logger.exception("Closing socket: %s", self.sock)
            self.sock.close()
            return
