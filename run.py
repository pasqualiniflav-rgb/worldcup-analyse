"""Point d'entrée unique : Excel -> base -> rapports.

    python run.py

Enchaîne l'ingestion du classeur de saisie puis la génération de
tous les rapports HTML. C'est la commande à donner au staff.
"""
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent / "scripts"


def step(name, args):
    print(f"\n=== {name} ===")
    subprocess.run([sys.executable, str(SCRIPTS / args)], check=True, cwd=SCRIPTS)


if __name__ == "__main__":
    step("1/2 Ingestion Excel -> base", "ingest.py")
    step("2/2 Génération des rapports", "report.py")
    print("\n✔ Terminé. Ouvrez reports/index.html")
