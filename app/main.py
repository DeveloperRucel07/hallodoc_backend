from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from ollama import Client

from app.auth.auth_router import router as auth_router
from app.chat.chat_router import router as chat_router
from app.core.config import config
from app.models.database import init_db

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app = FastAPI(title="HalloDOC API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)

client = Client(host=config.OLLAMA_BASE_URL)

@app.get("/")
def read_root():
    return RedirectResponse(url="/patient/login")