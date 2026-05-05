"""
utils/file_loader.py
File upload and data loading utilities for SAP AI Platform.
Handles CSV, Excel, and image uploads with validation and preview.
"""

import pandas as pd
import streamlit as st
from typing import Optional

DATA_TYPES  = ["csv", "xlsx", "xls"]
IMAGE_TYPES = ["png", "jpg", "jpeg", "webp"]
ALLOWED_TYPES = DATA_TYPES + IMAGE_TYPES


def render_file_uploader(
    label: str = "Upload file",
    accept: list = None,
    key: str = "file_upload",
    help_text: str = None,
):
    if accept is None:
        accept = ALLOWED_TYPES
    return st.file_uploader(
        label,
        type=accept,
        key=key,
        help=help_text or f"Supported: {', '.join(accept)}",
    )


def load_dataframe(uploaded_file) -> tuple:
    """Load an uploaded CSV or Excel file into a Pandas DataFrame."""
    if uploaded_file is None:
        return None, "No file uploaded."
    filename = uploaded_file.name.lower()
    try:
        if filename.endswith(".csv"):
            try:
                df = pd.read_csv(uploaded_file, encoding="utf-8")
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding="latin-1")
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded_file, engine="openpyxl")
        else:
            return None, f"Unsupported file type: {filename}"
        return df, ""
    except Exception as e:
        return None, f"Failed to load file: {e}"


def get_image_bytes(uploaded_file) -> tuple:
    """Read raw bytes from an uploaded image file."""
    if uploaded_file is None:
        return None, ""
    mime_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }
    ext = uploaded_file.name.lower().split(".")[-1]
    mime = mime_map.get(ext, "image/png")
    return uploaded_file.read(), mime


def render_dataframe_preview(
    df: pd.DataFrame,
    max_rows: int = 5,
    title: str = "Preview",
) -> None:
    """Render a styled DataFrame preview with row/column counts."""
    st.markdown(f"**{title}** — {df.shape[0]:,} rows × {df.shape[1]} columns")
    st.dataframe(df.head(max_rows), use_container_width=True)


def dataframe_summary(df: pd.DataFrame) -> dict:
    """Generate a structural summary for Layer 1 validation."""
    return {
        "row_count":      int(df.shape[0]),
        "col_count":      int(df.shape[1]),
        "columns":        list(df.columns),
        "null_counts":    df.isnull().sum().to_dict(),
        "null_pct":       (df.isnull().sum() / len(df) * 100).round(2).to_dict(),
        "dtypes":         {col: str(dtype) for col, dtype in df.dtypes.items()},
        "duplicate_rows": int(df.duplicated().sum()),
        "row_sample":     df.head(3).to_dict(orient="records"),
    }
