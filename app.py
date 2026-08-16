from __future__ import annotations

import base64
import csv
import io
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from invoice_renamer import parse_invoice

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
st.write("Subí tus PDFs de facturas, editá el nombre en la tabla si hace falta, y descargá.")

if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0

files = st.file_uploader(
    "PDFs de facturas",
    type="pdf",
    accept_multiple_files=True,
    key=f"uploader_{st.session_state['uploader_key']}",
)

if files and st.button("Procesar facturas", type="primary"):

    processed = []

    with st.spinner(f"Procesando {len(files)} PDF(s)..."):

        for i, uploaded in enumerate(files):

            tmp_path = Path(f"/tmp/{uploaded.name}")
            tmp_path.write_bytes(uploaded.getvalue())

            info = parse_invoice(tmp_path)

            processed.append({
                "id": i,
                "original_name": info.original_name,
                "suggested_name": info.renamed_name,
                "vendor": info.vendor,
                "doc_type": info.doc_type,
                "number": info.number,
                "invoice_date": info.invoice_date,
                "confidence": info.confidence,
                "bytes": uploaded.getvalue(),
            })

            tmp_path.unlink(missing_ok=True)

    st.session_state["processed"] = processed


processed = st.session_state.get("processed")

if processed:

    bytes_by_id = {item["id"]: item["bytes"] for item in processed}

    confidence_icon = {"alta": "🟢", "media": "🟡", "baja": "🔴"}

    df = pd.DataFrame([
        {
            "id": item["id"],
            "Original": item["original_name"],
            "Nombre archivo": item["suggested_name"],
            "Proveedor": item["vendor"],
            "Tipo": item["doc_type"],
            "Número": item["number"],
            "Fecha": item["invoice_date"],
            "Confianza": confidence_icon.get(item["confidence"], "") + " " + item["confidence"],
        }
        for item in processed
    ])

    st.success(f"{len(processed)} factura(s) procesadas. Editá el nombre si hace falta, o borrá una fila (seleccionala y presioná la tecla Delete) para sacarla del lote.")

    edited_df = st.data_editor(
        df,
        column_order=["Original", "Nombre archivo", "Proveedor", "Tipo", "Número", "Fecha", "Confianza"],
        column_config={
            "Original": st.column_config.TextColumn(disabled=True),
            "Nombre archivo": st.column_config.TextColumn(required=True),
            "Proveedor": st.column_config.TextColumn(disabled=True),
            "Tipo": st.column_config.TextColumn(disabled=True),
            "Número": st.column_config.TextColumn(disabled=True),
            "Fecha": st.column_config.TextColumn(disabled=True),
            "Confianza": st.column_config.TextColumn(disabled=True),
        },
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key="editor",
    )

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("🗑️ Limpiar todo y empezar de nuevo"):
            st.session_state.pop("processed", None)
            st.session_state["uploader_key"] += 1
            st.rerun()

    # Filas sobrevivientes (no borradas), en el orden editado
    rows = edited_df[edited_df["Nombre archivo"].notna()].to_dict("records")

    st.divider()
    st.subheader("Vista previa individual")

    final_rows = []

    for row in rows:

        item_id = row["id"]
        item_bytes = bytes_by_id.get(item_id)

        if item_bytes is None:
            continue

        name = str(row["Nombre archivo"]).strip()

        if not name:
            continue

        if not name.lower().endswith(".pdf"):
            name += ".pdf"

        final_rows.append({
            "original_name": row["Original"],
            "name": name,
            "vendor": row["Proveedor"],
            "doc_type": row["Tipo"],
            "number": row["Número"],
            "invoice_date": row["Fecha"],
            "confidence": row["Confianza"],
            "bytes": item_bytes,
        })

        with st.expander(f"{row['Confianza']} {row['Original']} → {name}"):

            show_key = f"show_pdf_{item_id}"

            if st.button("👁️ Ver PDF", key=f"toggle_{item_id}"):
                st.session_state[show_key] = not st.session_state.get(show_key, False)

            if st.session_state.get(show_key):
                b64 = base64.b64encode(item_bytes).decode("utf-8")
                st.markdown(
                    f'<embed src="data:application/pdf;base64,{b64}" '
                    f'width="100%" height="500" type="application/pdf" />',
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Si no se ve la vista previa, tu navegador la está bloqueando — "
                    "usá el botón de abajo para descargar y abrirla."
                )

            st.download_button(
                "⬇️ Descargar este PDF",
                data=item_bytes,
                file_name=name,
                mime="application/pdf",
                key=f"download_{item_id}",
            )

    if not final_rows:
        st.warning("No quedan facturas en el lote.")
        st.stop()

    # Resolver duplicados de nombre para el ZIP
    seen: dict[str, int] = {}
    had_duplicates = False

    for row in final_rows:

        name = row["name"]

        if name not in seen:
            seen[name] = 1
        else:
            seen[name] += 1
            stem, suffix = Path(name).stem, Path(name).suffix
            row["name"] = f"{stem} ({seen[name]}){suffix}"
            had_duplicates = True

    if had_duplicates:
        st.warning("Había nombres repetidos — se numeraron automáticamente en el ZIP.")

    # CSV
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow([
        "archivo_original", "archivo_renombrado", "proveedor",
        "tipo_documento", "numero", "fecha_factura", "confianza",
    ])
    for row in final_rows:
        writer.writerow([
            row["original_name"], row["name"], row["vendor"],
            row["doc_type"], row["number"], row["invoice_date"], row["confidence"],
        ])

    # ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for row in final_rows:
            zf.writestr(row["name"], row["bytes"])
        zf.writestr("invoice_index.csv", csv_buffer.getvalue().encode("utf-8-sig"))
    zip_buffer.seek(0)

    st.divider()

    st.download_button(
        "⬇️ Descargar ZIP (todas las facturas + índice)",
        data=zip_buffer,
        file_name="facturas renombradas.zip",
        mime="application/zip",
        type="primary",
    )
