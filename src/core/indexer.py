import chromadb
from sentence_transformers import SentenceTransformer

# Initialize the model once for indexing
embedder = SentenceTransformer("all-MiniLM-L6-v2")

def index_tools_to_db(tools_list, db_path="./market_agent_db"):
    """
    Takes a list of tool INSTANCES or DEFINITIONS and stores them in ChromaDB.
    """
    # 1. Initialize persistent client
    client = chromadb.PersistentClient(path=db_path)
    
    # 2. Get or Create Collection (delete old one to ensure freshness if needed)
    try:
        client.delete_collection(name="agent_tools")
    except ValueError:
        pass # Collection didn't exist
        
    collection = client.create_collection(name="agent_tools")

    ids = []
    documents = [] # The raw trigger text
    embeddings = [] # The vector representation
    metadatas = [] # Extra info like tool name

    print("🔌 Indexing tools into Vector DB...")

    for tool in tools_list:
        # Determine the trigger text
        trigger_text = getattr(tool, "trigger", None) or tool.description or tool.name
        
        if trigger_text:
            print(f"   - Embedding '{tool.name}'...")
            # Generate embedding
            vector = embedder.encode(trigger_text).tolist()
            
            ids.append(tool.name)
            documents.append(trigger_text)
            embeddings.append(vector)
            metadatas.append({"tool_name": tool.name})

    # 3. Add to Chroma
    if ids:
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        print(f"✅ Successfully indexed {len(ids)} tools to {db_path}")
    else:
        print("⚠️ No tools found to index.")

# --- usage example ---
# You would call this ideally OUTSIDE the agent class, or in a startup script
# dummy_id = "init_indexing" 
# all_tools = [trading_bot_factory(dummy_id), ...] 
# index_tools_to_db(all_tools)