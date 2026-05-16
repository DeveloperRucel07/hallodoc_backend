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


class ChatRequest(BaseModel):
    message: str
    session_id: str 

class ChatResponse(BaseModel):
    response: str
    status: str

@app.post("/hallodoc/chat/", response_model=ChatResponse)
async def ai_chat(request: ChatRequest):
    try:
        result = client.chat(model=config.OLLAMA_MODEL, messages=[
            {
                'role': 'system',
                'content': promt
            },
            {
                'role': 'user',
                'content': request.message,
            },
        ])
        
        return ChatResponse(
            response=result['message']['content'],
            status="success"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))