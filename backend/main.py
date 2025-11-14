from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import pandas as pd
import requests
import re
import traceback
import threading
import time

app = FastAPI()

# === CORS ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Google Sheet CSV Export Link ===
SHEET_URL = "https://docs.google.com/spreadsheets/d/1IrRRTxzEFodqxxlDTLaFZ-IXzmdr5P4xoFaYgfb6KyA/gviz/tq?tqx=out:csv"

# === Cache ===
DATA_CACHE = {"df": None, "last_updated": None}


# === Load data from Google Sheet ===
def load_data():
    print("🔄 Fetching latest data from Google Sheet...")
    df = pd.read_csv(SHEET_URL, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df.fillna("")
    print(f"✅ Loaded {len(df)} rows successfully.")
    return df


def refresh_data_cache():
    """Refresh sheet data every 10 minutes."""
    global DATA_CACHE
    while True:
        try:
            df = load_data()
            DATA_CACHE["df"] = df
            DATA_CACHE["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"✅ Cache refreshed at {DATA_CACHE['last_updated']}")
        except Exception as e:
            print("❌ Error refreshing cache:", e)
            traceback.print_exc()

        time.sleep(600)


@app.on_event("startup")
def on_startup():
    try:
        DATA_CACHE["df"] = load_data()
        DATA_CACHE["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print("⚠️ Failed to load initial data:", e)

    threading.Thread(target=refresh_data_cache, daemon=True).start()


# === Manual Refresh Endpoint ===
@app.get("/refresh-sheet")
def refresh_sheet():
    try:
        df = load_data()
        DATA_CACHE["df"] = df
        DATA_CACHE["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")

        print("🔄 Sheet manually refreshed!")
        return {
            "status": "success",
            "message": "Sheet refreshed successfully",
            "last_updated": DATA_CACHE["last_updated"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Helper: Extract file ID from Google Drive link ===
def extract_file_id(url):
    if not url or not isinstance(url, str):
        return None
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url) or re.search(r"id=([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


# === Image Proxy ===
@app.get("/image-proxy/{file_id}")
def image_proxy(file_id: str):
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


# === Student Lookup ===
@app.get("/student/{scholar_id}")
def get_student(scholar_id: str):

    print(f"🔍 Searching for Scholar ID: {scholar_id}")

    if DATA_CACHE["df"] is None:
        raise HTTPException(status_code=503, detail="Data cache not ready.")

    try:
        df = DATA_CACHE["df"]

        if "Scholar ID" not in df.columns:
            raise HTTPException(status_code=500, detail="Column 'Scholar ID' missing in sheet")

        # === CLEAN & NORMALIZE IDs ===
        df["Scholar ID Clean"] = (
            df["Scholar ID"]
            .astype(str)
            .str.strip()
            .str.replace(" ", "", regex=False)
            .str.split("/").str[0]
            .str.lower()
        )

        short_id = scholar_id.strip().replace(" ", "").lower()

        # === EXACT MATCH ONLY ===
        row = df[df["Scholar ID Clean"] == short_id]

        if row.empty:
            raise HTTPException(status_code=404, detail=f"Scholar ID {scholar_id} not found")

        data = row.iloc[0].to_dict()

        # Replace empty strings with None
        for k, v in data.items():
            if v == "":
                data[k] = None

        # Image fields to convert to proxy URLs
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
                    data[field] = f"https://student-image-finder.onrender.com/image-proxy/{file_id}"

        print(f"✅ Found data for Scholar ID: {short_id}")

        return {
            "last_updated": DATA_CACHE["last_updated"],
            **data
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Unexpected error:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
