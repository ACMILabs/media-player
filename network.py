"""
Based on: https://github.com/oaubert/python-vlc/tree/master/examples/video_sync
"""

import logging
import socket
import threading
import time

logger = logging.getLogger(__name__)  # pylint: disable=C0103
ch = logging.StreamHandler()  # pylint: disable=C0103
ch.setLevel(logging.DEBUG)
ch.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(ch)


class Server:
    """
    A server class for synchronisation. Sends the time of the video
    being currently played each second to a set of clients.
    """

    def __init__(self, host, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        logger.info("Server started on %s port %s", host, port)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))

        self.sock.listen(5)

        self.clients = set()
        listener_thread = threading.Thread(target=self.listen_for_clients, args=())
        listener_thread.daemon = True
        listener_thread.start()

    def listen_for_clients(self):
        """
        Constantly listens for incoming clients to set up a connection.
        """
        while True:
            client, _ = self.sock.accept()
            logger.info("Accepted Connection from: %s", client)
            self.clients.add(client)

    def send(self, data):
        """
        Sends the time in milliseconds (int) to the set of registered clients.
        """
        data = '{},'.format(data).encode()

        for client in self.clients:
            try:
                client.send(data)
            except socket.error:
                logger.exception("Connection to client: %s was broken!", client)
                client.close()
                self.clients.remove(client)


class Client:  # pylint: disable=R0903
    """
    A client class for synchronisation. Receives the time of the video
    being currently in the server player.
    """

    def __init__(self, address, port):

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        logger.info("Connecting to %s port %s", address, port)
        connected = False
        while not connected:
            try:
                self.sock.connect((address, port))
                connected = True
            except ConnectionRefusedError:
                logger.info("Waiting for server at %s port %s", address, port)
                time.sleep(1)
            except OSError:
                logger.info("Can't connect to %s port %s... retrying in 1 minute", address, port)
                time.sleep(60)

    def receive(self):
        """
        Receives data and tries to parse it into an integer containing
        the time of the server player in milliseconds.
        """
        try:
            data = self.sock.recv(4096)
            if data:
                data = data.decode()
                pos = data.split(',')[-2]
                return int(pos)
            return None
        except OSError:
            logger.exception("Closing socket: %s", self.sock)
            self.sock.close()
            return None
