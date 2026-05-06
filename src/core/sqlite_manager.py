"""
SQLite Temp Database Lifecycle Manager
=======================================
Single Responsibility: Create, connect, and destroy per-session SQLite databases.
Does NOT know about Excel, schemas, or queries — pure DB lifecycle.
"""

import os
import sqlite3
import threading
from typing import Dict, Optional


# Thread-safe registry of active connections
_lock = threading.Lock()
_connections: Dict[str, sqlite3.Connection] = {}

# Base directory for temp DB files
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cache", "excel_agent")


def _db_path(session_id: str) -> str:
    """Return the file path for a session's SQLite database."""
    return os.path.join(_DB_DIR, f"{session_id}.db")


def create_temp_db(session_id: str) -> sqlite3.Connection:
    """
    Create a new temporary SQLite database for the given session.
    
    Args:
        session_id: Unique session identifier (e.g. "{user_id}_{conversation_id}")
        
    Returns:
        sqlite3.Connection to the new database
        
    Raises:
        ValueError: If a database already exists for this session
    """
    with _lock:
        if session_id in _connections:
            raise ValueError(f"Database already exists for session: {session_id}")

        os.makedirs(_DB_DIR, exist_ok=True)
        db_file = _db_path(session_id)

        conn = sqlite3.connect(db_file, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Dict-like row access
        conn.execute("PRAGMA journal_mode=WAL;")  # Better concurrent reads

        _connections[session_id] = conn
        print(f"📂 Created temp DB: {db_file}")
        return conn


def get_connection(session_id: str) -> sqlite3.Connection:
    """
    Retrieve an existing connection for a session.
    
    Args:
        session_id: Unique session identifier
        
    Returns:
        sqlite3.Connection
        
    Raises:
        KeyError: If no database exists for this session
    """
    with _lock:
        if session_id not in _connections:
            raise KeyError(f"No database found for session: {session_id}")
        return _connections[session_id]


def destroy_temp_db(session_id: str) -> None:
    """
    Close connection and delete the database file for a session.
    
    Args:
        session_id: Unique session identifier
    """
    with _lock:
        conn = _connections.pop(session_id, None)

    if conn:
        try:
            conn.close()
        except Exception:
            pass

    db_file = _db_path(session_id)
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
            print(f"🗑️ Destroyed temp DB: {db_file}")
        except OSError as e:
            print(f"⚠️ Failed to delete DB file {db_file}: {e}")

    # Also clean up WAL/SHM files if they exist
    for suffix in ("-wal", "-shm"):
        wal_file = db_file + suffix
        if os.path.exists(wal_file):
            try:
                os.remove(wal_file)
            except OSError:
                pass


def has_session(session_id: str) -> bool:
    """Check if a session's database exists."""
    with _lock:
        return session_id in _connections
