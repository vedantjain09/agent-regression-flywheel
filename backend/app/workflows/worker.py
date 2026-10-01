"""Temporal worker entrypoint: python -m app.workflows.worker
Connects to a Temporal server (TEMPORAL_ADDRESS, default localhost:7233)
and polls the "regression-runs" task queue."""
from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from app.workflows.regression_run import RegressionRunWorkflow, run_trial_activity

TASK_QUEUE = "regression-runs"


async def main() -> None:
    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    client = await Client.connect(address)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[RegressionRunWorkflow],
        activities=[run_trial_activity],
    )
    print(f"worker polling task queue '{TASK_QUEUE}' on {address}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
