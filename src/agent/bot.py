import time
import json
import re
from typing import List, Dict, Optional, Any

import inspect
from sentence_transformers import SentenceTransformer, util
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv

# Import the registry logic
from src.agent.agents import get_agent_config

load_dotenv()

class PlanningAgent:
    def __init__(self, agent_name: str, unique_id: str = None):
        """
        Dynamic Initialization:
        1. Looks up the agent factory by name.
        2. Loads tools and prompts.
        3. Builds the Semantic Router specifically for those tools.
        """
        print(f"⚙️ Initializing PlanningAgent: {agent_name}...")
        
        # 1. Load Configuration from Factory
        self.config = get_agent_config(agent_name, unique_id)
        
        self.name = self.config.name
        self.base_prompt = self.config.base_prompt
        self.tools = {}

        for tool_factory in self.config.tools:
            tool = tool_factory(unique_id)   # 🔥 EXECUTE FACTORY
            self.tools[tool.name] = tool

        print(self.name)
        print(self.base_prompt)
        print(self.tools)
        print(type(self.tools))
        print(self.tools.keys())
        print(type(next(iter(self.tools.values()))))

        
        # 2. Initialize LLM
        self.llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0)
        
        # 3. Initialize State
        self.history = []
        self.active_tool_name = None

        # 4. Build Semantic Router (Dynamic based on loaded tools)
        self._build_router()
        print(f"✅ {self.name} Ready with {len(self.tools)} tools.")

    def _build_router(self):
            """Encodes tool triggers for this specific agent instance."""
            print(f"🔌 Building Router for {len(self.tools)} tools...")
            
            self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
            self.tool_names = []
            triggers = []
            print("tool mapping:")
            print(self.tools)

            for name, tool in self.tools.items():
                route_text = getattr(tool, "trigger", None) or tool.description or tool.name
                
                if route_text:
                    self.tool_names.append(name)
                    triggers.append(route_text)
                    print(f"   Mapped '{name}' -> Trigger: '{route_text[:50]}...'")
                else:
                    print(f"⚠️  Skipping '{name}': No trigger or description found.")

            if triggers:
                # Convert to tensor immediately to ensure shape is correct
                self.tool_embeddings = self.embedder.encode(triggers, convert_to_tensor=True)
                print(f"✅ Router built with {len(triggers)} triggers.")
            else:
                self.tool_embeddings = None
                print("❌ Router setup failed: No valid triggers found.")
    # def _build_router(self):
    #     """Encodes tool triggers for this specific agent instance."""
    #     self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        
    #     # Assuming tools have a .trigger or .description attribute for routing
    #     self.tool_names = list(self.tools.keys())
    #     # Fallback to description if trigger not present
    #     triggers = [getattr(t, "trigger", t.description) for t in self.tools.values()]
        
    #     if triggers:
    #         self.tool_embeddings = self.embedder.encode(triggers, convert_to_tensor=True)
    #     else:
    #         self.tool_embeddings = None

    def _semantic_route(self, query: str, threshold: float = 0.40) -> Optional[str]:
        if self.tool_embeddings is None:
            return None
            
        query_embedding = self.embedder.encode(query, convert_to_tensor=True)
        hits = util.semantic_search(query_embedding, self.tool_embeddings, top_k=1)

        if hits and hits[0][0]["score"] >= threshold:
            return self.tool_names[hits[0][0]["corpus_id"]]
        return None

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Helper to safely parse JSON from LLM output."""
        text = re.sub(r"```json|```", "", text).strip()
        start = text.find("{")
        if start == -1: return None
        try:
            return json.loads(text[start:text.rfind("}") + 1])
        except:
            return None

    async def run(self, user_input: str):
            # ------------------------------------------------------------------
            # STEP 1: ROUTING 
            # ------------------------------------------------------------------
            if not self.active_tool_name:
                detected_tool = self._semantic_route(user_input)
                if detected_tool:
                    self.active_tool_name = detected_tool
                    print(f"🎯 Router Switch: {self.active_tool_name}")

            # ------------------------------------------------------------------
            # STEP 2: GENERAL CHAT 
            # ------------------------------------------------------------------
            if not self.active_tool_name:
                messages = [
                    SystemMessage(content=self.base_prompt),
                    HumanMessage(content=user_input)
                ]
                # Ensure LLM invocation is handled correctly (invoke is usually sync in LangChain, ainvoke is async)
                # If using standard LangChain:
                response = self.llm.invoke(messages) 
                return response.content

            # ------------------------------------------------------------------
            # STEP 3: SLOT FILLING 
            # ------------------------------------------------------------------
            tool_obj = self.tools[self.active_tool_name]
            print(f"🛠️  Active Tool: {tool_obj.name}")

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
            content = response.content.strip()

            # ------------------------------------------------------------------
            # STEP 4: EXECUTION CHECK
            # ------------------------------------------------------------------
            tool_call = self._extract_json(content)
            
            if tool_call and "arguments" in tool_call:
                print(f"🚀 Executing: {tool_obj.name} with {tool_call['arguments']}")
                try:
                    # 2. CHANGE: Access the 'function' attribute directly
                    func = tool_obj.function
                    
                    # 3. CHANGE: Handle Async execution
                    if inspect.iscoroutinefunction(func):
                        result = await func(**tool_call["arguments"])
                    else:
                        result = func(**tool_call["arguments"])

                except Exception as e:
                    result = f"❌ Error: {e}"
                    print(result) # Print stack trace for debugging if needed

                # Reset state after execution
                self.history = []
                self.active_tool_name = None
                return result

            # ------------------------------------------------------------------
            # STEP 5: CONTINUE DIALOGUE
            # ------------------------------------------------------------------
            self.history.append(HumanMessage(content=user_input))
            self.history.append(AIMessage(content=content))
            return content