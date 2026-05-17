from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.core.config import config
from app.prompts.system_prompt import system_prompt as promt
from ollama import Client
app = FastAPI(title="HalloDOC API")
client = Client(
    host=config.OLLAMA_BASE_URL
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "HalloDOC Backend ist online"}
