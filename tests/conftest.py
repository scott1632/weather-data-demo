import os
import sys

# ingestion/ is a plain script directory, not an installed package, so make
# it importable as `import ingest` without needing setup.py/pyproject.toml.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingestion"))
