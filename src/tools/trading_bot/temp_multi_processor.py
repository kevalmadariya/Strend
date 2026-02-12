process_pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global process_pool
    # Limit workers to avoid crashing the server (e.g., 3 concurrent reports)
    process_pool = ProcessPoolExecutor(max_workers=3)
    yield
    process_pool.shutdown()



import asyncio
import functools
import os
from concurrent.futures import ProcessPoolExecutor


# Global pool reference
process_pool = None


def _worker_entrypoint(func, args, kwargs):
    """
    This generic function runs INSIDE the new process.
    It receives the target function and arguments, creates a loop, and runs it.
    """
    print(f"[Process {os.getpid()}] Running {func.__name__}...")
    try:
        # Since we are in a new process, we must start a new event loop
        return asyncio.run(func(*args, **kwargs))
    except Exception as e:
        print(f"Error in process: {e}")
        raise e


def run_in_process(func):
    """
    Add this decorator to ANY async function to make it run
    automatically in the ProcessPoolExecutor.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_running_loop()
       
        # We assume 'process_pool' is available globally (initialized in lifespan)
        # We pass the original function + args to the generic worker
        return await loop.run_in_executor(
            process_pool,
            _worker_entrypoint,
            func,
            args,
            kwargs
        )
    return wrapper

