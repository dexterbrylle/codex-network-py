#!/usr/bin/env python3
from monitor.db import init_db
from monitor.scheduler import setup_schedule, run_loop


def main():
    init_db()
    setup_schedule()
    run_loop()


if __name__ == "__main__":
    main()
