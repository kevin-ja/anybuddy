import chromadb
from sentence_transformers import SentenceTransformer
from src.config import settings
from src.sinks import publish_outputs
from src.sources import ensure_inputs

VECTOR_DATABASE_PATH = settings.vector_db_path

CHROMA_COLLECTION_NAME = settings.chroma_collection_name

HNSW_CONFIG = {
    "hnsw:space": settings.hnsw_space,
    "hnsw:M": settings.hnsw_m,
    "hnsw:construction_ef": settings.hnsw_construction_ef,
    "hnsw:search_ef": settings.hnsw_search_ef,
}


def smart_recursive_splitter(text, chunk_size=500, chunk_overlap=50):
    """
    Divide el texto de forma inteligente y recursiva sin romper palabras.
    Sigue la jerarquía: Párrafos -> Líneas -> Oraciones -> Espacios.
    """
    separators = ["\n\n", "\n", ". ", " "]

    def _split_recursive(block, current_sep_idx):
        # Si el bloque ya entra en el tamaño permitido, no hay que hacerle nada
        if len(block) <= chunk_size:
            return [block]

        # Si nos quedamos sin separadores lógicos, cortamos por caracteres (último recurso)
        if current_sep_idx >= len(separators):
            return [
                block[i : i + chunk_size]
                for i in range(0, len(block), chunk_size - chunk_overlap)
            ]

        sep = separators[current_sep_idx]
        if sep not in block:
            # Si este separador no existe en el bloque, saltamos al siguiente nivel de la jerarquía
            return _split_recursive(block, current_sep_idx + 1)

        # Dividir el texto usando el separador actual
        raw_splits = block.split(sep)
        final_splits = []

        for piece in raw_splits:
            if not piece:
                continue
            # Re-añadir el separador para mantener el formato original (excepto si es espacio)
            formatted_piece = piece + (sep if sep != " " else " ")

            if len(formatted_piece) > chunk_size:
                # Si el pedazo sigue siendo muy grande, lo mandamos a la picadora del siguiente nivel
                final_splits.extend(
                    _split_recursive(formatted_piece, current_sep_idx + 1)
                )
            else:
                final_splits.append(formatted_piece)

        return final_splits

    # 1. Obtener los fragmentos atómicos respetando la jerarquía
    atomic_pieces = _split_recursive(text, 0)

    # 2. Recombinar los fragmentos para llenar los chunks hasta el 'chunk_size' respetando el 'overlap'
    chunks = []
    current_chunk = ""

    for piece in atomic_pieces:
        # Si cabe el nuevo pedazo en el chunk actual, lo sumamos
        if len(current_chunk) + len(piece) <= chunk_size:
            current_chunk += piece
        else:
            # Si ya no cabe, guardamos el chunk que acumulamos
            if current_chunk:
                chunks.append(current_chunk.strip())

            # Calculamos el overlap tomando el final del chunk anterior
            if len(current_chunk) > chunk_overlap:
                overlap_text = current_chunk[-chunk_overlap:]
                # Intentamos no romper palabras en el overlap buscando el primer espacio limpio
                first_space = overlap_text.find(" ")
                if first_space != -1:
                    overlap_text = overlap_text[first_space:]
                current_chunk = overlap_text + piece
            else:
                current_chunk = piece

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def run_ingestion():

    # Resuelve inputs segun APP_ENV: en local valida disco, en prod baja de S3.
    inputs = ensure_inputs(settings)

    print(f"📖 Leyendo el knowledge base desde {inputs.knowledge_path}...")
    text = inputs.knowledge_path.read_text(encoding="utf-8")

    print("🧠 Ejecutando el Chunking Inteligente Nativo...")
    chunks = smart_recursive_splitter(text, chunk_size=500, chunk_overlap=50)

    print("🧠 Cargando el modelo de embedding...")
    model = SentenceTransformer(inputs.model_ref)

    print(f"🧬 Generando vectores para {len(chunks)} fragmentos...")
    embeddings = model.encode(chunks, convert_to_numpy=True).tolist()

    # Creación de la DB Vectorial con ChromaDB ---------------------------------------------

    # 5. Inicializar el cliente y pasar los parámetros sagrados en el metadata
    print("🗄️ Conectando al almacenamiento local de ChromaDB...")
    chroma_client = chromadb.PersistentClient(path=str(VECTOR_DATABASE_PATH))

    collection = chroma_client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        metadata=HNSW_CONFIG,
    )

    ids = [f"chunk_{i}" for i in range(len(chunks))]
    collection.add(ids=ids, embeddings=embeddings, documents=chunks)

    print("✅ ¡Ingesta completada!")
    publish_outputs(settings)


if __name__ == "__main__":
    run_ingestion()
