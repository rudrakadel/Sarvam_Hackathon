"""
VeriDictum AI — Natural Language Query Service
RAG over case corpus using OpenAI embeddings + Pinecone vector search.
Fallback to PostgreSQL full-text search when Pinecone unavailable.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Document, Transcript, TranscriptSegment

logger = logging.getLogger(__name__)

openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

NL_QUERY_SYSTEM_PROMPT = """You are a legal AI assistant helping attorneys analyse courtroom transcripts and documentary evidence.

Answer the attorney's question using ONLY information found in the provided sources below.
Cite each piece of information with [SOURCE: type=transcript|document, id=..., speaker=..., timestamp=..., page=...].

If the answer is not found in the sources, say "This information was not found in the available case materials."

Be precise, factual, and professional. Do not speculate beyond what is in the sources."""


async def answer_nl_query(
    db: AsyncSession,
    case_id: UUID,
    query: str,
) -> Tuple[str, List[Dict[str, Any]], int, str]:
    """
    Answer a natural language query against the case corpus.
    Returns (answer, citations, tokens_used, model_used).
    """
    # --- Retrieve relevant context ---
    context_chunks = await _retrieve_context(db, case_id, query)

    if not context_chunks:
        return (
            "No case materials are available yet. Please ensure transcripts and documents have been processed.",
            [],
            0,
            settings.OPENAI_MODEL,
        )

    # --- Build prompt ---
    sources_block = "\n\n".join(
        f"[SOURCE: type={c['type']}, id={c['id']}, speaker={c.get('speaker','N/A')}, "
        f"timestamp={c.get('timestamp','N/A')}, page={c.get('page','N/A')}]\n{c['text']}"
        for c in context_chunks
    )

    # --- Query OpenAI ---
    try:
        response = await openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": NL_QUERY_SYSTEM_PROMPT},
                {"role": "user", "content": f"QUESTION: {query}\n\nSOURCES:\n{sources_block}"},
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        answer = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0
    except Exception as e:
        logger.warning(f"OpenAI query failed: {e}")
        answer = "The AI service is temporarily unavailable. Please try again later."
        tokens = 0

    # --- Extract citations ---
    citations = []
    for chunk in context_chunks:
        citations.append({
            "source_type": chunk["type"],
            "source_id": chunk["id"],
            "speaker": chunk.get("speaker"),
            "timestamp": chunk.get("timestamp"),
            "page": chunk.get("page"),
            "excerpt": chunk["text"][:200],
        })

    return answer, citations, tokens, settings.OPENAI_MODEL


async def _retrieve_context(
    db: AsyncSession,
    case_id: UUID,
    query: str,
    max_chunks: int = 20,
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant context chunks.
    Priority: Pinecone vector search → PostgreSQL full-text fallback.
    """
    try:
        return await _pinecone_search(case_id, query, max_chunks)
    except Exception as e:
        logger.warning(f"Pinecone search failed, falling back to PostgreSQL: {e}")
        return await _postgres_fulltext_search(db, case_id, query, max_chunks)


async def _pinecone_search(
    case_id: UUID,
    query: str,
    max_chunks: int,
) -> List[Dict[str, Any]]:
    """Vector search in Pinecone using OpenAI embeddings."""
    if not settings.PINECONE_API_KEY:
        raise RuntimeError("Pinecone not configured")

    # Embed query
    embed_response = await openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query,
    )
    query_vector = embed_response.data[0].embedding

    from pinecone import Pinecone
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    index = pc.Index(settings.PINECONE_INDEX_NAME)

    results = index.query(
        vector=query_vector,
        top_k=max_chunks,
        filter={"case_id": str(case_id)},
        include_metadata=True,
    )

    chunks = []
    for match in results.matches:
        meta = match.metadata or {}
        chunks.append({
            "id": meta.get("source_id", match.id),
            "type": meta.get("source_type", "unknown"),
            "text": meta.get("text", ""),
            "speaker": meta.get("speaker"),
            "timestamp": meta.get("timestamp"),
            "page": meta.get("page"),
            "score": match.score,
        })
    return chunks


async def _postgres_fulltext_search(
    db: AsyncSession,
    case_id: UUID,
    query: str,
    max_chunks: int,
) -> List[Dict[str, Any]]:
    """
    Full-text search against PostgreSQL using native tsvector/tsquery.
    Falls back to returning ALL case content when FTS yields nothing,
    so GPT always has material to answer from.
    """
    chunks = []
    case_id_str = str(case_id)
    half = max(1, max_chunks // 2)

    # --- Pass 1: PostgreSQL native full-text search ---
    try:
        seg_fts = await db.execute(
            text("""
                SELECT ts.id, ts.text, ts.speaker_name, ts.speaker_label, ts.start_time,
                       ts_rank(to_tsvector('english', ts.text),
                               plainto_tsquery('english', :query)) AS rank
                FROM transcript_segments ts
                JOIN transcripts t ON ts.transcript_id = t.id
                WHERE t.case_id = :case_id
                  AND to_tsvector('english', ts.text)
                      @@ plainto_tsquery('english', :query)
                ORDER BY rank DESC
                LIMIT :limit
            """),
            {"query": query, "case_id": case_id_str, "limit": half},
        )
        for row in seg_fts:
            chunks.append({
                "id": str(row.id),
                "type": "transcript",
                "text": row.text,
                "speaker": row.speaker_name or row.speaker_label,
                "timestamp": float(row.start_time) if row.start_time else None,
                "page": None,
            })

        doc_fts = await db.execute(
            text("""
                SELECT id, original_filename, extracted_text,
                       ts_rank(to_tsvector('english', coalesce(extracted_text, '')),
                               plainto_tsquery('english', :query)) AS rank
                FROM documents
                WHERE case_id = :case_id
                  AND extracted_text IS NOT NULL
                  AND to_tsvector('english', coalesce(extracted_text, ''))
                      @@ plainto_tsquery('english', :query)
                ORDER BY rank DESC
                LIMIT :limit
            """),
            {"query": query, "case_id": case_id_str, "limit": half},
        )
        for row in doc_fts:
            text_val = row.extracted_text or ""
            # Find the most relevant 600-char window
            query_words = [w.lower() for w in query.split() if len(w) > 3]
            best_idx = 0
            for word in query_words:
                idx = text_val.lower().find(word)
                if idx >= 0:
                    best_idx = idx
                    break
            snippet = text_val[max(0, best_idx - 100): best_idx + 500]
            chunks.append({
                "id": str(row.id),
                "type": "document",
                "text": snippet.strip() or text_val[:600],
                "speaker": None,
                "timestamp": None,
                "page": 1,
            })
    except Exception as e:
        logger.warning(f"PG FTS query failed: {e}")

    # --- Pass 2: Keyword LIKE fallback if FTS returned nothing ---
    if not chunks:
        stop_words = {"what", "when", "where", "which", "that", "this", "with", "from",
                      "have", "does", "about", "between", "their", "there", "were", "been"}
        keywords = [w.lower() for w in query.split() if len(w) >= 4 and w.lower() not in stop_words]

        for keyword in keywords[:5]:
            like_kw = f"%{keyword}%"
            try:
                kw_segs = await db.execute(
                    text("""
                        SELECT ts.id, ts.text, ts.speaker_name, ts.speaker_label, ts.start_time
                        FROM transcript_segments ts
                        JOIN transcripts t ON ts.transcript_id = t.id
                        WHERE t.case_id = :case_id AND lower(ts.text) LIKE :kw
                        LIMIT 3
                    """),
                    {"kw": like_kw, "case_id": case_id_str},
                )
                for row in kw_segs:
                    entry = {
                        "id": str(row.id),
                        "type": "transcript",
                        "text": row.text,
                        "speaker": row.speaker_name or row.speaker_label,
                        "timestamp": float(row.start_time) if row.start_time else None,
                        "page": None,
                    }
                    if entry not in chunks:
                        chunks.append(entry)
            except Exception:
                pass

    # --- Pass 3: Full-case fallback — always give GPT something to work with ---
    if not chunks:
        logger.info("No FTS/keyword matches — returning full case content for RAG")

        all_segs = await db.execute(
            text("""
                SELECT ts.id, ts.text, ts.speaker_name, ts.speaker_label, ts.start_time
                FROM transcript_segments ts
                JOIN transcripts t ON ts.transcript_id = t.id
                WHERE t.case_id = :case_id
                ORDER BY ts.start_time
                LIMIT :limit
            """),
            {"case_id": case_id_str, "limit": half},
        )
        for row in all_segs:
            chunks.append({
                "id": str(row.id),
                "type": "transcript",
                "text": row.text,
                "speaker": row.speaker_name or row.speaker_label,
                "timestamp": float(row.start_time) if row.start_time else None,
                "page": None,
            })

        all_docs = await db.execute(
            text("""
                SELECT id, original_filename, extracted_text
                FROM documents
                WHERE case_id = :case_id AND extracted_text IS NOT NULL
                LIMIT :limit
            """),
            {"case_id": case_id_str, "limit": half},
        )
        for row in all_docs:
            chunks.append({
                "id": str(row.id),
                "type": "document",
                "text": (row.extracted_text or "")[:1500],
                "speaker": None,
                "timestamp": None,
                "page": 1,
            })

    return chunks[:max_chunks]
