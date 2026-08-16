from __future__ import annotations

import argparse
import csv
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from pypdf import PdfReader


# =========================================================
# MODELOS
# =========================================================

@dataclass
class InvoiceInfo:
    vendor: str
    doc_type: str
    number: str
    invoice_date: str
    confidence: str
    original_name: str
    renamed_name: str


@dataclass
class VendorRule:
    name: str
    detect: Callable[[str], bool]
    number_patterns: list[tuple[str, str]]
    doc_type_patterns: list[tuple[str, str]]


# =========================================================
# UTILIDADES
# =========================================================

def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def sanitize_filename(value: str) -> str:
    value = value.strip().replace("/", "-")
    value = re.sub(r"\s+", " ", value)
    return re.sub(r'[<>:"\\|?*]', "", value)


def own_company_keyword(own_company: str) -> str:
    """
    De 'NATARE SWIM SAS' saca 'natare' — la palabra distintiva que
    permite reconocer al comprador dentro del PDF y no confundirlo
    con el proveedor.
    """

    name = own_company.upper().strip()
    name = re.sub(r"\b(S\.?A\.?S\.?|LTDA\.?|LTD\.?|S\.?A\.?)$", "", name).strip()

    words = name.split()

    return words[0].lower() if words else ""


def clean_number(value: str) -> str:
    return (
        value.strip()
        .replace(" ", "")
        .replace("–", "-")
        .replace("—", "-")
    )


def clean_vendor_name(value: str) -> str:
    value = value.upper().strip()

    replacements = {
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "Ñ": "N",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    value = value.replace(".", "")
    value = value.replace(",", "")
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" -")

    return sanitize_filename(value)


# =========================================================
# PDF
# =========================================================

def extract_text_from_pdf(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []

    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")

    return "\n".join(parts)


# =========================================================
# FECHA FACTURA
# =========================================================

def extract_invoice_date(text: str, fallback_path: Path) -> str:
    """
    Obtiene SOLO la fecha real de factura.
    Ignora resolución DIAN, vigencias, autorizaciones, etc.
    """

    priority_patterns = [
        r"Fecha\s+y\s+hora\s+Factura.*?(\d{2})/(\d{2})/(20\d{2})",
        r"Fecha\s+Factura[:\s]+(\d{2})/(\d{2})/(20\d{2})",
        r"Fecha\s+de\s+emisi[oó]n[:\s]+(20\d{2})-(\d{2})-(\d{2})",
        r"Fecha\s+Emisi[oó]n[:\s]+(\d{2})-(\d{2})-(20\d{2})",
        r"Fecha\s+de\s+Documento[:\s]+(\d{2})/(\d{2})/(20\d{2})",
        r"Fecha\s+Documento[:\s]+(\d{2})/(\d{2})/(20\d{2})",
        r"Generación\s*(\d{2})/(\d{2})/(20\d{2})",
        r"Expedición\s*(\d{2})/(\d{2})/(20\d{2})",
        r"Fecha\s+y\s*Hora\s+de\s+Generación[:\s]+(20\d{2})-(\d{2})-(\d{2})",
        r"Fecha\s+Nota[:\s]+(\d{2})\.(\d{2})\.(20\d{2})",
        r"Fecha\s*:\s*(20\d{2})/(\d{1,2})/(\d{1,2})",
        r"Fecha\s*:\s*(\d{1,2})/(\d{1,2})/(20\d{2})",
        r"Fecha\s+de\s+Expedici[oó]n[:\s]+(20\d{2})/(\d{2})/(\d{2})",
        r"Fecha\s+de\s+Expedici[oó]n[:\s]+(\d{2})/(\d{2})/(20\d{2})",
        r"Fecha\s+Factura[:\s]+(20\d{2})/(\d{2})/(\d{2})",
    ]

    for pattern in priority_patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            groups = match.groups()

            if len(groups[0]) == 4:
                year, month, day = (
                    groups[0],
                    groups[1].zfill(2),
                    groups[2].zfill(2),
                )
            else:
                day, month, year = (
                    groups[0].zfill(2),
                    groups[1].zfill(2),
                    groups[2],
                )

            return f"{year}-{month}-{day}"

    ignore_words = [
        "resoluci",
        "vigencia",
        "autorizaci",
        "numeracion",
        "numeración",
        "rango",
        "desde",
        "hasta",
        "dian",
    ]

    generic_patterns = [
        r"(\d{2})/(\d{2})/(20\d{2})",
        r"(\d{2})-(\d{2})-(20\d{2})",
        r"(20\d{2})-(\d{2})-(\d{2})",
        r"(20\d{2})/(\d{2})/(\d{2})",
        r"(\d{2})\.(\d{2})\.(20\d{2})",
    ]

    for pattern in generic_patterns:
        for match in re.finditer(pattern, text):

            context = text[max(0, match.start() - 90):match.start()].lower()

            if any(word in context for word in ignore_words):
                continue

            groups = match.groups()

            if len(groups[0]) == 4:
                year, month, day = (
                    groups[0],
                    groups[1].zfill(2),
                    groups[2].zfill(2),
                )
            else:
                day, month, year = (
                    groups[0].zfill(2),
                    groups[1].zfill(2),
                    groups[2],
                )

            return f"{year}-{month}-{day}"

    from datetime import datetime

    dt = datetime.fromtimestamp(fallback_path.stat().st_mtime)

    return dt.strftime("%Y-%m-%d")


# =========================================================
# DOCUMENTO
# =========================================================

def detect_doc_type(
    text: str,
    vendor_rule: Optional[VendorRule] = None
) -> str:

    if vendor_rule:
        for pattern, label in vendor_rule.doc_type_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return label

    if re.search(r"nota\s+cr[eé]dito|nota\s+credito", text, re.IGNORECASE):
        return "NC"

    if re.search(
        r"doc\.\s*equivalente\s*peajes|peajes\s+electr[oó]nico",
        text,
        re.IGNORECASE
    ):
        return "PEAJE"

    return "FACT"


# =========================================================
# NUMERO FACTURA
# =========================================================

def extract_number(
    text: str,
    vendor_rule: VendorRule
) -> Optional[str]:

    for pattern, group_name in vendor_rule.number_patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return clean_number(match.group(group_name))

    return None


def fallback_invoice_number(text: str) -> str:
    """
    Detecta número aunque el proveedor sea nuevo.
    """

    patterns = [
        r"Factura\s+Electr[oó]nica\s+de\s+Venta\s*(?:No\.?|N°|Nº)?\s*[:\-]?\s*(?P<num>[A-Z0-9]{1,10}[-\s]?\d+)",
        r"No\.\s*(?P<num>[A-Z0-9]{1,10}[-\s]?\d+)",
        r"N[°º]\s*(?P<num>[A-Z0-9]{1,10}[-\s]?\d+)",
        r"Nro\.?\s*Doc\.?\s*[:\-]?\s*(?P<num>[A-Z0-9]{1,10}[-\s]?\d+)",
        r"Tiquete\s*[:\-]\s*(?P<num>[A-Z0-9]{1,10}[-\s]?\d+)",
        r"Documento\s*(?:No\.?|N°|Nº)?\s*[:\-]?\s*(?P<num>[A-Z0-9]{1,10}[-\s]?\d+)",
        r"Nota\s+Cr[eé]dito.*?(?P<num>NC[-\s]?\d+)",
        r"NOTA\s+CREDITO\s+ELECTR[ÓO]NICA\s*(?P<num>\d+)",
        r"FACTURA\s+ELECTR[ÓO]NICA\s+DE\s+VENTA\s*(?P<num>\d{6,})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return clean_number(match.group("num"))

    return "NUMERO PENDIENTE"


# =========================================================
# PROVEEDOR AUTOMATICO
# =========================================================

def fallback_vendor_name(raw_text: str, own_company: str = "NATARE SWIM SAS") -> str:
    """
    Detecta proveedor automáticamente aunque sea nuevo.
    """

    own_keyword = own_company_keyword(own_company)

    lines = [
        line.strip()
        for line in raw_text.splitlines()
        if line.strip()
    ]

    text = normalize_spaces(raw_text)

    skip_words = [
        "factura",
        "electrónica",
        "electronica",
        "nota crédito",
        "nota credito",
        "cliente",
        "adquiriente",
        "adquirente",
        "fecha",
        "resolución",
        "resolucion",
        "dian",
        "cufe",
        "cude",
        "total",
        "original",
        "representación",
        "representacion",
        "nro",
        "no.",
        "n°",
        "proveedor tecnol",
        "software",
        "solucion tecnol",
        "solución tecnol",
        "operador tecnol",
        "operador de facturaci",
    ]

    if own_keyword:
        skip_words.append(own_keyword)

    blocklist_names = [
        "alegra",
        "loggro",
        "siigo",
        "worldoffice",
        "world office",
        "factus",
        "helisa",
        "a2 softway",
    ]

    # Cuando el nombre de la empresa queda partido en dos líneas del PDF
    # (ej. "SURTIDORA DE HERRAJES" / "SAS"), se une con la línea anterior.
    suffix_only = re.compile(r"^(S\.?A\.?S\.?|SA|LTDA\.?|LTD\.?)$", re.IGNORECASE)

    merged_lines: list[str] = []

    for line in lines:

        if merged_lines and suffix_only.match(line):
            merged_lines[-1] = f"{merged_lines[-1]} {line}"
        else:
            merged_lines.append(line)

    lines = merged_lines

    # 1) primeras líneas
    for line in lines[:20]:

        low = line.lower()

        if any(word in low for word in skip_words):
            continue

        if any(word in low for word in blocklist_names):
            continue

        if re.search(
            r"\b(?:S\.?A\.?S|SAS|S\.?A\.?|SA|LTDA|LTD|COLOMBIA)\b",
            line,
            re.IGNORECASE
        ):
            return clean_vendor_name(line)

    # 2) antes de NIT (línea por línea, para no cruzar renglones distintos)
    patterns = [
        r"([A-ZÁÉÍÓÚÑ0-9 &\.\-]+(?:S\.?A\.?S|SAS|S\.?A\.?|SA|LTDA|LTD))\s+NIT",
        r"([A-ZÁÉÍÓÚÑ0-9 &\.\-]+)\s+NIT[:\s\.]+[0-9\.\-]+",
        r"Raz[oó]n\s*social(?:/Nombre)?[:\s]+([A-ZÁÉÍÓÚÑ0-9 &\.\-]+)",
        r"Emisor[:\s\-]+([A-ZÁÉÍÓÚÑ0-9 &\.\-]+)",
    ]

    for line in lines[:40]:

        low = line.lower()

        if own_keyword and own_keyword in low:
            continue

        if any(word in low for word in skip_words + blocklist_names):
            continue

        for pattern in patterns:

            match = re.search(pattern, line, re.IGNORECASE)

            if not match:
                continue

            vendor = match.group(1).strip()

            if len(vendor) < 4:
                continue

            return clean_vendor_name(vendor)

    # 3) fallback primeras líneas
    for line in lines[:15]:

        low = line.lower()

        if any(word in low for word in skip_words):
            continue

        if own_keyword and own_keyword in low:
            continue

        if len(line) >= 5:
            return clean_vendor_name(line)

    return "PROVEEDOR PENDIENTE"


# =========================================================
# REGLAS CONOCIDAS
# =========================================================

VENDOR_RULES: list[VendorRule] = [

    VendorRule(
        name="F2X SAS",
        detect=lambda t: "f2x s.a.s" in t.lower(),
        number_patterns=[
            (r"(?P<num>DEFL[-\s]?\d+)", "num"),
            (r"(?P<num>FLYP[-\s]?\d+)", "num"),
            (r"(?P<num>FEFL[-\s]?\d+)", "num"),
        ],
        doc_type_patterns=[
            (r"Doc\.\s*Equivalente\s*Peajes", "PEAJE"),
            (r"nota\s+cr[eé]dito", "NC"),
            (r"factura", "FACT"),
        ],
    ),

    VendorRule(
        name="ENVIOCLICK",
        detect=lambda t: "envioclick" in t.lower(),
        number_patterns=[
            (r"No\.\s*FE\s*(?P<num>\d+)", "num")
        ],
        doc_type_patterns=[
            (r"factura", "FACT")
        ],
    ),

    VendorRule(
        name="WOMPI",
        detect=lambda t: "wompi" in t.lower(),
        number_patterns=[
            (r"(?P<num>WO\d+)", "num")
        ],
        doc_type_patterns=[
            (r"factura", "FACT")
        ],
    ),

    VendorRule(
        name="ADDI",
        detect=lambda t:
            "adelante soluciones financieras" in t.lower()
            or "documento no. addi" in t.lower(),
        number_patterns=[
            (r"Documento\s+No\.\s*(?P<num>ADDI\d+)", "num")
        ],
        doc_type_patterns=[
            (r"factura", "FACT")
        ],
    ),

    VendorRule(
        name="LA LOCURA DEL HOGAR SAS",
        detect=lambda t: "la locura del hogar" in t.lower(),
        number_patterns=[
            (r"(?P<num>FEL\d{4,})", "num"),
        ],
        doc_type_patterns=[],
    ),

    VendorRule(
        name="RIOTO COLOMBIA S.A.S",
        detect=lambda t: "rioto colombia" in t.lower(),
        number_patterns=[
            (r"(?P<num>FEVR\d+)", "num"),
        ],
        doc_type_patterns=[],
    ),

    VendorRule(
        name="MANUFACTURAS ELIOT",
        detect=lambda t:
            "eliot" in t.lower()
            or "tekstelas" in t.lower()
            or "8600004526" in re.sub(r"[.,\-\s]", "", t),
        number_patterns=[
            (r"FACTURA\s+ELECTR[ÓO]NICA\s+DE\s+VENTA\s*(?P<num>\d{6,})", "num"),
            (r"NOTA\s+CREDITO\s+ELECTR[ÓO]NICA\s*(?P<num>\d+)", "num"),
        ],
        doc_type_patterns=[
            (r"nota\s+cr[eé]dito", "NC"),
            (r"factura", "FACT"),
        ],
    ),

    VendorRule(
        name="FRISBY SAS",
        detect=lambda t: "frisby" in t.lower(),
        number_patterns=[
            (r"venta:\s*(?P<num>[A-Z]{1,3}\d+)", "num"),
        ],
        doc_type_patterns=[],
    ),

    VendorRule(
        name="EL PASO TEX-MEX CITY PLAZA",
        detect=lambda t: "tex-mex" in t.lower() or "tex mex" in t.lower(),
        number_patterns=[],
        doc_type_patterns=[],
    ),

    VendorRule(
        name="SUSHI MARKET",
        detect=lambda t: "sushimarket" in t.lower() or "sushi market" in t.lower(),
        number_patterns=[
            (r"POS:\s*(?P<num>CT\s?\d+)", "num"),
        ],
        doc_type_patterns=[],
    ),

    VendorRule(
        name="PRODUVARIOS",
        detect=lambda t: "produvarios" in t.lower(),
        number_patterns=[],
        doc_type_patterns=[],
    ),

    VendorRule(
        name="COMPAÑIA DE ALIMENTOS COLOMBIANOS CALCO S.A.",
        detect=lambda t: "calco" in t.lower(),
        number_patterns=[
            (r"(?P<num>341E\s*-?\s*\d+)", "num"),
        ],
        doc_type_patterns=[],
    ),

    VendorRule(
        name="SURTIDORA DE HERRAJES SAS",
        detect=lambda t: "surtidora de herrajes" in t.lower(),
        number_patterns=[
            (r"No\.\s*(?P<num>FESH\s?\d+)", "num"),
        ],
        doc_type_patterns=[],
    ),

    VendorRule(
        name="ALMACENES PLASTITELAS S.A.S.",
        detect=lambda t: "plastitelas" in t.lower(),
        number_patterns=[
            (r"(?P<num>FEP\d+)", "num"),
        ],
        doc_type_patterns=[],
    ),

    VendorRule(
        name="MAR ANTIGUO SAS",
        detect=lambda t: "mar antiguo" in t.lower(),
        number_patterns=[
            (r"(?P<num>MAE-?\d{4,})", "num"),
        ],
        doc_type_patterns=[],
    ),
]


# =========================================================
# PARSE FACTURA
# =========================================================

def parse_invoice(pdf_path: Path, own_company: str = "NATARE SWIM SAS") -> InvoiceInfo:

    raw_text = extract_text_from_pdf(pdf_path)
    text = normalize_spaces(raw_text)

    selected_rule: Optional[VendorRule] = None

    for rule in VENDOR_RULES:

        if rule.detect(text):
            selected_rule = rule
            break

    if selected_rule is None:

        vendor = fallback_vendor_name(raw_text, own_company)

        doc_type = detect_doc_type(text)

        number = fallback_invoice_number(text)

        confidence = (
            "media"
            if vendor != "PROVEEDOR PENDIENTE"
            and number != "NUMERO PENDIENTE"
            else "baja"
        )

    else:

        vendor = selected_rule.name

        doc_type = detect_doc_type(text, selected_rule)

        number = (
            extract_number(text, selected_rule)
            or fallback_invoice_number(text)
        )

        confidence = (
            "alta"
            if number != "NUMERO PENDIENTE"
            else "media"
        )

    invoice_date = extract_invoice_date(text, pdf_path)

    renamed_name = sanitize_filename(
        f"{vendor} - {doc_type} - {number} - {invoice_date}.pdf"
    )

    return InvoiceInfo(
        vendor=vendor,
        doc_type=doc_type,
        number=number,
        invoice_date=invoice_date,
        confidence=confidence,
        original_name=pdf_path.name,
        renamed_name=renamed_name,
    )


# =========================================================
# PROCESAR CARPETA
# =========================================================

def process_folder(
    input_dir: Path,
    output_dir: Path,
    own_company: str = "NATARE SWIM SAS"
) -> None:

    input_dir.mkdir(parents=True, exist_ok=True)

    output_dir.mkdir(parents=True, exist_ok=True)

    renamed_dir = output_dir / "renamed"

    renamed_dir.mkdir(exist_ok=True)

    csv_path = output_dir / "invoice_index.csv"

    zip_path = output_dir / "facturas renombradas.zip"

    pdfs = sorted(input_dir.glob("*.pdf"))

    rows: list[InvoiceInfo] = []

    for pdf in pdfs:

        info = parse_invoice(pdf, own_company)

        destination = renamed_dir / info.renamed_name

        counter = 2

        while destination.exists():

            stem = destination.stem
            suffix = destination.suffix

            destination = (
                renamed_dir
                / f"{stem} ({counter}){suffix}"
            )

            counter += 1

        shutil.copy2(pdf, destination)

        info.renamed_name = destination.name

        rows.append(info)

    # CSV
    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "archivo_original",
            "archivo_renombrado",
            "proveedor",
            "tipo_documento",
            "numero",
            "fecha_factura",
            "confianza",
        ])

        for row in rows:

            writer.writerow([
                row.original_name,
                row.renamed_name,
                row.vendor,
                row.doc_type,
                row.number,
                row.invoice_date,
                row.confidence,
            ])

    # ZIP
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED
    ) as zf:

        for pdf in sorted(renamed_dir.glob("*.pdf")):
            zf.write(pdf, arcname=pdf.name)

    print(f"PDFs procesados: {len(rows)}")
    print(f"Carpeta: {renamed_dir}")
    print(f"CSV: {csv_path}")
    print(f"ZIP: {zip_path}")


# =========================================================
# MAIN
# =========================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description="Renombra facturas PDF automáticamente"
    )

    parser.add_argument(
        "input_dir",
        type=Path,
        help="Carpeta con PDFs"
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./output"),
        help="Carpeta salida"
    )

    parser.add_argument(
        "--empresa",
        type=str,
        default="NATARE SWIM SAS",
        help="Nombre de tu empresa (la compradora), para no confundirla con el proveedor"
    )

    args = parser.parse_args()

    process_folder(
        args.input_dir,
        args.output,
        args.empresa
    )


if __name__ == "__main__":
    main()