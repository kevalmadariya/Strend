import chromadb
from sentence_transformers import SentenceTransformer
import os

class ToolVectorDB:
    def __init__(self, base_path="./vector_db", agent_name: str = None):
        assert agent_name, "agent_name is required for ToolVectorDB"

        self.agent_name = agent_name
        self.db_path = os.path.join(base_path, agent_name)

        print(f"📦 Initializing Vector DB for agent: {agent_name}")
        print(f"📂 DB Path: {self.db_path}")

        os.makedirs(self.db_path, exist_ok=True)

        self.client = chromadb.PersistentClient(path=self.db_path)
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

        self.collection = self.client.get_or_create_collection(
            name="agent_tools"
        )

        print(f"✅ Vector DB ready. Current tool count: {self.collection.count()}")

    def sync_agent_tools(self, tools: dict):
        print("/////////////////////////")
        print("TOOLS RECEIVED:", tools)

        print(f"\n🔄 Syncing tools for agent '{self.agent_name}'")
        print(f"🛠️ Tools in code: {list(tools.keys())}")

        # Get all existing IDs in DB
        existing = self.collection.get()
        existing_ids = set(existing["ids"]) if existing["ids"] else set()

        print(f"📚 Existing vector IDs in DB: {existing_ids}")

        new_ids = []
        new_embeddings = []
        new_documents = []

        for tool_name, tool in tools.items():

            # 🔹 Normalize triggers
            triggers = []

            if hasattr(tool, "triggers") and tool.triggers:
                triggers = tool.triggers
            elif hasattr(tool, "trigger") and tool.trigger:
                triggers = [tool.trigger]
            elif tool.description:
                triggers = [tool.description]
            else:
                triggers = [tool.name]

            print(f"\n🧩 Tool '{tool_name}' triggers:")
            for i, t in enumerate(triggers):
                print(f"   [{i}] {t}")

            # 🔹 Create embedding PER trigger
            for idx, trigger_text in enumerate(triggers):
                vector_id = f"{tool_name}::{idx}"

                if vector_id in existing_ids:
                    print(f"   ⏭️ Skipping existing embedding: {vector_id}")
                    continue

                print(f"   🔹 Embedding [{vector_id}] → '{trigger_text}'")

                vector = self.embedder.encode(trigger_text).tolist()

                new_ids.append(vector_id)
                new_embeddings.append(vector)
                new_documents.append(trigger_text)

        if not new_ids:
            print("✅ No new trigger embeddings to add.")
            return

        self.collection.add(
            ids=new_ids,
            embeddings=new_embeddings,
            documents=new_documents,
            metadatas=[
                {"tool_name": vid.split("::")[0]} for vid in new_ids
            ]
        )

        print(f"\n🚀 Added {len(new_ids)} new trigger embeddings to Vector DB")

    def search(self, query: str, similarity_threshold: float = 0.3):
        """
        Semantic search using COSINE SIMILARITY.
        Returns tool name only if similarity >= threshold.
        """
        print(f"\n🔍 Semantic search query: '{query}'")

        # # ---- 0️⃣ Guard against greetings / junk
        # small_talk = {"hi", "hii", "hello", "hey", "thanks", "thank you", "ok"}
        # if query.strip().lower() in small_talk:
        #     print("💬 Small talk detected — skipping tool routing")
        #     return None

        # ---- 1️⃣ Encode query
        query_vec = self.embedder.encode(query, normalize_embeddings=True).tolist()

        # ---- 2️⃣ Query Chroma
        results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=1
        )

        if not results or not results["ids"] or not results["ids"][0]:
            print("❌ No results from vector DB")
            return None

        result_id = results["ids"][0][0]
        tool_name = result_id.split("::")[0]

        distance = results["distances"][0][0]
        cosine_similarity = 1 - distance

        print(
            f"🏆 Best match: {tool_name} | "
            f"Cosine Similarity: {cosine_similarity:.4f}"
        )

        # ---- 3️⃣ Threshold check
        if cosine_similarity < similarity_threshold:
            print(
                f"🚫 Similarity {cosine_similarity:.4f} "
                f"< threshold {similarity_threshold}"
            )
            return None

        print(f"🎯 Tool accepted: {tool_name}")
        return tool_name
