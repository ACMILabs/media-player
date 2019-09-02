import time

from kombu import Connection, Exchange, Queue

media_player_exchange = Exchange('media_player', 'direct', durable=True)
playback_queue = Queue('playback', exchange=media_player_exchange, routing_key='playback')

# connections
with Connection('amqp://media_player:grime-unpin-guidance-regent@172.16.80.105:5672//') as conn:

    # produce
    for i in range(1000):
        print("Publishing JSON...")
        producer = conn.Producer(serializer='json')
        producer.publish({'name': '/tmp/lolcat1.avi', 'size': 1301013, 'index': i},
                        exchange=media_player_exchange, routing_key='playback',
                        declare=[playback_queue])
        time.sleep(5)
