from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from app.routers import ingest, candidates, whatsapp, users
from app.services.scheduler import scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start automated 6-hour Google Drive sync scheduler
    scheduler.start()
    print("Automated 6-Hour Google Drive Sync Scheduler Started.")
    yield
    # Shutdown: Stop scheduler
    scheduler.stop()

app = FastAPI(
    title="AT BiZ API",
    description="Multi-Tenant Recruitment and Workforce Management Platform Backend",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for Next.js frontend (allow localhost, 127.0.0.1, and local LAN IPs)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(ingest.router)
app.include_router(candidates.router)
app.include_router(whatsapp.router)
app.include_router(users.router)

@app.get("/")
def home():
    return {
        "status": "success",
        "message": "AT BiZ Backend is running",
        "version": "1.0.0",
        "docs_url": "/docs"
    }

@app.post("/")
async def root_post_fallback(request: Request, background_tasks: BackgroundTasks):
    """Fallback handler in case external webhook callback is configured without path suffix"""
    from app.routers.whatsapp import handle_whatsapp_message
    return await handle_whatsapp_message(request, background_tasks)

@app.get("/health")
def health():
    return {"status": "healthy"}
