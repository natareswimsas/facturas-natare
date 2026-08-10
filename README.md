# Proyecto: Automatizador de facturas PDF

Este proyecto renombra facturas automáticamente con este formato:

`AAAA-MM - PROVEEDOR - TIPO - NUMERO.pdf`

Ejemplo:

`2026-02 - MARQUIDEAS - FACT - FE2620.pdf`

## Requisitos

Instala Python 3 y luego ejecuta:

```bash
pip install -r requirements.txt
```

## Cómo usar

1. Copia tus PDFs dentro de la carpeta `input/`
2. Abre terminal dentro de esta carpeta del proyecto
3. Ejecuta:

```bash
python invoice_renamer.py input --output output
```

## Qué genera

Dentro de `output/` vas a encontrar:

- `renamed/` → PDFs renombrados
- `invoice_index.csv` → índice de control
- `facturas_renombradas.zip` → ZIP final

## Recomendación

Usa siempre esta estructura:

- `input/` → archivos nuevos del lote
- `output/` → resultados del lote

Cuando termines un lote, vacía `input/` antes del siguiente.

## Proveedores configurados

Actualmente el script reconoce, entre otros:

- F2X
- Envioclick
- Wompi
- Addi
- Marquideas
- Mar Antiguo
- Surtidora de Herrajes
- Swimmer
- Produvarios
- DHL
- Distracom
- Texaco Envigado
- Sodimac
- Eliot
- Insumos
- Restrepo Cardona
- IKSO
- Cámara de Comercio Medellín
- Comercializadora Giraldo Z
