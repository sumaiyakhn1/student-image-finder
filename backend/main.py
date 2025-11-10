from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import re
import traceback

app = FastAPI()

# === Allow frontend requests (React, Render, etc.) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for testing; restrict later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Google Sheet CSV Link ===
SHEET_URL = "https://docs.google.com/spreadsheets/d/1IrRRTxzEFodqxxlDTLaFZ-IXzmdr5P4xoFaYgfb6KyA/gviz/tq?tqx=out:csv"


# === Helper: Load Sheet ===
def load_data():
    """Load Google Sheet data and normalize column names."""
    print("🔄 Fetching data from Google Sheet...")
    try:
        df = pd.read_csv(SHEET_URL, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        df = df.fillna("")  # Replace NaN with empty string
        print(f"✅ Loaded {len(df)} rows successfully. Columns: {df.columns.tolist()}")
        return df
    except Exception as e:
        print("❌ Error loading sheet:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to load Google Sheet: {e}")


# === Helper: Convert Google Drive link to viewable image URL ===
def convert_drive_link(url):
    """Convert Google Drive file links into direct image URLs."""
    if not url or not isinstance(url, str):
        return None

    # Case 1: /file/d/<ID>/view
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return f"https://drive.google.com/uc?export=view&id={match.group(1)}"

    # Case 2: id=<ID>
    match2 = re.search(r"id=([a-zA-Z0-9_-]+)", url)
    if match2:
        return f"https://drive.google.com/uc?export=view&id={match2.group(1)}"

    return None


# === Endpoint: Get student details by Scholar ID ===
@app.get("/student/{scholar_id}")
def get_student(scholar_id: str):
    """
    User can enter full Scholar ID (like 2172/2016),
    system extracts numeric part (2172) and searches accordingly.
    """
    print(f"🔍 Searching for Scholar ID: {scholar_id}")

    try:
        df = load_data()

        # Ensure correct column exists
        if "Scholar ID" not in df.columns:
            raise HTTPException(status_code=500, detail="Column 'Scholar ID' not found in Google Sheet")

        # Clean and normalize Scholar IDs
        df["Scholar ID"] = df["Scholar ID"].astype(str).str.strip().str.replace(" ", "", regex=False)

        # Extract numeric part before "/" for search
        short_id = scholar_id.strip().split("/")[0].replace(" ", "")
        print(f"🧩 Extracted ID for search: {short_id}")

        # ✅ Match both full and short versions
        row = df[
            (df["Scholar ID"].str.strip().str.lower() == scholar_id.strip().lower())
            | (df["Scholar ID"].str.contains(re.escape(short_id), case=False, na=False))
        ]

        if row.empty:
            raise HTTPException(status_code=404, detail=f"Scholar ID {scholar_id} not found")

        # Get the first matching row
        data = row.iloc[0].to_dict()

        # Replace empty strings with None for cleaner JSON
        for k, v in data.items():
            if v == "":
                data[k] = None

        # Print which columns are being treated as image fields
        print("🖼️ Image Fields Found:", [f for f in data.keys() if "Photograph" in f or "Photo" in f])

        # Convert Google Drive image links
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
            if field in data and data[field]:
                data[field] = convert_drive_link(data[field])

        print(f"✅ Found record for Scholar ID: {short_id}")
        return data

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Unexpected Error:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
