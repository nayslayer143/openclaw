"""
Shared pytest configuration.

Sets CLAWMSON_DB_PATH once before any test module is imported, so all
test files share the same DB and the schema is created (via clawmson_db
module-level _init_db call) before clean_db fixtures try to DELETE FROM it.
"""
import os
import sys
import tempfile
from pathlib import Path

# Set the shared DB path exactly once — before test modules override it.
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.environ["CLAWMSON_DB_PATH"] = _db_path

# Make scripts/ importable from all test files.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# Import clawmson_db here so its module-level _init_db() runs against the
# correct DB path before any test file re-assigns CLAWMSON_DB_PATH.
import clawmson_db  # noqa: F401  — side-effect: creates schema
