from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import pandas as pd
import requests
import re
import traceback

app = FastAPI()

# === Allow all origins (frontend React, etc.) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # You can restrict later (e.g., ["https://student-image-viewer.onrender.com"])
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Google Sheet CSV Export Link ===
SHEET_URL = "https://docs.google.com/spreadsheets/d/1IrRRTxzEFodqxxlDTLaFZ-IXzmdr5P4xoFaYgfb6KyA/gviz/tq?tqx=out:csv"


# === Load data from Google Sheet ===
def load_data():
    """Loads the Google Sheet into a pandas DataFrame."""
    print("🔄 Fetching latest data from Google Sheet...")
    try:
        df = pd.read_csv(SHEET_URL, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        df = df.fillna("")  # Replace NaN with empty strings
        print(f"✅ Loaded {len(df)} rows successfully.")
        return df
    except Exception as e:
        print("❌ Error loading sheet:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to load Google Sheet: {e}")


# === Helper: Extract file ID from Google Drive link ===
def extract_file_id(url):
    if not url or not isinstance(url, str):
        return None
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url) or re.search(r"id=([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    return None


# === Proxy endpoint: fetch image directly from Google Drive ===
@app.get("/image-proxy/{file_id}")
def image_proxy(file_id: str):
    """Fetches an image from Google Drive and returns it as a stream (bypasses CORS)."""
    try:
        url = f"https://drive.google.com/uc?export=view&id={file_id}"
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Image fetch failed")

        return StreamingResponse(
            response.iter_content(chunk_size=1024),
            media_type=response.headers.get("content-type", "image/jpeg"),
            headers={"Access-Control-Allow-Origin": "*"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Main endpoint: get student by Scholar ID ===
@app.get("/student/{scholar_id}")
def get_student(scholar_id: str):
    """
    Fetch student data using scholar ID.
    Automatically handles IDs like '4523/2022' by extracting '4523' for matching.
    """
    print(f"🔍 Searching for Scholar ID: {scholar_id}")

    try:
        df = load_data()

        if "Scholar ID" not in df.columns:
            raise HTTPException(status_code=500, detail="Column 'Scholar ID' not found in Google Sheet")

        # Normalize IDs
        df["Scholar ID"] = df["Scholar ID"].astype(str).str.strip().str.replace(" ", "", regex=False)

        # Extract the numeric or first part before "/"
        short_id = scholar_id.strip().split("/")[0].replace(" ", "")
        print(f"🧩 Extracted short ID: {short_id}")

        # Search flexibly — partial match
        row = df[df["Scholar ID"].str.contains(re.escape(short_id), case=False, na=False)]
        if row.empty:
            raise HTTPException(status_code=404, detail=f"Scholar ID {scholar_id} not found")

        data = row.iloc[0].to_dict()

        # Replace empty strings with None for clean JSON
        for k, v in data.items():
            if v == "":
                data[k] = None

        # Convert image links to proxy URLs
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
            if data.get(field):
                file_id = extract_file_id(data[field])
                if file_id:
                    # ✅ Replace with your proxy route (this always renders)
                    data[field] = f"https://student-image-finder.onrender.com/image-proxy/{file_id}"

        print(f"✅ Found data for Scholar ID: {short_id}")
        return data

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Unexpected error:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
