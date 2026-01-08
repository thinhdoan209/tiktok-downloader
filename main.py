from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
import httpx
from bs4 import BeautifulSoup
import json
import re
import os
from urllib.parse import quote

app = FastAPI()

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.tiktok.com/",
}

# --- QUAN TRỌNG: Phục vụ file HTML ---
@app.get("/")
async def read_index():
    # Render sẽ tìm file index.html cùng thư mục
    return FileResponse("index.html")

async def get_final_url(short_url: str):
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            resp = await client.get(short_url, headers=HEADERS)
            return str(resp.url)
        except:
            return short_url

@app.get("/api/info")
async def get_tiktok_info(url: str = Query(..., description="Link TikTok")):
    final_url = url
    if "vt.tiktok.com" in url or "vm.tiktok.com" in url:
        final_url = await get_final_url(url)

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            response = await client.get(final_url, headers=HEADERS)
        except httpx.RequestError:
            raise HTTPException(status_code=400, detail="Lỗi kết nối TikTok")

    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find("script", {"id": "__UNIVERSAL_DATA_FOR_REHYDRATION__"}) or \
                 soup.find("script", {"id": "SIGI_STATE"})
    
    if not script_tag:
        raise HTTPException(status_code=500, detail="Không tìm thấy dữ liệu (Captcha/IP chặn)")

    try:
        json_data = json.loads(script_tag.string)
        default_scope = json_data.get("__DEFAULT_SCOPE__", {})
        
        item_struct = None
        video_detail = default_scope.get("webapp.video-detail", {})
        if video_detail:
            item_info = video_detail.get("itemInfo", {})
            item_struct = item_info.get("itemStruct")
        
        if not item_struct:
             raise HTTPException(status_code=404, detail="Không bóc tách được thông tin")

        music_info = item_struct.get("music", {})
        
        # Lấy thông tin tác giả
        author_info = item_struct.get("author", {})

        return {
            "status": "success",
            "video_id": item_struct.get("id"),
            "desc": item_struct.get("desc"),
            "author_unique_id": author_info.get("uniqueId"), 
            "cover": music_info.get("coverLarge"),
            "music_title": music_info.get("title"),
            "music_author": music_info.get("authorName"),
            "mp3_url": music_info.get("playUrl")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý: {str(e)}")

@app.get("/api/download_mp3")
async def download_mp3_proxy(url: str = Query(...), filename: str = Query("music")):
    safe_filename = "tiktok_audio"
    encoded_filename = quote(filename)

    async def iterfile():
        async with httpx.AsyncClient(timeout=45, follow_redirects=True, verify=False) as client:
            try:
                req_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.tiktok.com/",
                }
                async with client.stream("GET", url, headers=req_headers) as response:
                    if response.status_code != 200:
                        return
                    async for chunk in response.aiter_bytes():
                        yield chunk
            except Exception:
                return

    headers = {
        "Content-Type": "audio/mpeg",
        "Content-Disposition": f"attachment; filename=\"{safe_filename}.mp3\"; filename*=UTF-8''{encoded_filename}.mp3"
    }

    return StreamingResponse(iterfile(), media_type="audio/mpeg", headers=headers)

if __name__ == "__main__":
    import uvicorn
    # Host 0.0.0.0 để các máy khác trong mạng LAN cũng vào được
    # Nhưng trên trình duyệt máy chủ, hãy gõ localhost:8000
    uvicorn.run(app, host="0.0.0.0", port=8000)