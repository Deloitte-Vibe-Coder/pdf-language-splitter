import tempfile
import zipfile
from pathlib import Path

import streamlit as st

from split_bilingual_pdf import split_pdf

# --- Batch limits (adjustable) -------------------------------------------
# These exist because Streamlit Community Cloud's free tier caps each app
# at 1GB of RAM, shared across everyone using it at that moment. All files
# selected in one batch sit fully in memory before/while processing, so we
# cap both file count and combined size to stay well under that ceiling.
MAX_FILES_PER_BATCH = 10
MAX_TOTAL_SIZE_MB = 150
# ---------------------------------------------------------------------------

st.set_page_config(page_title="NL/FR PDF Splitter", page_icon="📄")

st.title("📄 Bilingual PDF Splitter")
st.write(
    "Upload one or more Belgian parliamentary documents (Dutch/French "
    "parallel-column format) and get back separate, single-language PDFs "
    "for each one."
)
st.caption(
    f"Batch limit: up to {MAX_FILES_PER_BATCH} files, "
    f"{MAX_TOTAL_SIZE_MB}MB combined per upload."
)

uploaded_files = st.file_uploader(
    "Choose PDF file(s)", type="pdf", accept_multiple_files=True
)

if uploaded_files:
    total_size_mb = sum(f.size for f in uploaded_files) / (1024 * 1024)

    if len(uploaded_files) > MAX_FILES_PER_BATCH:
        st.error(
            f"You've selected {len(uploaded_files)} files, which is over the "
            f"{MAX_FILES_PER_BATCH}-file limit per batch. Please remove some "
            "and split this into smaller batches."
        )
        st.stop()

    if total_size_mb > MAX_TOTAL_SIZE_MB:
        st.error(
            f"These files total {total_size_mb:.0f}MB, which is over the "
            f"{MAX_TOTAL_SIZE_MB}MB limit per batch. Please remove some "
            "and split this into smaller batches."
        )
        st.stop()

    zip_buffer_path = None
    summary_rows = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = Path(tmp_dir)
        zip_path = tmp_dir / "split_results.zip"

        progress = st.progress(0.0, text="Starting...")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, uploaded_file in enumerate(uploaded_files):
                base_name = uploaded_file.name.rsplit(".", 1)[0]
                progress.progress(
                    i / len(uploaded_files),
                    text=f"Processing {uploaded_file.name} ({i + 1}/{len(uploaded_files)})...",
                )

                input_path = tmp_dir / f"in_{i}.pdf"
                nl_path = tmp_dir / f"out_{i}_NL.pdf"
                fr_path = tmp_dir / f"out_{i}_FR.pdf"
                input_path.write_bytes(uploaded_file.getvalue())

                try:
                    report = split_pdf(
                        str(input_path), str(nl_path), str(fr_path),
                        log=lambda *a: None,
                    )
                    n_two_col = sum(1 for r in report if r[1] == "two-column")
                    n_single = len(report) - n_two_col

                    zf.write(nl_path, f"{base_name}_NL.pdf")
                    zf.write(fr_path, f"{base_name}_FR.pdf")

                    summary_rows.append({
                        "File": uploaded_file.name,
                        "Status": "✅ Done",
                        "Pages": len(report),
                        "Two-column": n_two_col,
                        "Single-column": n_single,
                    })
                except Exception as e:
                    summary_rows.append({
                        "File": uploaded_file.name,
                        "Status": f"❌ Error: {e}",
                        "Pages": "-",
                        "Two-column": "-",
                        "Single-column": "-",
                    })

                # Free this file's memory before moving to the next
                input_path.unlink(missing_ok=True)

        progress.progress(1.0, text="Done.")

        n_ok = sum(1 for r in summary_rows if r["Status"] == "✅ Done")
        st.success(f"Processed {n_ok}/{len(uploaded_files)} file(s) successfully.")

        st.dataframe(summary_rows, use_container_width=True)

        if n_ok > 0:
            st.download_button(
                "⬇️ Download all results (.zip)",
                data=zip_path.read_bytes(),
                file_name="split_results.zip",
                mime="application/zip",
                use_container_width=True,
            )

st.caption(
    "This tool is intended for public Belgian parliamentary documents "
    "(NL/FR parallel-column format)."
)
