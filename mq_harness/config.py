from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    rabbitmq_host: str = os.getenv("RABBITMQ_HOST", "localhost")
    rabbitmq_port: int = int(os.getenv("RABBITMQ_PORT", "5672"))
    rabbitmq_user: str = os.getenv("RABBITMQ_USER", "mq_user")
    rabbitmq_password: str = os.getenv("RABBITMQ_PASSWORD", "mq_password")
    queue: str = os.getenv("ORDER_QUEUE", "orders")
    dlq: str = os.getenv("DEAD_LETTER_QUEUE", "orders.dead")
    incoming: Path = Path(os.getenv("INCOMING_DIR", "/data/incoming"))
    rejected: Path = Path(os.getenv("REJECTED_DIR", "/data/rejected"))
    archive: Path = Path(os.getenv("ARCHIVE_DIR", "/data/archive"))
    schemas: Path = Path(os.getenv("SCHEMA_DIR", "/app/schemas"))
    log_file: Path = Path(os.getenv("LOG_FILE", "/data/logs/pipeline.jsonl"))
    oracle_user: str = os.getenv("ORACLE_USER", "mq_user")
    oracle_password: str = os.getenv("ORACLE_PASSWORD", "mq_password")
    oracle_dsn: str = os.getenv("ORACLE_DSN", "localhost:1521/FREEPDB1")
    failure_rate: float = float(os.getenv("PROCESSING_FAILURE_RATE", "0.05"))
