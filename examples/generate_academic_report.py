"""Generate the actual 21-section report without launching Qt or probing hardware."""
import argparse
from pathlib import Path

from expecto_process_manager.reporting.academic import generate_academic_report


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root/"reports"/"academic-final.html")
    parser.add_argument("--hardware-file", type=Path, default=root/"data"/"hardware-detected.json",
                        help="Inventário prévio opcional; nenhuma recolha de hardware é executada.")
    args = parser.parse_args()
    path = generate_academic_report(args.output, args.hardware_file)
    print(f"Relatório gerado e verificações A–I aprovadas: {path}")
    print("8 experiências SIMULATED; 21 secções; HTML/SVG offline; sem medições físicas de potência/temperatura.")


if __name__ == "__main__":
    main()
