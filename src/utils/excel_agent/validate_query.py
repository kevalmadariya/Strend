"""
Query Validator
================
Single Responsibility: Validate SQL queries for safety before execution.
Whitelist allowed operations, blacklist dangerous patterns.
Does NOT execute queries — that's query_executor's job.
"""

import re
from typing import Tuple, Optional


# Allowed SQL statement prefixes (case-insensitive)
_ALLOWED_PREFIXES = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "ALTER TABLE",
    "CREATE TABLE",
)

# Dangerous patterns that should NEVER be allowed
_BLACKLIST_PATTERNS = [
    r"\bDROP\s+DATABASE\b",
    r"\bDROP\s+TABLE\b",
    r"\bDROP\s+INDEX\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
    r"\bCREATE\s+TRIGGER\b",
    r"\bCREATE\s+INDEX\b",
    r"\bVACUUM\b",
    r"\bREINDEX\b",
    r"\bANALYZE\b",
    r"\bEXPLAIN\b",
    # Block PRAGMA except table_info (which we use internally)
    r"\bPRAGMA\s+(?!table_info\b)\w+",
]

# Compiled blacklist for performance
_COMPILED_BLACKLIST = [re.compile(p, re.IGNORECASE) for p in _BLACKLIST_PATTERNS]


def validate_query(sql: str) -> Tuple[bool, Optional[str]]:
    """
    Validate an SQL query for safety.
    
    Args:
        sql: The SQL string to validate
        
    Returns:
        (True, None) if safe
        (False, "error reason") if dangerous
    """
    if not sql or not isinstance(sql, str):
        return False, "Empty or invalid SQL query"

    stripped = sql.strip()
    if not stripped:
        return False, "Empty SQL query"

    # ── Check for multi-statement injection (semicolons mid-query) ──
    # Allow trailing semicolon but not multiple statements
    without_trailing = stripped.rstrip(";").strip()
    if ";" in without_trailing:
        return False, "Multi-statement queries are not allowed (potential SQL injection)"

    # ── Whitelist check ──
    upper = stripped.upper().lstrip()
    if not any(upper.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
        return False, (
            f"Statement type not allowed. "
            f"Allowed: {', '.join(_ALLOWED_PREFIXES)}. "
            f"Got: '{stripped[:30]}...'"
        )

    # ── ALTER TABLE: only allow ADD COLUMN ──
    if upper.startswith("ALTER TABLE"):
        if not re.search(r"\bADD\s+(COLUMN\s+)?\w+", upper):
            return False, "ALTER TABLE only supports ADD COLUMN operations"

    # ── Blacklist check ──
    for pattern in _COMPILED_BLACKLIST:
        match = pattern.search(stripped)
        if match:
            return False, f"Blocked dangerous pattern: '{match.group()}'"

    return True, None


def sanitize_table_name(name: str) -> str:
    """
    Ensure a table name contains only safe characters.
    
    Args:
        name: Raw table name
        
    Returns:
        Sanitized table name (alphanumeric + underscores only)
        
    Raises:
        ValueError: If name is empty after sanitization
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")

    if not sanitized:
        raise ValueError(f"Table name '{name}' is invalid after sanitization")

    # Ensure it doesn't start with a digit
    if sanitized[0].isdigit():
        sanitized = "t_" + sanitized

    return sanitized


def validate_column_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a column name for safety.
    
    Returns:
        (True, None) if valid
        (False, "error reason") if invalid
    """
    if not name or not isinstance(name, str):
        return False, "Empty or invalid column name"

    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name.strip()):
        return False, f"Column name '{name}' contains invalid characters"

    return True, None
