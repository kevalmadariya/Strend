
from contextlib import asynccontextmanager
from concurrent.futures import ProcessPoolExecutor
from fastapi import FastAPI

# Global pool reference
process_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global process_pool
    # Limit workers to avoid crashing the server
    # We use 'spawn' or default context. 
    # Note: On Windows, default is 'spawn' which is good.
    process_pool = ProcessPoolExecutor(max_workers=3)
    yield
    process_pool.shutdown()
