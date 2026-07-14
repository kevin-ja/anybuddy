import json
import os
from typing import Literal
from langchain_core.tools import tool
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
from app.config import settings
from model_loader.embedding import ensure_embedding_model
from model_loader.reranker import ensure_reranker_model


# =====================================================================
# CONFIGURACIÓN DE RUTAS Y SETTINGS PROPIOS
# =====================================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINKS_JSON_PATH = os.path.join(BASE_DIR, "data", "links.json")
CALENDAR_JSON_PATH = os.path.join(BASE_DIR, "data", "calendar.json")

CHROMA_HOST = settings.chroma_host
CHROMA_PORT = settings.chroma_port

CHROMA_COLLECTION_NAME = settings.chroma_collection_name
RERANKER_BEST_N_CHUNKS = settings.reranker_best_n_chunks

embedding_dir = ensure_embedding_model(
    settings.models_cache_dir,
    bucket=settings.s3_bucket_name,
    key=settings.embedding_model_s3_key,
    region=settings.aws_region,
)

reranker_dir = ensure_reranker_model(
    settings.models_cache_dir,
    bucket=settings.s3_bucket_name,
    key=settings.reranker_model_s3_key,
    region=settings.aws_region,
)

EMBEDDING_MODEL = SentenceTransformer(str(embedding_dir))
RERANKER_MODEL  = CrossEncoder(str(reranker_dir))


AllowedResources = Literal[
    "theoretical_classes", "practical_classes", "notion_dashboard"
]

AllowedSprints = Literal[
    "sprint_1",
    "sprint_2",
    "sprint_3",
    "sprint_4",
]


@tool
def get_class_link(resource_id: AllowedResources) -> str:
    """
    Useful to find links to recordings, live classes, or platforms.

    Instructions for the LLM:
    - If the user asks for theory, magistral, or 'clases de teoría', choose 'theoretical_classes'.
    - If the user asks for Alfredo, practice, labs, or 'clases prácticas', choose 'practical_classes'.
    - If the user asks for Notion or platform, choose 'notion_dashboard'.
    """
    try:
        with open(LINKS_JSON_PATH, "r", encoding="utf-8") as file:
            links_db = json.load(file)
    except FileNotFoundError:
        return "System Error: Database unavailable."

    for resource in links_db:
        if resource["id"] == resource_id:
            friendly_name = resource_id.replace("_", " ").title()
            return f"Here is the link for {friendly_name}: {resource['url']}"

    return "I couldn't find that specific resource."


@tool
def get_sprint_deadline(sprint_id: AllowedSprints) -> str:
    """
    Useful to find the exact due date or deadline for projects and sprints.

    Input should be the sprint identifier:
    - sprint_1
    - sprint_2
    - sprint_3
    - sprint_4
    """
    try:
        with open(CALENDAR_JSON_PATH, "r", encoding="utf-8") as file:
            calendar_db = json.load(file)
    except FileNotFoundError:
        return "System Error: Calendar database unavailable."

    query = sprint_id.lower().strip()

    for sprint in calendar_db:
        if sprint["id"] == query:
            friendly_name = query.replace("_", " ").title()
            return f"The deadline for {friendly_name} is {sprint['date']}."

    return f"I couldn't find the deadline for '{sprint_id}'."


@tool
def search_academy_faqs(student_question: str) -> str:
    """
    Useful when the student asks general questions about academy policies,
    grading systems, regulations, what happens if they fail a sprint,
    pair programming rules, squads, or how final projects are assigned.
    """
    try:
        # 1. Conexión por red usando tus configuraciones inyectadas de Pydantic
        chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        collection = chroma_client.get_collection(name=CHROMA_COLLECTION_NAME)

        # 2. Reutilización instantánea del modelo de embedding global
        query_vector = EMBEDDING_MODEL.encode(
            student_question, convert_to_numpy=True
        ).tolist()

        # 3. Extraer un espectro amplio de 8 candidatos para contrarrestar el ruido semántico
        db_results = collection.query(query_embeddings=[query_vector], n_results=8)
        retrieved_chunks = db_results["documents"][0]

        if not retrieved_chunks:
            return "No specific regulation found matching your question in the institutional repository."

        # 4. Reutilización instantánea del Reranker global
        pairs = [[student_question, chunk] for chunk in retrieved_chunks]
        reranker_scores = RERANKER_MODEL.predict(pairs)

        # 5. Reordenar los resultados de mayor a menor coincidencia semántica pura
        scored_docs = sorted(
            zip(reranker_scores, retrieved_chunks), key=lambda x: x[0], reverse=True
        )

        # 6. Filtrar usando el número de cortes estricto de tus settings
        top_clean_chunks = [doc for score, doc in scored_docs[:RERANKER_BEST_N_CHUNKS]]

        # Unificar el contexto en un único string limpio para el contexto de LangGraph
        return "\n\n---\n\n".join(top_clean_chunks)

    except Exception as e:
        # Blindaje ante caídas de ChromaDB
        return f"[Knowledge Base Error]: Temporarily unable to retrieve regulations. Details: {str(e)}"


# Lista de herramientas que expondremos al Agente
ANYBUDDY_TOOLS = [get_class_link, get_sprint_deadline, search_academy_faqs]
