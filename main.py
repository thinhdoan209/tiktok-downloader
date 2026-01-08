from fastapi import FastAPI, Query, HTTPException
import httpx
from urllib.parse import quote

app = FastAPI()


@app.get("/")
def home():
    return {"status": "ok", "message": "TikTok downloader API"}


@app.get("/api/info")
async def tiktok_info(
    url: str = Query(..., description="TikTok video URL")
):
    if "tiktok.com" not in url:
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    # Encode URL để truyền an toàn
    encoded_url = quote(url, safe="")

    oembed_url = f"https://www.tiktok.com/oembed?url={encoded_url}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(oembed_url, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail="Failed to fetch TikTok oEmbed data"
        )

    data = resp.json()

    # video_id chuẩn TikTok
    video_id = (
        data.get("embed_product_id")
        or data.get("html", "")
    )

    if not video_id:
        raise HTTPException(
            status_code=500,
            detail="Cannot extract video_id"
        )

    return {
        "source": "oEmbed",
        "video_id": data.get("embed_product_id"),
        "title": data.get("title"),
        "author_name": data.get("author_name"),
        "author_unique_id": data.get("author_unique_id"),
        "author_url": data.get("author_url"),
        "thumbnail": data.get("thumbnail_url"),
        "provider": data.get("provider_name"),
    }
