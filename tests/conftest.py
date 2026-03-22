import sys
from pathlib import Path

# Add scripts/ to path so test files can import from scripts/ without sys.path hacks
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
