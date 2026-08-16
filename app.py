from __future__ import annotations

import base64
import csv
import io
import zipfile
from pathlib import Path

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
st.write("Subí tus PDFs de facturas, revisá o editá el nombre sugerido, y descargá.")

files = st.file_uploader("PDFs de facturas", type="pdf", accept_multiple_files=True)

if files and st.button("Procesar facturas", type="primary"):

    processed = []

    with st.spinner(f"Procesando {len(files)} PDF(s)..."):

        for uploaded in files:

            tmp_path = Path(f"/tmp/{uploaded.name}")
            tmp_path.write_bytes(uploaded.getvalue())

            info = parse_invoice(tmp_path)

            processed.append({
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

    st.success(f"{len(processed)} factura(s) procesadas. Revisá el nombre antes de descargar.")

    final_names: list[str] = []

    for i, item in enumerate(processed):

        confidence_icon = {"alta": "🟢", "media": "🟡", "baja": "🔴"}.get(item["confidence"], "")

        with st.expander(f"{confidence_icon} {item['original_name']} → {item['suggested_name']}"):

            st.caption(
                f"Proveedor: {item['vendor']} · Tipo: {item['doc_type']} · "
                f"Número: {item['number']} · Fecha: {item['invoice_date']} · "
                f"Confianza: {item['confidence']}"
            )

            show_key = f"show_pdf_{i}"

            if st.button("👁️ Ver PDF", key=f"toggle_{i}"):
                st.session_state[show_key] = not st.session_state.get(show_key, False)

            if st.session_state.get(show_key):
                b64 = base64.b64encode(item["bytes"]).decode("utf-8")
                st.markdown(
                    f'<embed src="data:application/pdf;base64,{b64}" '
                    f'width="100%" height="500" type="application/pdf" />',
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Si no se ve la vista previa, tu navegador la está bloqueando — "
                    "usá el botón de abajo para descargar y abrirla."
                )

            edited_name = st.text_input(
                "Nombre del archivo",
                value=item["suggested_name"],
                key=f"name_{i}",
            )

            if not edited_name.lower().endswith(".pdf"):
                edited_name += ".pdf"

            final_names.append(edited_name)

            st.download_button(
                "⬇️ Descargar este PDF",
                data=item["bytes"],
                file_name=edited_name,
                mime="application/pdf",
                key=f"download_{i}",
            )

    # Resolver duplicados de nombre para el ZIP
    seen: dict[str, int] = {}
    resolved_names: list[str] = []

    for name in final_names:

        if name not in seen:
            seen[name] = 1
            resolved_names.append(name)
        else:
            seen[name] += 1
            stem, suffix = Path(name).stem, Path(name).suffix
            resolved_names.append(f"{stem} ({seen[name]}){suffix}")

    if resolved_names != final_names:
        st.warning("Había nombres repetidos — se numeraron automáticamente en el ZIP.")

    st.divider()

    # CSV
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow([
        "archivo_original", "archivo_renombrado", "proveedor",
        "tipo_documento", "numero", "fecha_factura", "confianza",
    ])
    for item, name in zip(processed, resolved_names):
        writer.writerow([
            item["original_name"], name, item["vendor"],
            item["doc_type"], item["number"], item["invoice_date"], item["confidence"],
        ])

    # ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item, name in zip(processed, resolved_names):
            zf.writestr(name, item["bytes"])
        zf.writestr("invoice_index.csv", csv_buffer.getvalue().encode("utf-8-sig"))
    zip_buffer.seek(0)

    st.download_button(
        "⬇️ Descargar ZIP (todas las facturas + índice)",
        data=zip_buffer,
        file_name="facturas renombradas.zip",
        mime="application/zip",
        type="primary",
    )
