from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import re
import traceback

app = FastAPI()

# === Allow frontend requests ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Google Sheet CSV link ===
SHEET_URL = "https://docs.google.com/spreadsheets/d/1IrRRTxzEFodqxxlDTLaFZ-IXzmdr5P4xoFaYgfb6KyA/gviz/tq?tqx=out:csv"


# === Helper: Load Sheet ===
def load_data():
    print("🔄 Loading Google Sheet data...")
    try:
        df = pd.read_csv(SHEET_URL, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        df = df.fillna("")  # Replace NaN with ""
        print(f"✅ Loaded {len(df)} rows successfully.")
        return df
    except Exception as e:
        print("❌ Error loading sheet:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to load Google Sheet: {e}")


# === Helper: Convert Drive link to thumbnail ===
def convert_drive_link(url):
    """Convert Google Drive file link to a thumbnail URL."""
    if not url or not isinstance(url, str):
        return None

    # Match file ID from /file/d/.../ or id=...
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        match = re.search(r"id=([a-zA-Z0-9_-]+)", url)

    if match:
        file_id = match.group(1)
        # ✅ Use thumbnail endpoint (faster, works in <img>)
        return f"https://drive.google.com/thumbnail?id={file_id}"

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

        if "Scholar ID" not in df.columns:
            raise HTTPException(status_code=500, detail="Column 'Scholar ID' not found in sheet")

        df["Scholar ID"] = df["Scholar ID"].astype(str).str.strip().str.replace(" ", "", regex=False)

        # Extract numeric part before slash
        short_id = scholar_id.strip().split("/")[0].replace(" ", "")
        print(f"🧩 Extracted search ID: {short_id}")

        # Match both full and short version
        row = df[
            (df["Scholar ID"].str.lower() == scholar_id.strip().lower())
            | (df["Scholar ID"].str.contains(re.escape(short_id), case=False, na=False))
        ]

        if row.empty:
            raise HTTPException(status_code=404, detail=f"Scholar ID {scholar_id} not found")

        data = row.iloc[0].to_dict()

        # Replace empty strings with None
        for k, v in data.items():
            if v == "":
                data[k] = None

        print("🖼️ Found image-related fields:",
              [f for f in data.keys() if "Photograph" in f or "Photo" in f])

        # Fields that may contain image links
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

        # Convert Drive URLs → thumbnail URLs
        for field in image_fields:
            if field in data and data[field]:
                data[field] = convert_drive_link(data[field])

        print(f"✅ Record found for Scholar ID: {scholar_id}")
        return data

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Unexpected error:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
