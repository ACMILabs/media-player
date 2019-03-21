import os
from kombu import Connection, Exchange, Queue


AMQP_URL = os.getenv('AMQP_URL')
MEDIA_PLAYER_ID = os.getenv('MEDIA_PLAYER_ID')
queue_name = f'playback_{MEDIA_PLAYER_ID}'

media_player_exchange = Exchange('media_player', 'direct', durable=True)
playback_queue = Queue(queue_name, exchange=media_player_exchange, routing_key=queue_name)


def process_media(body, message):
    print(body)
    message.ack()

# connections
with Connection(AMQP_URL) as conn:

    # consume
    with conn.Consumer(playback_queue, callbacks=[process_media]) as consumer:
        # Process messages and handle events on all channels
        while True:
            conn.drain_events()
