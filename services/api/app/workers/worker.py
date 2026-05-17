from rq import Worker

from app.workers.queue import get_redis_connection, get_run_queue


def main() -> None:
    queue = get_run_queue()
    worker = Worker([queue], connection=get_redis_connection())
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
