from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import streamlit as st

from invoice_renamer import InvoiceInfo, parse_invoice

st.set_page_config(page_title="Facturas Natare", page_icon="🧾", layout="centered")


# =========================================================
# ACCESO
# =========================================================

def check_password() -> bool:
    if st.session_state.get("authed"):
        return True

    st.title("🧾 Facturas Natare")
    password = st.text_input("Contraseña", type="password")

    if password:
        if password == st.secrets.get("APP_PASSWORD"):
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")

    return False


if not check_password():
    st.stop()


# =========================================================
# APP
# =========================================================

st.title("🧾 Renombrador de facturas")
st.write("Subí tus PDFs de facturas. La app las renombra, arma el índice y te da un ZIP para descargar.")

files = st.file_uploader("PDFs de facturas", type="pdf", accept_multiple_files=True)

if files and st.button("Procesar facturas", type="primary"):

    rows: list[InvoiceInfo] = []
    renamed_files: dict[str, bytes] = {}
    used_names: set[str] = set()

    with st.spinner(f"Procesando {len(files)} PDF(s)..."):

        for uploaded in files:

            tmp_path = Path(f"/tmp/{uploaded.name}")
            tmp_path.write_bytes(uploaded.getvalue())

            info = parse_invoice(tmp_path)

            name = info.renamed_name
            stem, suffix = Path(name).stem, Path(name).suffix
            counter = 2

            while name in used_names:
                name = f"{stem} ({counter}){suffix}"
                counter += 1

            used_names.add(name)
            info.renamed_name = name
            renamed_files[name] = uploaded.getvalue()
            rows.append(info)

            tmp_path.unlink(missing_ok=True)

    st.success(f"{len(rows)} factura(s) procesadas.")

    # Tabla resumen
    st.dataframe(
        [
            {
                "Original": r.original_name,
                "Renombrado": r.renamed_name,
                "Proveedor": r.vendor,
                "Tipo": r.doc_type,
                "Número": r.number,
                "Fecha": r.invoice_date,
                "Confianza": r.confidence,
            }
            for r in rows
        ],
        use_container_width=True,
    )

    low_confidence = [r for r in rows if r.confidence == "baja"]
    if low_confidence:
        st.warning(
            f"{len(low_confidence)} factura(s) con confianza baja — revisalas manualmente: "
            + ", ".join(r.original_name for r in low_confidence)
        )

    # CSV
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow([
        "archivo_original", "archivo_renombrado", "proveedor",
        "tipo_documento", "numero", "fecha_factura", "confianza",
    ])
    for r in rows:
        writer.writerow([
            r.original_name, r.renamed_name, r.vendor,
            r.doc_type, r.number, r.invoice_date, r.confidence,
        ])

    # ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in renamed_files.items():
            zf.writestr(name, content)
        zf.writestr("invoice_index.csv", csv_buffer.getvalue().encode("utf-8-sig"))
    zip_buffer.seek(0)

    st.download_button(
        "⬇️ Descargar ZIP (facturas + índice)",
        data=zip_buffer,
        file_name="facturas renombradas.zip",
        mime="application/zip",
        type="primary",
    )
