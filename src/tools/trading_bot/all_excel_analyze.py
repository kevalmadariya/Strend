"""
Tool: all_excel_analyze
=======================
Analyzes all cached strategy Excel files for today, calls stock_analysis_util for each,
and appends the results into respective slot-wise CSV files in the dataset folder.
"""

import json
import os
import re
from datetime import datetime
import pandas as pd
from src.tools.base import DynamicTool, ToolParam
from src.tools.utils.stock_analysis_util import analyze_stock_data


def makeTool(router):
    """Factory function for the All Excel Analyze tool."""

    def func(unique_id):

        async def all_excel_analyze(date_str: str = None):
            """
            Analyze all Excel files stored in cache for a given date (defaults to today),
            and append the results to dataset CSVs slot-wise.
            """
            try:
                # 1. Determine date (unchanged)
                if not date_str or date_str.lower() == "today":
                    from zoneinfo import ZoneInfo
                    try:
                        IST = ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))
                        date_str = datetime.now(IST).date().isoformat()
                    except Exception:
                        date_str = datetime.now().date().isoformat()

                # 2. Paths (unchanged)
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
                cache_dir = os.path.join(project_root, "cache", "strategy")
                dataset_dir = os.path.join(project_root, "dataset")
                os.makedirs(dataset_dir, exist_ok=True)

                if not os.path.exists(cache_dir):
                    yield json.dumps({"status": "error", "error": f"Cache directory not found: {cache_dir}"})
                    return

                all_data = []
                processed_files = []

                # 3. Iterate over files
                for filename in os.listdir(cache_dir):
                    if filename.endswith(".xlsx") and date_str in filename:
                        file_path = os.path.join(cache_dir, filename)

                        # Extract slot
                        slot_match = re.search(r'(slot_\d+)', filename)
                        if not slot_match:
                            continue
                        slot_label = slot_match.group(1)

                        # ---------- NEW: Extract generation time ----------
                        gen_time = None
                        time_match = re.search(r'_(\d{4})_(\d{4})\.xlsx$', filename)
                        if time_match:
                            gen_time = time_match.group(2)   # e.g., "1003"
                        # -------------------------------------------------

                        # Read Excel
                        try:
                            df = pd.read_excel(file_path)
                            records = df.to_dict(orient="records")
                            data_payload = {"file": records}

                            # Call analyze utility WITH generation_time and slot
                            result = analyze_stock_data(
                                data_payload,
                                date_str,
                                generation_time=gen_time,  # <-- pass extracted time
                                slot=slot_label            # <-- pass extracted slot
                            )

                            if result.get("status") == "success":
                                analyzed_rows = result.get("data", {}).get("file", [])
                                if analyzed_rows:
                                    for r in analyzed_rows:
                                        if "date" not in r:
                                            r["date"] = date_str
                                        r["slot"] = slot_label

                                    all_data.extend(analyzed_rows)

                                    csv_path = os.path.join(dataset_dir, f"{slot_label}.csv")
                                    out_df = pd.DataFrame(analyzed_rows)
                                    file_exists = os.path.exists(csv_path)
                                    out_df.to_csv(csv_path, mode='a', header=not file_exists, index=False)
                                    processed_files.append(filename)
                        except Exception as e:
                            print(f"Error processing {filename}: {e}")
                            continue

                yield json.dumps({
                    "status": "success",
                    "data": all_data,
                })

            except Exception as e:
                yield json.dumps({
                    "status": "error",
                    "error": f"Analysis failed: {str(e)}"
                })
        return DynamicTool(
            name="all_excel_analyze",
            description="Analyze all Excel cache files for a specific date (defaults to today). It reads each excel file, performs stock data analysis, appends the result to /dataset/{slot}.csv slot-wise, and returns all merged data.",
            function=all_excel_analyze,
            parameters=[
                ToolParam(
                    name="date_str",
                    type="string",
                    description="Date for analysis in YYYY-MM-DD format. Defaults to current date if not provided.",
                    required=False,
                ),
            ],
            endpoint="/all-excel-analyze",
            router=router,
        )

    return func
