import json
import re
import inspect
from typing import Optional, Dict
from dotenv import load_dotenv
import os
from langchain_groq import ChatGroq
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from src.agent.agents import get_agent_config
# from src.core.vector_db import ToolVectorDB  # <-- Commented out

load_dotenv()

class PlanningAgent:
    def __init__(self, agent_name: str, unique_id: str = None):
        print(f"\n[*] Initializing PlanningAgent: {agent_name}")

        self.unique_id = unique_id
        self.config = get_agent_config(agent_name, unique_id)

        self.name = self.config.name
        self.base_prompt = self.config.base_prompt

        # --------------------------------------------------
        # LOAD TOOLS
        # --------------------------------------------------
        self.tools = {}
        print("\n[*] Loading tools:")

        for factory in self.config.tools:
            tool = factory(unique_id)
            self.tools[tool.name] = tool
            print(f"   [+] Loaded tool: {tool.name}")

        print(f"[+] Total tools loaded: {len(self.tools)}")

        # --------------------------------------------------
        # VECTOR DB (DISABLED)
        # --------------------------------------------------
        # self.vector_db = ToolVectorDB(
        #     base_path="./vector_db",
        #     agent_name=self.name
        # )
        # self.vector_db.sync_agent_tools(self.tools)

        # --------------------------------------------------
        # LLM
        # --------------------------------------------------
        # self.llm = ChatGroq(
        #     model_name="llama-3.3-70b-versatile",
        #     temperature=0
        # )


        self.llm = ChatNVIDIA(
        model=os.getenv("MODEL_NAME"),
        api_key="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", 
        temperature=0,
        top_p=0.7,
        max_tokens=1024,
        )

        # self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

        # --------------------------------------------------
        # STATE
        # --------------------------------------------------
        self.history = []
        # self.active_tool_name = None # No longer relying on sticky tool state, LLM decides

        print(f"\n[+] {self.name} ready")

    # --------------------------------------------------
    # HELPER: Get Tools Description
    # --------------------------------------------------
    def _get_tools_prompt(self):
        tools_desc = []
        for name, tool in self.tools.items():
            params_parts = []
            for p in tool.parameters:
                req_label = 'REQUIRED' if p.required else 'optional'
                if p.type in ('list', 'array'):
                    params_parts.append(f"{p.name} ({req_label}, type: JSON array of strings, e.g. [\"val1\", \"val2\"]) - {p.description}")
                else:
                    params_parts.append(f"{p.name} ({req_label}, type: {p.type}) - {p.description}")
            params_str = "; ".join(params_parts)
            tools_desc.append(f"- {name}: {tool.description}\n  Params: {params_str}")
        return "\n".join(tools_desc)

    # --------------------------------------------------
    # HELPER: Coerce arguments to match expected types
    # --------------------------------------------------
    def _coerce_arguments(self, tool_name: str, arguments: dict) -> dict:
        """Convert string-typed list/array params into actual Python lists."""
        if tool_name not in self.tools:
            return arguments
        tool = self.tools[tool_name]
        param_types = {p.name: p.type for p in tool.parameters}
        
        coerced = dict(arguments)
        for key, value in coerced.items():
            expected_type = param_types.get(key)
            if expected_type in ('list', 'array') and isinstance(value, str):
                # Try JSON parse first: '["A", "B"]'
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        coerced[key] = parsed
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass
                # Fallback: comma/space separated string: "A, B, C"
                coerced[key] = [t.strip() for t in value.split(',') if t.strip()]
        return coerced

    # --------------------------------------------------
    # HELPER: Merge live fetched data back into the DB
    # --------------------------------------------------
    def _merge_live_data_to_db(self, result: str):
        """
        After fetch_stock_data returns, parse the JSON result and UPDATE
        the SQLite database with real-time values (High, Open, Close, etc.)
        so that subsequent computed columns use fresh data.
        """
        from src.core.sqlite_manager import has_session, get_connection

        if not self.unique_id or not has_session(self.unique_id):
            return

        # Extract JSON from the result (it may have progress text before it)
        json_str = None
        for line in result.strip().split('\n'):
            line = line.strip()
            if line.startswith('{'):
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict) and 'data' in parsed:
                        json_str = parsed
                        break
                except (json.JSONDecodeError, TypeError):
                    pass

        if not json_str or not json_str.get('data'):
            return

        conn = get_connection(self.unique_id)
        data = json_str['data']
        updated_count = 0

        for ticker_key, rows in data.items():
            if not rows or not isinstance(rows, list):
                continue

            # Use the last row (most recent data point)
            latest = rows[-1] if rows else {}
            real_high = latest.get('High')
            real_open = latest.get('Open')
            real_close = latest.get('Close') or latest.get('Price')
            real_low = latest.get('Low')
            real_volume = latest.get('Volume')

            # Strip .NS / .BO suffix to match database tickers
            clean_ticker = ticker_key.replace('.NS', '').replace('.BO', '')

            if real_high is not None:
                try:
                    conn.execute(
                        'UPDATE "excel_data" SET "todayhigh" = ? WHERE "ticker" = ?',
                        (float(real_high), clean_ticker)
                    )
                    updated_count += 1
                except Exception:
                    pass

        if updated_count > 0:
            conn.commit()
            print(f"[+] Merged live data: updated todayhigh for {updated_count} tickers in DB")

    # --------------------------------------------------
    # JSON EXTRACTION
    # --------------------------------------------------
    def _extract_json(self, text: str) -> Optional[Dict]:
        text = re.sub(r"```json|```", "", text).strip()
        
        start_idx = 0
        while True:
            start = text.find("{", start_idx)
            if start == -1:
                break
            
            # Find matching closing brace tracking quotes/escapes
            brace_count = 0
            end = -1
            in_string = False
            escape = False
            for i in range(start, len(text)):
                char = text[i]
                if escape:
                    escape = False
                    continue
                if char == '\\':
                    escape = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i
                            break
            
            if end != -1:
                candidate = text[start:end + 1]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    pass
            
            start_idx = start + 1
            
        return None

    # --------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------
    async def run(self, user_input: str):
        print(f"\n[>] User: {user_input}")

        # Build dynamic prompt with all tools
        tools_info = self._get_tools_prompt()
        
        system_prompt = f"""
        {self.base_prompt}

        AVAILABLE TOOLS:
        {tools_info}

        INSTRUCTIONS:
        1. Analyze the user's request.
        2. If the user's intent matches a tool, check if you have ALL required parameters.
           - Map synonyms: 'make' -> 'create', 'add' -> 'insert', etc.
        3. IF YOU HAVE ALL PARAMS: Return strictly JSON:
           {{ "tool": "tool_name", "arguments": {{ "param1": "value1", ... }} }}
        4. IF MISSING PARAMS: Ask the user specifically for the missing information (do not return JSON yet).
        5. IF NO TOOL MATCHES: Just chat helpfully.
        
        DATA FRESHNESS RULES:
        - If user asks about "today's high", "current price", "live data", "real-time" values, or any market data NOT present in the uploaded Excel:
          First extract the tickers from the database using execute_query, then call fetch_stock_data with those tickers, today's date, duration="1d", and timeframe="1day" to get real values.
        - Only use columns already in the database if they clearly contain the data the user needs.
        - When the user refers to columns like "col_3 (C)", map it to the actual column name by position (e.g., col 1=stock_name, col 2=ticker, col 3=price, etc based on the schema).
        - If the user explicitly asks to "analyze excel", you MUST use the 'analyze_excel' tool instead of 'make_temp_database'.

        MULTI-STEP REASONING:
        - For complex tasks requiring multiple tools, execute ONE tool per response.
        - After each tool result, decide your next action based on the result.
        - Example: Extract tickers -> fetch real-time data -> add computed column -> query results.
        - Never skip steps or assume data exists without checking.

        IMPORTANT:
        - Do not output JSON if you are asking a question.
        - Only one JSON block per response.
        """

        # Append initial user input
        self.history.append(HumanMessage(content=user_input))

        max_turns = 10
        for turn in range(max_turns):
            messages = (
                [SystemMessage(content=system_prompt)] + 
                self.history
            )

            response = self.llm.invoke(messages)
            content = response.content.strip()
            print(f"\n[<] LLM Response: {content}")

            tool_call = self._extract_json(content)
            
            # If valid JSON tool call found, execute it
            if tool_call and "tool" in tool_call and "arguments" in tool_call:
                tool_name = tool_call["tool"]
                if tool_name in self.tools:
                    print(f"[>] Executing tool {tool_name}")
                    tool_obj = self.tools[tool_name]
                    
                    # Coerce arguments (e.g. string tickers -> list)
                    tool_args = self._coerce_arguments(tool_name, tool_call["arguments"])
                    
                    # Log AI's tool call intent
                    self.history.append(AIMessage(content=content))

                    result = ""
                    try:
                        func = tool_obj.function
                        if inspect.isasyncgenfunction(func):
                            async for item in func(**tool_args):
                                print(item) 
                                yield str(item)
                                result += str(item) + "\n"
                        elif inspect.iscoroutinefunction(func):
                            res = await func(**tool_args)
                            yield str(res)
                            result = str(res)
                        else:
                            res = func(**tool_args)
                            yield str(res)
                            result = str(res)
                    except Exception as e:
                        result = f"[!] Tool error: {e}"
                        yield result
                    
                    # Auto-merge live data into DB after fetch_stock_data
                    if tool_name == 'fetch_stock_data':
                        self._merge_live_data_to_db(result)
                    
                    # Feed tool result back into history to continue reasoning
                    observation = f"Tool '{tool_name}' result:\n{result}\n\nWhat is your next step or final answer?"
                    self.history.append(HumanMessage(content=observation))
                    continue
                else:
                    err = f"[!] Error: LLM hallucinated tool '{tool_name}'"
                    self.history.append(AIMessage(content=content))
                    self.history.append(HumanMessage(content=err))
                    yield err
                    continue

            # If no tool call or just chat/question, yield final answer and break
            self.history.append(AIMessage(content=content))
            yield content
            return
            
        yield "[!] Error: Maximum reasoning turns exceeded."
