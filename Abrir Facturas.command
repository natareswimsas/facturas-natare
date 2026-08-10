#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if ! command -v python3 >/dev/null 2>&1; then
  osascript -e 'display dialog "No encontré Python 3 instalado. Instálalo primero y vuelve a intentar." buttons {"OK"} default button "OK"'
  exit 1
fi

if ! python3 -c "import pypdf" >/dev/null 2>&1; then
  osascript -e 'display dialog "Voy a instalar la librería necesaria pypdf. Esto puede tardar un momento." buttons {"OK"} default button "OK"'
  python3 -m pip install -r requirements.txt
fi

python3 invoice_renamer.py input --output output

open "$DIR/output"
osascript -e 'display dialog "Proceso terminado. Revisa la carpeta output." buttons {"OK"} default button "OK"'
