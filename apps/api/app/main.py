# app/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.agent.graph import anybuddy_graph  # <-- CAMBIÓ AQUÍ (Agregamos "app.")

app = FastAPI(title="AnyBuddy API")


class ChatRequest(BaseModel):
    message: str
    user_id: str


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        inputs = {"messages": [("user", request.message)]}
        config = {"configurable": {"thread_id": request.user_id}}

        resultado = await anybuddy_graph.ainvoke(inputs, config)

        respuesta_final = resultado["messages"][-1].content
        return {"response": respuesta_final}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
