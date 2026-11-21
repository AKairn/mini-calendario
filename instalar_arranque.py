"""Crea (o quita) el acceso directo que abre el mini calendario al iniciar sesión en Windows.

Uso, dentro de la carpeta del proyecto: en Anaconda Prompt, tal cual; en PowerShell o cmd,
cambiando `python` por la ruta completa de python.exe (la que da `where python` en Anaconda Prompt):
    python instalar_arranque.py           # instala
    python instalar_arranque.py --quitar  # desinstala
    python instalar_arranque.py --ver     # muestra qué hay instalado

El acceso directo apunta al pythonw.exe del Python con el que ejecutes este script
(pythonw = sin ventana de consola). Como el calendario solo usa la librería estándar,
vale el Python base de Anaconda: no hay que activar ningún entorno.
"""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("calendario.pyw").resolve()
NOMBRE_ACCESO = "Mini calendario.lnk"


def carpeta_inicio() -> Path:
    # Equivale a escribir shell:startup en Ejecutar (Win+R).
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def instalar() -> None:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        sys.exit(f"No encuentro {pythonw}. Ejecuta este script con el python.exe de Anaconda.")
    acceso = carpeta_inicio() / NOMBRE_ACCESO
    # Se crea el .lnk con el objeto COM WScript.Shell a través de PowerShell (sin dependencias extra).
    comando = (
        f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut("{acceso}"); '
        f'$s.TargetPath = "{pythonw}"; '
        f"$s.Arguments = '\"{SCRIPT}\"'; "
        f'$s.WorkingDirectory = "{SCRIPT.parent}"; '
        f'$s.Description = "Mini calendario"; '
        f"$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", comando], check=True)
    print(f"Acceso directo creado:\n  {acceso}\n  -> {pythonw} \"{SCRIPT}\"")
    print("Pruébalo haciendo doble clic en el acceso directo antes de reiniciar.")


def quitar() -> None:
    acceso = carpeta_inicio() / NOMBRE_ACCESO
    if acceso.exists():
        acceso.unlink()
        print(f"Eliminado: {acceso}")
    else:
        print("No había ningún acceso directo instalado.")


def ver() -> None:
    acceso = carpeta_inicio() / NOMBRE_ACCESO
    print(f"{'Instalado' if acceso.exists() else 'No instalado'}: {acceso}")


if __name__ == "__main__":
    if sys.platform != "win32":
        sys.exit("Este script es solo para Windows.")
    opcion = sys.argv[1] if len(sys.argv) > 1 else ""
    {"--quitar": quitar, "--ver": ver, "": instalar}.get(opcion, lambda: sys.exit(__doc__))()
