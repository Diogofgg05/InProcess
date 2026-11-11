"""Run the ten physical hardware experiments without Qt or hardware access."""
import argparse
from pathlib import Path
from expecto_process_manager.reporting.physical_suite import generate_physical_suite

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('reports/physical-lab-5'))
    args=parser.parse_args()
    print(generate_physical_suite(args.output).resolve())
