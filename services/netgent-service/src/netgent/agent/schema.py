from pydantic import BaseModel
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage


class NetGentState(BaseModel):
    specification: str
    model: str = "gpt-4o-mini"
    response: str | None = None


def call_llm(state: NetGentState) -> dict[str, str]:
    model = init_chat_model(model=state.model)
    response = model.invoke([HumanMessage(content=state.specification)])
    return {"response": str(response.content)}
