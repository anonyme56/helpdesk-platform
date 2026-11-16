"""Point d'entrée du worker : serveur de métriques + worker RQ."""
import json
import logging
import sys
import threading
import time

import redis
from prometheus_client import Gauge, start_http_server
from rq import Queue, SimpleWorker

from config import settings

QUEUE_LENGTH = Gauge("worker_queue_length", "Tâches en attente dans la file", ["queue"])
FAILED = Gauge("worker_failed_jobs", "Tâches en échec définitif", ["queue"])


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname,
                   "logger": record.name, "msg": record.getMessage()}
        payload.update(getattr(record, "fields", {}) or {})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging():
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    logging.basicConfig(level=settings.log_level, handlers=[h], force=True)


def watch_queue(conn: redis.Redis):
    q = Queue("default", connection=conn)
    while True:
        try:
            QUEUE_LENGTH.labels("default").set(len(q))
            FAILED.labels("default").set(q.failed_job_registry.count)
        except redis.RedisError:
            pass
        time.sleep(5)


def main():
    setup_logging()
    conn = redis.Redis(host=settings.redis_host, port=settings.redis_port,
                       password=settings.redis_password or None)
    start_http_server(9100)
    threading.Thread(target=watch_queue, args=(conn,), daemon=True).start()
    logging.getLogger("worker").info("worker démarré")
    # SimpleWorker : les taches tournent dans CE processus. Le Worker classique de RQ fait un fork par tache,
    # et les compteurs Prometheus incrementes dans le fils ne sont jamais vus par le processus qui sert /metrics.
    SimpleWorker(["default"], connection=conn).work(with_scheduler=False, logging_level="WARNING")


if __name__ == "__main__":
    main()
