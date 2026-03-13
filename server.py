import json, httpx
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://api.openalex.org"
YOUR_EMAIL = "dipnigeria2@gmail.com"
mcp = FastMCP("openalex_mcp")

async def _get(endpoint, params):
    params.setdefault("mailto", YOUR_EMAIL)
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{BASE_URL}/{endpoint}", params={k:v for k,v in params.items() if v}, headers={"User-Agent": f"openalex-mcp/1.0 (mailto:{YOUR_EMAIL})"})
        r.raise_for_status()
        return r.json()

def _err(e):
    if isinstance(e, httpx.HTTPStatusError):
        return f"Error: API status {e.response.status_code}"
    return f"Error: {e}"

def _fmt(w):
    src = (w.get("primary_location") or {}).get("source") or {}
    return {"id": w.get("id","").replace("https://openalex.org/",""), "title": w.get("title",""), "authors": [a["author"]["display_name"] for a in w.get("authorships",[])[:5] if a.get("author")], "year": w.get("publication_year"), "source": src.get("display_name",""), "doi": w.get("doi",""), "cited_by_count": w.get("cited_by_count",0), "is_oa": w.get("open_access",{}).get("is_oa",False)}

class SW(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., description="Search query e.g. protest movements Africa")
    year_from: Optional[int] = Field(default=None, ge=1000, le=2100, description="Start year")
    year_to: Optional[int] = Field(default=None, ge=1000, le=2100, description="End year")
    work_type: Optional[str] = Field(default=None, description="article, book, preprint")
    open_access_only: bool = Field(default=False, description="OA only")
    sort_by: str = Field(default="relevance_score", description="relevance_score or cited_by_count")
    per_page: int = Field(default=10, ge=1, le=25)
    page: int = Field(default=1, ge=1)

class GW(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_id: str = Field(..., description="OpenAlex ID e.g. W2741809807")

class SA(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., description="Author name")
    per_page: int = Field(default=10, ge=1, le=25)

class GAW(BaseModel):
    model_config = ConfigDict(extra="forbid")
    author_id: str = Field(..., description="OpenAlex author ID e.g. A2208157607")
    per_page: int = Field(default=10, ge=1, le=25)
    sort_by: str = Field(default="cited_by_count", description="cited_by_count or publication_year")

class CB(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_id: str = Field(..., description="OpenAlex work ID")
    per_page: int = Field(default=10, ge=1, le=25)

@mcp.tool(name="openalex_search_works", annotations={"readOnlyHint": True, "destructiveHint": False})
async def openalex_search_works(params: SW) -> str:
    """Search OpenAlex for scholarly works with filters for year, type, open access."""
    try:
        f = []
        if params.year_from and params.year_to: f.append(f"publication_year:{params.year_from}-{params.year_to}")
        elif params.year_from: f.append(f"publication_year:>{params.year_from-1}")
        elif params.year_to: f.append(f"publication_year:<{params.year_to+1}")
        if params.work_type: f.append(f"type:{params.work_type}")
        if params.open_access_only: f.append("is_oa:true")
        p = {"search": params.query, "sort": params.sort_by, "per-page": params.per_page, "page": params.page}
        if f: p["filter"] = ",".join(f)
        d = await _get("works", p)
        return json.dumps({"total": d.get("meta",{}).get("count",0), "works": [_fmt(w) for w in d.get("results",[])]}, indent=2)
    except Exception as e: return _err(e)

@mcp.tool(name="openalex_get_work", annotations={"readOnlyHint": True, "destructiveHint": False})
async def openalex_get_work(params: GW) -> str:
    """Get full details for a single work including abstract, authors, topics."""
    try:
        wid = params.work_id if params.work_id.startswith("W") else f"W{params.work_id}"
        d = await _get(f"works/{wid}", {})
        inv = d.get("abstract_inverted_index") or {}
        abstract = ""
        if inv:
            mp = max((p for ps in inv.values() for p in ps), default=0)
            words = [""]*(mp+1)
            for word,ps in inv.items():
                for p in ps:
                    if p<=mp: words[p]=word
            abstract = " ".join(w for w in words if w)
        src = (d.get("primary_location") or {}).get("source") or {}
        return json.dumps({"id": d.get("id","").replace("https://openalex.org/",""), "title": d.get("title",""), "abstract": abstract[:1500] or "(not available)", "authors": [{"name": a["author"]["display_name"], "institutions": [i.get("display_name","") for i in a.get("institutions",[])]} for a in d.get("authorships",[])[:10] if a.get("author")], "year": d.get("publication_year"), "source": src.get("display_name",""), "doi": d.get("doi",""), "cited_by_count": d.get("cited_by_count",0), "topics": [t.get("display_name","") for t in d.get("topics",[])[:5]]}, indent=2)
    except Exception as e: return _err(e)

@mcp.tool(name="openalex_search_authors", annotations={"readOnlyHint": True, "destructiveHint": False})
async def openalex_search_authors(params: SA) -> str:
    """Search for authors by name."""
    try:
        d = await _get("authors", {"search": params.query, "per-page": params.per_page})
        return json.dumps({"total": d.get("meta",{}).get("count",0), "authors": [{"id": a.get("id","").replace("https://openalex.org/",""), "name": a.get("display_name",""), "works_count": a.get("works_count",0), "cited_by_count": a.get("cited_by_count",0), "institution": (a.get("last_known_institutions") or [{}])[0].get("display_name","")} for a in d.get("results",[])]}, indent=2)
    except Exception as e: return _err(e)

@mcp.tool(name="openalex_get_author_works", annotations={"readOnlyHint": True, "destructiveHint": False})
async def openalex_get_author_works(params: GAW) -> str:
    """Get publications by a specific author using their OpenAlex ID."""
    try:
        aid = params.author_id if params.author_id.startswith("A") else f"A{params.author_id}"
        d = await _get("works", {"filter": f"author.id:{aid}", "sort": "cited_by_count:desc" if params.sort_by=="cited_by_count" else "publication_year:desc", "per-page": params.per_page})
        return json.dumps({"author_id": aid, "total_works": d.get("meta",{}).get("count",0), "works": [_fmt(w) for w in d.get("results",[])]}, indent=2)
    except Exception as e: return _err(e)

@mcp.tool(name="openalex_get_cited_by", annotations={"readOnlyHint": True, "destructiveHint": False})
async def openalex_get_cited_by(params: CB) -> str:
    """Find works that cite a specific paper."""
    try:
        wid = params.work_id if params.work_id.startswith("W") else f"W{params.work_id}"
        d = await _get("works", {"filter": f"cites:{wid}", "sort": "cited_by_count:desc", "per-page": params.per_page})
        return json.dumps({"source_work_id": wid, "total_citing": d.get("meta",{}).get("count",0), "works": [_fmt(w) for w in d.get("results",[])]}, indent=2)
    except Exception as e: return _err(e)

if __name__ == "__main__":
    import os, uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    port = int(os.environ.get("PORT", 8000))
    sse = SseServerTransport("/messages/")
    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp._mcp_server.run(streams[0], streams[1], mcp._mcp_server.create_initialization_options())
    starlette_app = Starlette(routes=[Route("/sse", endpoint=handle_sse), Mount("/messages/", app=sse.handle_post_message)])
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
