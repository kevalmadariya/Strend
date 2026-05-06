import json
import re
import inspect
from typing import Optional, Dict
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from src.agent.agents import get_agent_config
# from src.core.vector_db import ToolVectorDB  # <-- Commented out

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
        self.llm = ChatGroq(
            model_name="llama-3.3-70b-versatile",
            temperature=0
        )

        # self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

        # --------------------------------------------------
        # STATE
        # --------------------------------------------------
        self.history = []
        # self.active_tool_name = None # No longer relying on sticky tool state, LLM decides

        print(f"\n✅ {self.name} ready")

    # --------------------------------------------------
    # HELPER: Get Tools Description
    # --------------------------------------------------
    def _get_tools_prompt(self):
        tools_desc = []
        for name, tool in self.tools.items():
            params = ", ".join([f"{p.name} ({'Req' if p.required else 'Opt'})" for p in tool.parameters])
            tools_desc.append(f"- {name}: {tool.description} | Params: [{params}]")
        return "\n".join(tools_desc)

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
        
        IMPORTANT:
        - Do not output JSON if you are asking a question.
        - Only one JSON block per response.
        """

        messages = (
            [SystemMessage(content=system_prompt)] + 
            self.history + 
            [HumanMessage(content=user_input)]
        )

        response = self.llm.invoke(messages)
        content = response.content.strip()
        print(f"\n💬 LLM Response: {content}")

        tool_call = self._extract_json(content)
        
        # If valid JSON tool call found, execute it
        if tool_call and "tool" in tool_call and "arguments" in tool_call:
            tool_name = tool_call["tool"]
            if tool_name in self.tools:
                print(f"🚀 Executing tool {tool_name}")
                tool_obj = self.tools[tool_name]
                
                # Yield the tool selection thought/confirmation first if there is any pre-text? 
                # Usually LLM might say "Sure, executing..." then JSON. 
                # extract_json handles the block. formatting might strip the pre-text.
                # Let's yield what the LLM said first if it's not just JSON? 
                # For now, let's just run the tool.

                result = ""
                try:
                    func = tool_obj.function
                    if inspect.isasyncgenfunction(func):
                        async for item in func(**tool_call["arguments"]):
                            print(item) 
                            yield str(item)
                            result += str(item) + "\n"
                    elif inspect.iscoroutinefunction(func):
                        res = await func(**tool_call["arguments"])
                        yield str(res)
                        result = str(res)
                    else:
                        res = func(**tool_call["arguments"])
                        yield str(res)
                        result = str(res)
                except Exception as e:
                    result = f"❌ Tool error: {e}"
                    yield result
                
                # Append full turn to history
                self.history.append(HumanMessage(content=user_input))
                self.history.append(AIMessage(content=str(result)))
                return
            else:
                 content = f"❌ Error: LLM hallucinated tool '{tool_name}'"

        # If no tool call or just chat/question
        self.history.append(HumanMessage(content=user_input))
        self.history.append(AIMessage(content=content))
        yield content
