from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import re
import traceback

app = FastAPI()

# === Allow React frontend (CORS) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update later for your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === YOUR LATEST GOOGLE SHEET (CSV VIEW) ===
SHEET_URL = "https://docs.google.com/spreadsheets/d/1IrRRTxzEFodqxxlDTLaFZ-IXzmdr5P4xoFaYgfb6KyA/gviz/tq?tqx=out:csv"


# === Helper: Load and sanitize sheet ===
def load_data():
    """Load Google Sheet safely and clean up types & column names."""
    print("🔄 Fetching data from Google Sheet...")
    try:
        df = pd.read_csv(SHEET_URL, dtype=str)  # ✅ Force everything as string
        df.columns = [c.strip() for c in df.columns]
        df = df.fillna("")  # Replace NaN with empty string
        print(f"✅ Loaded {len(df)} rows from sheet.")
        return df
    except Exception as e:
        print("❌ ERROR loading Google Sheet:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to load Google Sheet: {e}")


# === Helper: Convert Drive link to viewable URL ===
def convert_drive_link(url):
    """Turn Google Drive 'file/d/.../view' link into a direct-view image link."""
    if not url or not isinstance(url, str):
        return None

    # Match /d/<file_id> pattern
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=view&id={file_id}"

    # If already uc?id= style
    match2 = re.search(r"id=([a-zA-Z0-9_-]+)", url)
    if match2:
        file_id = match2.group(1)
        return f"https://drive.google.com/uc?export=view&id={file_id}"

    return None


# === Endpoint: Get student by Scholar ID ===
@app.get("/student/{scholar_id}")
def get_student(scholar_id: str):
    print(f"🔍 Searching for Scholar ID: {scholar_id}")
    try:
        df = load_data()

        # Ensure consistent Scholar ID column
        if "Scholar ID" not in df.columns:
            raise HTTPException(status_code=500, detail="Column 'Scholar ID' not found in sheet")

        # Clean all Scholar IDs
        df["Scholar ID"] = df["Scholar ID"].astype(str).str.strip().str.replace(" ", "", regex=False)

        # Clean input Scholar ID
        scholar_id = scholar_id.strip().replace(" ", "")

        # === FIX: Handle fraction-like IDs like "4523/2022" ===
        # Some spreadsheets interpret 4523/2022 as a division — this ensures we match even those
        possible_matches = df[df["Scholar ID"].str.contains(re.escape(scholar_id), case=False, na=False)]

        if possible_matches.empty:
            raise HTTPException(status_code=404, detail=f"Scholar ID {scholar_id} not found")

        # Use the first match (or you can extend for multiple)
        data = possible_matches.iloc[0].to_dict()

        # Replace empty strings with None
        for key, value in data.items():
            if value == "":
                data[key] = None

        # === Convert all image fields to viewable links ===
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

        print(f"✅ Found data for Scholar ID: {scholar_id}")
        return data

    except HTTPException:
        raise
    except Exception as e:
        print("❌ UNEXPECTED ERROR:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
