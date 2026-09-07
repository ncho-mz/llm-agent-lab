"""build_index.py로 만든, 특정 캐릭터의 Chroma 인덱스에서 질의와 관련된 문서 조각을 검색한다."""
from __future__ import annotations  # `dict | None` 같은 3.10+ 문법을 3.9에서도 되게 함 (EC2 기본 파이썬 대응)

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# sentence_transformers를 chromadb보다 먼저 import해야 함:
# 반대 순서면 tokenizers 라이브러리가 충돌해서 encode() 호출 시 TypeError가 남.
from sentence_transformers import SentenceTransformer
import chromadb

import characters
from config import load_config

_embedder = None
_collections: dict[str, "chromadb.Collection"] = {}


def _get_embedder(cfg: dict) -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(cfg["embedding_model"])
    return _embedder


def _get_collection(character: str):
    if character not in _collections:
        client = chromadb.PersistentClient(path=str(characters.chroma_dir(character)))
        _collections[character] = client.get_collection("docs")
    return _collections[character]


def retrieve(query: str, character: str, cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_config()
    embedder = _get_embedder(cfg)
    collection = _get_collection(character)
    query_embedding = embedder.encode([query]).tolist()
    result = collection.query(query_embeddings=query_embedding, n_results=cfg["top_k"])
    return result["documents"][0] if result["documents"] else []


if __name__ == "__main__":
    cfg = load_config()
    for chunk in retrieve("가장 자랑스러운 업적이 뭔가요?", cfg["active_character"], cfg):
        print("-", chunk[:80])
