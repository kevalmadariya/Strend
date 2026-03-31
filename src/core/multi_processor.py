from contextlib import asynccontextmanager
from concurrent.futures import ProcessPoolExecutor
from fastapi import FastAPI
from src.cron_jobs.news_cron_job import start_news_cron

# Global pool reference
process_pool = None
news_scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global process_pool
    global news_scheduler
    # Limit workers to avoid crashing the server
    # We use 'spawn' or default context. 
    # Note: On Windows, default is 'spawn' which is good.
    process_pool = ProcessPoolExecutor(max_workers=3)
    
    # Start cron jobs that are attached to FastAPI process
    news_scheduler = start_news_cron()
    
    yield
    
    process_pool.shutdown()
    if news_scheduler:
        news_scheduler.shutdown()

