from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH = "/app/search.db"

# Read API keys from environment (set this in Fly secrets later)
VALID_KEYS = os.getenv("API_KEYS", "sk-test-1234").split(",")

def search_db(query: str, limit: int = 20):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("""
        SELECT title, content, url, 
               bm25(pages) as rank 
        FROM pages 
        WHERE pages MATCH ? 
        ORDER BY rank
        LIMIT ?
    """, (query, limit))
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results

@app.get("/")
def root():
    return {"message": "AI Search Engine is live. Use /search?q=your+query&api_key=your_key"}

@app.get("/search")
def search(q: str = Query(..., min_length=1), api_key: str = Query(...), limit: int = 20):
    if api_key not in VALID_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    raw_results = search_db(q, limit)
    
    formatted = []
    for r in raw_results:
        snippet = r['content'][:1000].replace('\n', ' ')
        formatted.append({
            "title": r['title'],
            "url": r['url'],
            "snippet": snippet,
            "relevance_score": round(r['rank'], 2)
        })
    return {"query": q, "count": len(formatted), "results": formatted}
