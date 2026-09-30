import re
import joblib

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import KNOWLEDGE_DIR, RAG_INDEX_PATH


# ============================================================
# READ DOCUMENTS
# ============================================================

def load_documents():

    documents = []

    for file_path in KNOWLEDGE_DIR.glob("*.txt"):

        text = file_path.read_text(
            encoding="utf-8"
        )

        text = text.strip()

        if not text:
            continue

        documents.append(
            {
                "source": file_path.name,
                "text": text,
            }
        )

    return documents


# ============================================================
# SPLIT DOCUMENT INTO CHUNKS
# ============================================================

def split_text(
    text,
    chunk_size=700,
    overlap=100
):

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        chunk = text[start:end]

        chunks.append(
            chunk
        )

        start = end - overlap

        if start < 0:
            start = 0

    return chunks


# ============================================================
# BUILD RAG INDEX
# ============================================================

def build_index():

    documents = load_documents()

    if not documents:

        raise ValueError(
            "No knowledge documents found."
        )

    chunks = []

    for document in documents:

        document_chunks = split_text(
            document["text"]
        )

        for chunk in document_chunks:

            chunks.append(
                {
                    "source": document["source"],
                    "text": chunk,
                }
            )

    texts = [
        item["text"]
        for item in chunks
    ]

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        max_features=10000
    )

    matrix = vectorizer.fit_transform(
        texts
    )

    index = {

        "vectorizer": vectorizer,

        "matrix": matrix,

        "chunks": chunks,
    }

    joblib.dump(
        index,
        RAG_INDEX_PATH
    )

    return index


# ============================================================
# LOAD INDEX
# ============================================================

def load_index():

    if not RAG_INDEX_PATH.exists():

        return build_index()

    return joblib.load(
        RAG_INDEX_PATH
    )


# ============================================================
# RETRIEVE
# ============================================================

def retrieve(
    query,
    top_k=3
):

    index = load_index()

    vectorizer = index[
        "vectorizer"
    ]

    matrix = index[
        "matrix"
    ]

    chunks = index[
        "chunks"
    ]

    query_vector = vectorizer.transform(
        [query]
    )

    similarities = cosine_similarity(
        query_vector,
        matrix
    )[0]

    ranked_indices = similarities.argsort()[
        ::-1
    ]

    results = []

    for index_position in ranked_indices[
        :top_k
    ]:

        score = float(
            similarities[index_position]
        )

        chunk = chunks[
            index_position
        ]

        results.append(
            {
                "source": chunk["source"],
                "score": round(
                    score,
                    4
                ),
                "text": chunk["text"],
            }
        )

    return results


# ============================================================
# FORMAT CONTEXT
# ============================================================

def get_context(
    query,
    top_k=3
):

    results = retrieve(
        query,
        top_k
    )

    if not results:

        return "No relevant knowledge found."

    context_parts = []

    for result in results:

        context_parts.append(
            (
                f"SOURCE: {result['source']}\n"
                f"RELEVANCE: {result['score']}\n"
                f"CONTENT:\n{result['text']}"
            )
        )

    return "\n\n---\n\n".join(
        context_parts
    )