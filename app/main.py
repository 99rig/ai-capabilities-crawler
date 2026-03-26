import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app import db
from app.api import search, jobs, patterns
from app.patterns.registry import discover_patterns

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    discover_patterns()
    yield
    await db.close()


app = FastAPI(title="AI Capabilities Crawler", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
)

app.include_router(search.router)
app.include_router(jobs.router)
app.include_router(patterns.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def dashboard():
    return FileResponse("app/static/index.html")
