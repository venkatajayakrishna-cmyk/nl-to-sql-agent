from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import agent  # import your already-built agent object

app = FastAPI(title="NL-to-SQL Data Analyst Agent")


import uuid
from typing import Optional

class QuestionRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class AnswerResponse(BaseModel):
    answer: str
    session_id: str


@app.post("/ask", response_model=AnswerResponse)
def ask_question(request: QuestionRequest):
    session_id = request.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    try:
        response = agent.invoke(
            {"messages": [{"role": "user", "content": request.question}]},
            config=config,
        )
        final_message = response["messages"][-1]

        if isinstance(final_message.content, list):
            answer_text = final_message.content[0].get("text", "")
        else:
            answer_text = final_message.content

        return AnswerResponse(answer=answer_text, session_id=session_id)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent failed to process the question: {str(e)}")


@app.get("/health")
def health_check():
    return {"status": "ok"}