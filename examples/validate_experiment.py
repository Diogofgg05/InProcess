"""Evaluate two genuinely separate acquisition manifests; no automatic certification."""
import argparse
import json
from pathlib import Path
from expecto_process_manager.physics.experimental_validation import evaluate_sessions

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training',type=Path,required=True)
    parser.add_argument('--validation',type=Path,required=True)
    parser.add_argument('--ambient-c',type=float)
    parser.add_argument('--allow-electrical-proxy',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=evaluate_sessions(args.training,args.validation,ambient_c=args.ambient_c,
                             allow_electrical_proxy=args.allow_electrical_proxy)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(result['status']); print('\n'.join(result['reasons']))
