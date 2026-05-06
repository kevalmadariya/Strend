"""
Workflow Controller
===================
POST /workflow/run — Accepts a workflow definition and spawns a
separate process to execute it. The main FastAPI process continues
to handle normal API requests without any interference.

The workflow process is fully isolated: no FastAPI routes, no uvicorn,
just the pipeline execution.
"""

import logging
import multiprocessing
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.core.db import get_db_connection

logger = logging.getLogger("workflow_controller")

router = APIRouter(prefix="/workflow")


# ─── Request Models ──────────────────────────────────────────────────────────

class StockPickParams(BaseModel):
    stock_list: Optional[str] = Field(None, description="Comma-separated tickers")
    method: Optional[str] = Field(
        "macd_bearish_bullish",
        description="Chartink method: macd_bullish, macd_bullish_rsi, macd_bullish_adx, rsi_70_above, simple, macd_bearish_bullish"
    )
    no_of_stocks: Optional[int] = Field(60, description="Number of stocks to fetch")
    query: Optional[str] = Field(None, description="Custom Chartink query text")


class FilterItem(BaseModel):
    field: str = Field(..., description="Field to filter on (volume, min_price, max_price, %chg, trend, macd, rsi_value, adx, score, recent)")
    operator: str = Field("greater", description="Comparison operator: greater, greater_equal, less, less_equal, equals, not_equals")
    value: float | bool | int = Field(..., description="Value to compare against")


class WorkflowStep(BaseModel):
    step: str = Field(..., description="Step name: stock_pick, filter, technical_analysis, fundamental_analysis, news_analysis, email")
    params: dict = Field(default_factory=dict, description="Step-specific parameters")


class WorkflowRequest(BaseModel):
    """
    The workflow definition sent by the frontend.
    
    The `workflow` list defines the ORDER of execution.
    Each step receives the stock list from the previous step.

    Example:
    {
        "workflow": [
            {"step": "stock_pick", "params": {"method": "macd_bullish", "no_of_stocks": 60}},
            {"step": "filter", "params": {"filters": [{"field": "volume", "operator": "greater", "value": 50000}]}},
            {"step": "technical_analysis", "params": {"filters": [{"field": "trend", "operator": "equals", "value": 1}]}},
            {"step": "news_analysis", "params": {"filters": [{"field": "recent", "operator": "equals", "value": true}]}},
            {"step": "email", "params": {"format": "pdf"}}
        ]
    }
    """
    workflow: List[WorkflowStep] = Field(..., description="Ordered list of workflow steps to execute")


# ─── Helpers ─────────────────────────────────────────────────────────────────

VALID_STEPS = {"stock_pick", "filter", "technical_analysis", "fundamental_analysis", "news_analysis", "email"}

VALID_METHODS = {"macd_bullish", "macd_bullish_rsi", "macd_bullish_adx", "rsi_70_above", "simple", "macd_bearish_bullish"}


def _get_user_email(user_id: int) -> str:
    """Fetch user's email from DB."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT email_id FROM "user" WHERE user_id = %s', (user_id,))
        row = cur.fetchone()
        return row[0] if row else ""
    except Exception as e:
        logger.error(f"Failed to fetch user email: {e}")
        return ""
    finally:
        if conn:
            conn.close()


# ─── Endpoint ────────────────────────────────────────────────────────────────

@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
def run_workflow(data: WorkflowRequest, request: Request):
    """
    Launch a workflow pipeline in a **separate process**.

    Returns 202 Accepted immediately. The workflow runs in the background.
    On completion, a notification is saved to the `notification` table.
    """
    # Extract user from JWT (set by auth middleware)
    user_payload = getattr(request.state, "user", None)
    if not user_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    user_id = int(user_payload.get("sub", 0))
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token: sub missing"
        )

    # Validate steps
    workflow_steps = []
    for step_config in data.workflow:
        step_name = step_config.step.lower().strip()
        if step_name not in VALID_STEPS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid step '{step_name}'. Valid steps: {', '.join(sorted(VALID_STEPS))}"
            )

        # Validate method if stock_pick
        if step_name == "stock_pick":
            method = step_config.params.get("method", "macd_bearish_bullish")
            if method and method not in VALID_METHODS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid method '{method}'. Valid methods: {', '.join(sorted(VALID_METHODS))}"
                )

        workflow_steps.append({
            "step": step_name,
            "params": step_config.params,
        })

    if not workflow_steps:
        raise HTTPException(status_code=400, detail="Workflow must have at least one step")

    # Get user email for the email step
    user_email = _get_user_email(user_id)

    logger.info(f"🚀 Spawning workflow process for user {user_id} with {len(workflow_steps)} step(s)")

    # ── Spawn a SEPARATE process ─────────────────────────────────────────
    # This process is completely isolated from FastAPI.
    # It won't affect the main process or its API routes.
    from src.tools.utils.workflow_executor import run_workflow_process

    process = multiprocessing.Process(
        target=run_workflow_process,
        args=(workflow_steps, user_id, user_email),
        daemon=True,  # Daemon so it doesn't block server shutdown
        name=f"workflow-user-{user_id}",
    )
    process.start()

    logger.info(f"✅ Workflow process spawned: PID={process.pid}")

    return {
        "status": "accepted",
        "message": "Workflow started in background. You will be notified upon completion.",
        "process_id": process.pid,
        "steps": [s["step"] for s in workflow_steps],
        "user_id": user_id,
    }
