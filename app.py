import gc
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

from split_bilingual_pdf import split_pdf

# --- Batch limit (adjustable) --------------------------------------------
# Streamlit Community Cloud's free tier caps each app at 1GB of RAM, shared
# across everyone using it at that moment. File COUNT is a poor proxy for
# memory pressure here, since these documents range from ~20 to 500+ pages
# (a handful of large files can use more memory than many small ones). We
# cap on combined upload size instead, which tracks actual memory use much
# more directly: raw uploaded bytes stay in memory for the session, and the
# zipped output (roughly 1.6x the input size, based on real measurements)
# is cached in memory too so the download button doesn't trigger a re-split.
MAX_TOTAL_SIZE_MB = 120
# ---------------------------------------------------------------------------

st.set_page_config(page_title="NL/FR PDF Splitter", page_icon="📄")

# uploader_version is bumped by the "Clear" button below. Changing the
# widget's key forces Streamlit to treat it as a brand new uploader with an
# empty selection -- this is what actually drops the old files' bytes from
# memory, rather than just hiding cached results while they linger.
if "uploader_version" not in st.session_state:
    st.session_state.uploader_version = 0


def clear_batch():
    st.session_state.batch_fingerprint = None
    st.session_state.summary_rows = None
    st.session_state.zip_bytes = None
    st.session_state.uploader_version += 1
    gc.collect()


st.title("📄 Bilingual PDF Splitter")
st.write(
    "Upload one or more Belgian parliamentary documents (Dutch/French "
    "parallel-column format) and get back separate, single-language PDFs "
    "for each one."
)
st.caption(f"Batch limit: {MAX_TOTAL_SIZE_MB}MB combined per upload (any number of files).")

uploaded_files = st.file_uploader(
    "Choose PDF file(s)", type="pdf", accept_multiple_files=True,
    key=f"pdf_uploader_{st.session_state.uploader_version}",
)

if uploaded_files:
    total_size_mb = sum(f.size for f in uploaded_files) / (1024 * 1024)
    usage_ratio = total_size_mb / MAX_TOTAL_SIZE_MB
    over_budget = total_size_mb > MAX_TOTAL_SIZE_MB

    # --- Live budget indicator, shown immediately on selection -- BEFORE
    # anything is processed -- so the user can see where they stand and
    # decide whether to proceed, rather than finding out after the fact. ---
    st.progress(
        min(usage_ratio, 1.0),
        text=f"{total_size_mb:.0f}MB / {MAX_TOTAL_SIZE_MB}MB used "
             f"({len(uploaded_files)} file(s))",
    )
    if over_budget:
        st.error(
            f"⚠️ Over budget by {total_size_mb - MAX_TOTAL_SIZE_MB:.0f}MB. "
            "Remove some files, or click \"Clear & start new batch\" below "
            "and split this into smaller batches."
        )
    elif usage_ratio >= 0.8:
        st.warning(
            f"Approaching the limit -- {MAX_TOTAL_SIZE_MB - total_size_mb:.0f}MB "
            "of headroom left in this batch."
        )
    else:
        st.caption(f"{MAX_TOTAL_SIZE_MB - total_size_mb:.0f}MB of headroom left in this batch.")

    batch_fingerprint = tuple((f.name, f.size) for f in uploaded_files)

    # Processing only ever starts when this button is explicitly clicked --
    # never automatically just because files were selected, and never again
    # just because some other widget (like the download button) triggered a
    # rerun. This is what makes the headroom indicator above meaningful: the
    # user sees it and consciously decides to proceed, rather than the split
    # already running before they've had a chance to look.
    process_clicked = st.button(
        "🚀 Process files",
        disabled=over_budget,
        use_container_width=True,
    )

    if process_clicked and not over_budget:
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

            # Cache results -- the temp dir disappears when this `with` block
            # exits, so we store the actual zip bytes, not just its path.
            st.session_state.batch_fingerprint = batch_fingerprint
            st.session_state.summary_rows = summary_rows
            st.session_state.zip_bytes = zip_path.read_bytes()

    # Show results if we have them cached for THIS exact set of uploaded
    # files -- either just computed above, or carried over from a previous
    # run (e.g. this rerun was triggered by clicking the download button,
    # not by clicking "Process files" again).
    has_results_for_this_batch = (
        st.session_state.get("batch_fingerprint") == batch_fingerprint
        and st.session_state.get("summary_rows") is not None
    )

    if has_results_for_this_batch:
        summary_rows = st.session_state.summary_rows
        n_ok = sum(1 for r in summary_rows if r["Status"] == "✅ Done")
        st.success(f"Processed {n_ok}/{len(uploaded_files)} file(s) successfully.")

        st.dataframe(summary_rows, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            if n_ok > 0:
                st.download_button(
                    "⬇️ Download all results (.zip)",
                    data=st.session_state.zip_bytes,
                    file_name="split_results.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
        with col2:
            st.button(
                "🗑️ Clear & start new batch",
                on_click=clear_batch,
                use_container_width=True,
                help="Frees this batch's files and results from memory before you upload the next one.",
            )

st.caption(
    "This tool is intended for public Belgian parliamentary documents "
    "(NL/FR parallel-column format)."
)
