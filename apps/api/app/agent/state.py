from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AnyBuddyState(TypedDict):
    # 'add_messages' hace que cada nuevo mensaje se agregue a la lista en lugar de sobrescribirla
    messages: Annotated[list[AnyMessage], add_messages]
