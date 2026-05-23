import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
OUT_LOG = ROOT / "streamlit.out.log"
ERR_LOG = ROOT / "streamlit.err.log"


def main() -> None:
    with OUT_LOG.open("ab", buffering=0) as stdout, ERR_LOG.open("ab", buffering=0) as stderr:
        process = subprocess.Popen(
            [
                PYTHON,
                "-m",
                "streamlit",
                "run",
                "app.py",
                "--server.headless",
                "true",
                "--server.port",
                "8501",
                "--browser.gatherUsageStats",
                "false",
            ],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
        )
        while process.poll() is None:
            time.sleep(10)


if __name__ == "__main__":
    main()
