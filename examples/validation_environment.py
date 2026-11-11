"""Record the actual interpreter and dependency versions beside test artifacts."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform

import psutil
import PySide6


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(platform=platform.platform(),python=platform.python_version(),
        psutil=psutil.__version__,qt=PySide6.__version__,recorded_at=datetime.now(timezone.utc).isoformat()),
        indent=2),encoding='utf-8')
