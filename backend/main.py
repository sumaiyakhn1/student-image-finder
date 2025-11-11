from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
import pandas as pd
import httpx
import re
import traceback
import threading
import time
import io
from PIL import Image

app = FastAPI()

# === Allow all origins ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Google Sheet CSV Export Link ===
SHEET_URL = "https://docs.google.com/spreadsheets/d/1IrRRTxzEFodqxxlDTLaFZ-IXzmdr5P4xoFaYgfb6KyA/gviz/tq?tqx=out:csv"

# === Global caches ===
DATA_CACHE = {"df": None, "last_updated": None}
IMAGE_CACHE = {}
CACHE_TTL = 60 * 60 * 4  # 4 hours


# === Utility: Compress image before returning ===
def compress_image(data, max_size=(350, 350)):
    """Reduce image size to ~300–400 px for faster delivery."""
    try:
        img = Image.open(io.BytesIO(data))
        img.thumbnail(max_size)
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=80)
        return output.getvalue()
    except Exception:
        return data  # fallback (in case of non-image file)


# === Extract file ID from Google Drive URL ===
def extract_file_id(url: str):
    if not url or not isinstance(url, str):
        return None
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url) or re.search(r"id=([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


# === Build proxy URL helper ===
def build_image_url(url: str):
    file_id = extract_file_id(url)
    return f"https://student-image-finder.onrender.com/image-proxy/{file_id}" if file_id else None


# === Load data from Google Sheet and prebuild proxy URLs ===
def load_data():
    print("🔄 Fetching latest data from Google Sheet...")
    try:
        df = pd.read_csv(SHEET_URL, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        df = df.fillna("")

        image_fields = [
            "Student's Photograph", "Father's Photograph", "Mother's Photograph",
            "Guardian's Photo", "Grandfather's Photograph", "Grandmother's Photograph",
            "Sibling-1 Photograph (Real brother/sister)",
            "Sibling-2 Photograph (Real brother/sister)",
        ]

        for field in image_fields:
            if field in df.columns:
                df[field] = df[field].apply(build_image_url)

        print(f"✅ Loaded {len(df)} rows successfully.")
        return df
    except Exception as e:
        print("❌ Error loading sheet:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to load Google Sheet: {e}")


# === Auto-refresh data cache every 10 minutes ===
def refresh_data_cache():
    while True:
        try:
            df = load_data()
            DATA_CACHE["df"] = df
            DATA_CACHE["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"✅ Data cache refreshed at {DATA_CACHE['last_updated']}")
        except Exception as e:
            print("❌ Error refreshing cache:", e)
        time.sleep(600)  # every 10 min


@app.on_event("startup")
def on_startup():
    try:
        DATA_CACHE["df"] = load_data()
        DATA_CACHE["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print("⚠️ Failed to load data on startup:", e)

    thread = threading.Thread(target=refresh_data_cache, daemon=True)
    thread.start()


# === Async, cached image proxy ===
@app.get("/image-proxy/{file_id}")
async def image_proxy(file_id: str):
    """Fetch Google Drive image asynchronously, cache + compress."""
    try:
        # ✅ Serve from memory cache
        if file_id in IMAGE_CACHE:
            cached = IMAGE_CACHE[file_id]
            if time.time() - cached["timestamp"] < CACHE_TTL:
                return Response(
                    content=cached["data"],
                    media_type=cached["content_type"],
                    headers={"Cache-Control": "public, max-age=14400"}
                )

        # 🧠 Fetch fresh from Google Drive
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"https://drive.google.com/uc?export=view&id={file_id}"
            resp = await client.get(url)

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Image fetch failed")

        # Compress & cache
        data = compress_image(resp.content)
        content_type = resp.headers.get("content-type", "image/jpeg")

        IMAGE_CACHE[file_id] = {
            "data": data,
            "content_type": content_type,
            "timestamp": time.time(),
        }

        return Response(
            content=data,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=14400"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Main endpoint: get student by Scholar ID ===
@app.get("/student/{scholar_id}")
def get_student(scholar_id: str):
    """
    Fetch student data quickly from cached DataFrame.
    """
    print(f"🔍 Searching for Scholar ID: {scholar_id}")

    if DATA_CACHE["df"] is None:
        raise HTTPException(status_code=503, detail="Data cache not ready. Try again shortly.")

    try:
        df = DATA_CACHE["df"]
        if "Scholar ID" not in df.columns:
            raise HTTPException(status_code=500, detail="Column 'Scholar ID' not found in Google Sheet")

        # Normalize Scholar IDs
        df["Scholar ID"] = df["Scholar ID"].astype(str).str.strip().str.replace(" ", "", regex=False)
        short_id = scholar_id.strip().split("/")[0].replace(" ", "")
        row = df[df["Scholar ID"].str.contains(re.escape(short_id), case=False, na=False)]

        if row.empty:
            raise HTTPException(status_code=404, detail=f"Scholar ID {scholar_id} not found")

        data = row.iloc[0].to_dict()

        # Replace empty strings with None
        for k, v in data.items():
            if v == "":
                data[k] = None

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
