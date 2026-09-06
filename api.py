@app.get("/stats")
def stats(creds: HTTPAuthorizationCredentials = Depends(security), api_key: str = Query(None)):
    token = (creds.credentials if creds else None) or api_key
    if token is None or token not in VALID_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    conn = _connect()
    try:
        row = conn.execute("SELECT COUNT(*) AS n, MAX(timestamp) AS newest FROM pages").fetchone()
        return {
            "indexed_pages": row["n"],
            "newest_index_ms": row["newest"],
            "seeds": crawler._load_seeds()["seeds"],
        }
    finally:
        conn.close()
