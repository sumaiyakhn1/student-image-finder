from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import re
import traceback

app = FastAPI()

# === Allow React frontend (CORS) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can replace "*" with your frontend URL later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === NEW GOOGLE SHEET LINK ===
SHEET_URL = "https://docs.google.com/spreadsheets/d/1IrRRTxzEFodqxxlDTLaFZ-IXzmdr5P4xoFaYgfb6KyA/gviz/tq?tqx=out:csv"


# === Load Google Sheet Data ===
def load_data():
    """Load Google Sheet as DataFrame and clean column names."""
    print("🔄 Fetching data from Google Sheet...")
    try:
        df = pd.read_csv(SHEET_URL)
        df.columns = [c.strip() for c in df.columns]
        print("✅ Data loaded successfully. Columns found:", df.columns.tolist())
        return df
    except Exception as e:
        print("❌ ERROR loading Google Sheet:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to load Google Sheet: {e}")


# === Convert Google Drive links for direct image rendering ===
def convert_drive_link(url):
    """Turn a Google Drive 'file/d/...' URL into a direct-view image URL."""
    if pd.isna(url) or not isinstance(url, str):
        return None
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=view&id={file_id}"
    return None


# === Fetch Student by Scholar ID ===
@app.get("/student/{scholar_id}")
def get_student(scholar_id: str):
    print(f"🔍 Searching for Scholar ID: {scholar_id}")
    try:
        df = load_data()

        # Ensure consistent column formatting
        df.columns = [c.strip() for c in df.columns]
        if "Scholar ID" not in df.columns:
            raise HTTPException(status_code=500, detail="Column 'Scholar ID' not found in sheet")

        # Clean & standardize Scholar IDs
        df["Scholar ID"] = df["Scholar ID"].astype(str).str.strip()

        # ✅ Partial + Case-insensitive matching
        pattern = re.escape(scholar_id.strip())
        row = df[df["Scholar ID"].str.contains(pattern, case=False, na=False)]

        if row.empty:
            raise HTTPException(status_code=404, detail=f"Scholar ID {scholar_id} not found")

        # Convert row to dictionary
        data = row.iloc[0].to_dict()

        # Replace NaN → None
        for key, value in data.items():
            if pd.isna(value):
                data[key] = None

        # === Convert all image fields ===
        image_fields = [
            "Student's Photograph",
            "Father's Photograph",
            "Mother's Photograph",
            "Guardian's Photo",
            "Grandfather's Photograph",
            "Grandmother's Photograph",
            "Sibling-1 Photograph (Real brother/sister)",
            "Aadhar Card Of Sibling 1",
            "Sibling-2 Photograph (Real brother/sister)",
            "Aadhar Card Of Sibling 2",
        ]

        for field in image_fields:
            if field in data:
                data[field] = convert_drive_link(data[field])

        print(f"✅ Found data for Scholar ID: {scholar_id}")
        return data

    except HTTPException:
        raise
    except Exception as e:
        print("❌ UNEXPECTED ERROR:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
