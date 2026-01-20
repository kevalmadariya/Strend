import json
import re
import inspect
from typing import Optional, Dict
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from sentence_transformers import SentenceTransformer

from src.agent.agents import get_agent_config
from src.core.vector_db import ToolVectorDB

load_dotenv()

class PlanningAgent:
    def __init__(self, agent_name: str, unique_id: str = None):
        print(f"\n⚙️ Initializing PlanningAgent: {agent_name}")

        self.config = get_agent_config(agent_name, unique_id)

        self.name = self.config.name
        self.base_prompt = self.config.base_prompt

        # --------------------------------------------------
        # LOAD TOOLS
        # --------------------------------------------------
        self.tools = {}
        print("\n🛠️ Loading tools:")

        for factory in self.config.tools:
            tool = factory(unique_id)
            self.tools[tool.name] = tool
            print(f"   ✅ Loaded tool: {tool.name}")

        print(f"📦 Total tools loaded: {len(self.tools)}")

        # --------------------------------------------------
        # VECTOR DB (PER AGENT)
        # --------------------------------------------------
        self.vector_db = ToolVectorDB(
            base_path="./vector_db",
            agent_name=self.name
        )

        self.vector_db.sync_agent_tools(self.tools)

        # --------------------------------------------------
        # LLM
        # --------------------------------------------------
        self.llm = ChatGroq(
            model_name="llama-3.3-70b-versatile",
            temperature=0
        )

        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

        # --------------------------------------------------
        # STATE
        # --------------------------------------------------
        self.history = []
        self.active_tool_name = None

        print(f"\n✅ {self.name} ready")

    # --------------------------------------------------
    # ROUTING
    # --------------------------------------------------
    def _semantic_route(self, query: str) -> Optional[str]:
        tool_name = self.vector_db.search(query)

        if tool_name and tool_name in self.tools:
            print(f"🎯 Router selected tool: {tool_name}")
            return tool_name

        print("⚠️ No suitable tool found")
        return None

    # --------------------------------------------------
    # JSON EXTRACTION
    # --------------------------------------------------
    def _extract_json(self, text: str) -> Optional[Dict]:
        text = re.sub(r"```json|```", "", text).strip()
        start = text.find("{")
        if start == -1:
            return None
        try:
            return json.loads(text[start:text.rfind("}") + 1])
        except Exception as e:
            print(f"❌ JSON parse error: {e}")
            return None

    # --------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------
    async def run(self, user_input: str):
        print(f"\n👤 User: {user_input}")

        # STEP 1: ROUTING
        if not self.active_tool_name:
            self.active_tool_name = self._semantic_route(user_input)

        # STEP 2: CHAT
        if not self.active_tool_name:
            messages = [
                SystemMessage(content=self.base_prompt),
                HumanMessage(content=user_input)
            ]
            response = self.llm.invoke(messages)
            return response.content

        # STEP 3: TOOL FILLING
        tool_obj = self.tools[self.active_tool_name]
        print(tool_obj)
        print(f"\n🛠️ Active tool: {tool_obj.name}")

        system_prompt = f"""
            {self.base_prompt}
            CURRENT FOCUS: You are using the tool '{tool_obj.name}'.
            Description: {tool_obj.description}
            Required Parameters: {tool_obj.parameters}
            INSTRUCTIONS:
            1. Check conversation history for parameters.
            2. If missing, ask user strictly for missing parameters.
            3. If ALL present, return JSON:
            {{ "tool": "{tool_obj.name}", "arguments": {{ ... }} }}
            """

        messages = (
            [SystemMessage(content=system_prompt)] + 
            self.history + 
            [HumanMessage(content=user_input)]
        )

        response = self.llm.invoke(messages)
        # response = {content: "fine"}
        content = response.content.strip()
        print(f"\n💬 LLM Response: {content}")

        tool_call = self._extract_json(content)
        print(f"\n🤖 Agent Response: {tool_call}")
        # STEP 4: EXECUTION
        if tool_call and "arguments" in tool_call:
            print(f"🚀 Executing tool {tool_obj.name}")
            try:
                func = tool_obj.function
                if inspect.isasyncgenfunction(func):
                    results_list = []
                    async for item in func(**tool_call["arguments"]):
                        results_list.append(str(item))
                    result = "\n".join(results_list)
                elif inspect.iscoroutinefunction(func):
                    result = await func(**tool_call["arguments"])
                else:
                    result = func(**tool_call["arguments"])
            except Exception as e:
                result = f"❌ Tool error: {e}"

            self.history = []
            self.active_tool_name = None
            return result

        # STEP 5: CONTINUE
        self.history.append(HumanMessage(content=user_input))
        self.history.append(AIMessage(content=content))
        return content
