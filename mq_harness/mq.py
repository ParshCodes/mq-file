import pika
from .config import Settings


def connection(settings: Settings) -> pika.BlockingConnection:
    credentials = pika.PlainCredentials(settings.rabbitmq_user, settings.rabbitmq_password)
    return pika.BlockingConnection(
        pika.ConnectionParameters(
            host=settings.rabbitmq_host,
            port=settings.rabbitmq_port,
            credentials=credentials,
            heartbeat=60,
            blocked_connection_timeout=30,
            connection_attempts=12,
            retry_delay=5,
        )
    )


def declare_topology(channel, settings: Settings) -> None:
    channel.exchange_declare(exchange="orders.dlx", exchange_type="direct", durable=True)
    channel.queue_declare(queue=settings.dlq, durable=True)
    channel.queue_bind(queue=settings.dlq, exchange="orders.dlx", routing_key="failed")
    channel.queue_declare(
        queue=settings.queue,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "orders.dlx",
            "x-dead-letter-routing-key": "failed",
        },
    )

