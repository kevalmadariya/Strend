import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Ensure the parent directory of `src` is in the path so that absolute imports work correctly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.append(project_root)

# Setup basic logging to output to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("news_cron_job")

# Load environment variables from the project root .env
load_dotenv(os.path.join(project_root, ".env"))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Import our target scraper function
from src.tools.utils.pulse_scraper import extract_pulse_news


async def job():
    """
    Scheduled job to extract news.
    """
    logger.info("Starting background extraction of Pulse News...")
    try:
        # call extract_pulse_news 
        result = await extract_pulse_news()
        
        # Determine success from the length of general output to give some log context
        if isinstance(result, dict) and 'error' not in result:
            general_count = len(result.get('general', []))
            logger.info(f"Successfully extracted pulse news. Processed {general_count} general articles (among other categories).")
        else:
            logger.error(f"Extraction returned an issue/error state: {result}")
            
    except Exception as e:
        logger.error(f"Error executing extract_pulse_news: {e}", exc_info=True)


def start_news_cron() -> AsyncIOScheduler:
    logger.info("Initializing Pulse News Cron Job Scheduler...")
    
    cron_schedule = os.getenv("PULSE_NEWS_CRON_SCHEDULE")
    
    if not cron_schedule:
        logger.warning("PULSE_NEWS_CRON_SCHEDULE not found in env. Defaulting to '*/5 * * * *'")
        cron_schedule = "*/5 * * * *"
        
    logger.info(f"Configured cron schedule: '{cron_schedule}'")

    scheduler = AsyncIOScheduler()
    
    try:
        trigger = CronTrigger.from_crontab(cron_schedule)
    except Exception as e:
        logger.error(f"Invalid cron expression '{cron_schedule}': {e}. Using fallback.")
        trigger = CronTrigger.from_crontab("*/5 * * * *")

    scheduler.add_job(
        job,
        trigger=trigger,
        id="pulse_news_extractor_job",
        replace_existing=True,
    )
    
    scheduler.start()
    logger.info("Scheduler started successfully. Attached to FastAPI Event Loop.")
    return scheduler

if __name__ == "__main__":
    # For local standalone testing
    if os.getenv("ENVIRONMENT_OS") == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    scheduler = start_news_cron()
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        logger.info("Program terminated by user.")
        scheduler.shutdown()
