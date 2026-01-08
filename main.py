from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse # <--- Thêm FileResponse
import httpx
from bs4 import BeautifulSoup
import json
import os # <--- Thêm thư viện os
from urllib.parse import quote

app = FastAPI()

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

# --- THÊM ĐOẠN NÀY ĐỂ HIỂN THỊ TRANG WEB ---
@app.get("/")
async def read_index():
    # Đảm bảo file index.html nằm cùng thư mục với main.py
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "Chưa có file index.html, vui lòng tạo file giao diện"}
# -------------------------------------------

async def get_final_url(short_url: str):
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            resp = await client.get(short_url, headers=HEADERS)
            return str(resp.url)
        except:
            return short_url

@app.get("/api/info")
async def get_tiktok_info(url: str = Query(..., description="Link TikTok")):
    # (Giữ nguyên code xử lý info như cũ)
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
        
        return {
            "status": "success",
            "video_id": item_struct.get("id"),
            "desc": item_struct.get("desc"),
            "cover": music_info.get("coverLarge"),
            "music_title": music_info.get("title"),
            "music_author": music_info.get("authorName"),
            "mp3_url": music_info.get("playUrl")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý: {str(e)}")

@app.get("/api/download_mp3")
async def download_mp3_proxy(url: str = Query(...), filename: str = Query("music")):
    # 1. Tạo tên file an toàn (Không dấu) để dự phòng
    # Nếu tên file lỗi, nó sẽ dùng tên này
    safe_filename = "tiktok_audio"
    
    # 2. Mã hóa tên file tiếng Việt sang dạng %xx%xx (URL Encoded)
    # Ví dụ: "nhạc nền" -> "nh%E1%BA%A1c%20n%E1%BB%81n"
    encoded_filename = quote(filename)

    async def iterfile():
        # Tắt verify=False để tránh lỗi SSL, tăng timeout lên 45s
        async with httpx.AsyncClient(timeout=45, follow_redirects=True, verify=False) as client:
            try:
                # Giả lập Header giống hệt Chrome
                req_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.tiktok.com/",
                }
                
                async with client.stream("GET", url, headers=req_headers) as response:
                    if response.status_code != 200:
                        # Nếu TikTok chặn, in lỗi ra terminal để debug
                        print(f"Lỗi tải từ TikTok: {response.status_code}")
                        return

                    async for chunk in response.aiter_bytes():
                        yield chunk
            except Exception as e:
                print(f"Lỗi kết nối: {e}")
                return

    # 3. Cấu hình Header trả về chuẩn RFC 5987
    # Đây là chuẩn quốc tế để trình duyệt hiểu được tên file tiếng Việt
    headers = {
        "Content-Type": "audio/mpeg",
        # Cấu trúc: filename="tên_không_dấu.mp3"; filename*=UTF-8''tên_có_dấu_đã_mã_hóa.mp3
        "Content-Disposition": f"attachment; filename=\"{safe_filename}.mp3\"; filename*=UTF-8''{encoded_filename}.mp3"
    }

    return StreamingResponse(iterfile(), media_type="audio/mpeg", headers=headers)

if __name__ == "__main__":
    import uvicorn
    # Host 0.0.0.0 để các máy khác trong mạng LAN cũng vào được
    # Nhưng trên trình duyệt máy chủ, hãy gõ localhost:8000
    uvicorn.run(app, host="0.0.0.0", port=8000)