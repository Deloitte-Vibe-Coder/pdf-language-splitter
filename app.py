import tempfile
from pathlib import Path

import streamlit as st

from split_bilingual_pdf import split_pdf

st.set_page_config(page_title="NL/FR PDF Splitter", page_icon="📄")

st.title("📄 Bilingual PDF Splitter")
st.write(
    "Upload a Belgian parliamentary document (Dutch/French parallel-column "
    "format) and get back two separate, single-language PDFs."
)

uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = Path(tmp_dir)
        input_path = tmp_dir / "input.pdf"
        nl_path = tmp_dir / "output_NL.pdf"
        fr_path = tmp_dir / "output_FR.pdf"

        input_path.write_bytes(uploaded_file.getvalue())

        with st.spinner("Splitting document — this can take a minute for long files..."):
            try:
                report = split_pdf(str(input_path), str(nl_path), str(fr_path), log=lambda *a: None)
            except Exception as e:
                st.error(f"Something went wrong while processing this file: {e}")
                st.stop()

        n_two_col = sum(1 for r in report if r[1] == "two-column")
        n_single = len(report) - n_two_col

        st.success(
            f"Done — {len(report)} pages processed "
            f"({n_two_col} two-column, {n_single} single-column annex/table pages)."
        )

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "⬇️ Download Dutch (NL) version",
                data=nl_path.read_bytes(),
                file_name=f"{uploaded_file.name.rsplit('.', 1)[0]}_NL.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        with col2:
            st.download_button(
                "⬇️ Download French (FR) version",
                data=fr_path.read_bytes(),
                file_name=f"{uploaded_file.name.rsplit('.', 1)[0]}_FR.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        with st.expander("Show per-page classification details"):
            st.dataframe(
                {
                    "Page": [r[0] for r in report],
                    "Type": [r[1] for r in report],
                    "Detail": [r[2] for r in report],
                },
                use_container_width=True,
            )

st.caption(
    "This tool is intended for public Belgian parliamentary documents "
    "(NL/FR parallel-column format)."
)
