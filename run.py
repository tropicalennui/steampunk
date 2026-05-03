import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn
from init import ensure_gandalf_initialised

if __name__ == "__main__":
    ensure_gandalf_initialised()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
