# Versión tipo app para Mac

## Qué hace
Solo haces doble clic en `Abrir Facturas.command` y el sistema:

1. revisa si Python 3 existe
2. instala `pypdf` si hace falta
3. procesa los PDFs de la carpeta `input`
4. genera:
   - `output/renamed/`
   - `output/invoice_index.csv`
   - `output/facturas_renombradas.zip`

## Cómo usarlo

### 1. Copia tus PDFs a:
`input/`

### 2. Haz doble clic en:
`Abrir Facturas.command`

### 3. Si macOS bloquea el archivo:
- clic derecho sobre `Abrir Facturas.command`
- elige **Abrir**
- confirma **Abrir**

## Resultado
Se abrirá automáticamente la carpeta `output`.

## Nota
Si quieres algo todavía más visual, este mismo archivo se puede convertir en una app con Automator o Script Editor.
