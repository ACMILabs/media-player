import os
from kombu import Connection, Exchange, Queue
from kombu.mixins import ConsumerMixin

AMQP_URL = os.getenv('AMQP_URL')
MEDIA_PLAYER_ID = os.getenv('MEDIA_PLAYER_ID')
queue_name = f'mqtt-subscription-playback_{MEDIA_PLAYER_ID}'
routing_key = f'mediaplayer.{MEDIA_PLAYER_ID}'


class Worker(ConsumerMixin):
    def __init__(self, connection, queues):
        self.connection = connection
        self.queues = queues
    def get_consumers(self, Consumer, channel):
        return [Consumer(queues=self.queues,
                         callbacks=[self.on_message])]
    def on_message(self, body, message):
        print('Got message: {0}'.format(body))
        message.ack()
exchange = Exchange('amq.topic', 'direct')
queues = [Queue(queue_name, exchange, routing_key=routing_key)]
with Connection(AMQP_URL, heartbeat=4) as conn:
        worker = Worker(conn, queues)
        worker.run()
