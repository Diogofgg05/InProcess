"""Deterministic, CPU-bound reference task for independent benchmark trials.

Pure Python integer arithmetic; identical iterations should produce the
same checksum on each platform. It does not claim identical OS scheduling,
CPU microarchitecture, or power consumption across Windows and Linux.
"""
import argparse


def run(iterations:int) -> int:
    if type(iterations) is not int or not 1000<=iterations<=100_000_000:
        raise ValueError("Use 1000–100000000 iterações.")
    value=0x12345678
    for i in range(iterations):
        value=((value^i)*1664525+1013904223)&0xFFFFFFFF
    return value


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--iterations",type=int,default=3_000_000)
    args=parser.parse_args()
    print(f"{run(args.iterations):08x}")


if __name__=="__main__":
    main()
