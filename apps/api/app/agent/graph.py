import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_openai import (
    ChatOpenAI,
)  # Puedes cambiarlo por ChatAnthropic o ChatGoogleGenerativeAI

from app.agent.state import AnyBuddyState
from app.agent.tools import ANYBUDDY_TOOLS

# Cargar variables de entorno (como OPENAI_API_KEY)
load_dotenv()

# 1. Configurar el LLM y "vincularle" las herramientas
# Usamos un modelo económico y rápido, ideal para tareas administrativas
model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
model_with_tools = model.bind_tools(ANYBUDDY_TOOLS)


# 2. Definir los Nodos del Grafo
def call_model(state: AnyBuddyState):
    """
    Nodo del Agente: Pasa el historial de mensajes al LLM (con las herramientas vinculadas)
    y devuelve la decisión del modelo.
    """
    messages = state["messages"]

    # Mensaje de sistema para darle el contexto institucional de Anyone AI
    system_prompt = (
        "You are AnyBuddy, the friendly and professional AI assistant for Anyone AI academy. "
        "Your goal is to help students with deadlines, class links, and academy policies. "
        "Always answer clearly, politely, and in English. Use the provided tools to fetch "
        "accurate information before answering. If you don't know the answer and no tool "
        "can provide it, ask the student to contact human support."
    )

    # Insertar el system prompt al inicio sin alterar el estado original
    messages_with_system = [{"role": "system", "content": system_prompt}] + messages

    response = model_with_tools.invoke(messages_with_system)

    # Devolvemos el mensaje del LLM para que se agregue al estado
    return {"messages": [response]}


# 3. Definir la lógica de enrutamiento (Conditional Edge)


def should_continue(state: AnyBuddyState):
    """
    Función que evalúa si el LLM decidió llamar a una herramienta o responder directamente.
    """
    last_message = state["messages"][-1]

    # Si el último mensaje del LLM contiene 'tool_calls', significa que necesita ejecutar una herramienta
    if last_message.tool_calls:
        return "tools"

    # Si no hay llamadas a herramientas, terminamos el flujo
    return END


# 4. Construir y Compilar el Grafo ------------------------------------------

# Inicializamos el grafo con nuestra estructura de estado
workflow = StateGraph(AnyBuddyState)

# Añadimos los nodos principales
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(ANYBUDDY_TOOLS))

# Establecemos el punto de entrada
workflow.add_edge(START, "agent")

# Añadimos el camino condicional desde el agente
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "tools",
        END: END,
    },
)

workflow.add_edge("tools", "agent")

# Compilamos el grafo
anybuddy_graph = workflow.compile()
