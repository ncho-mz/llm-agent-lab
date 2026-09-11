"""characters/<name>/docs 안의 문서를 임베딩해서 그 캐릭터 전용 Chroma 벡터 인덱스를 만든다.
CPU만으로도 충분히 빠르게 돈다 (임베딩 모델이 작아서 GPU 불필요).

실행: python rag/build_index.py [--character odysseus]
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# sentence_transformers를 chromadb보다 먼저 import해야 함 (retriever.py 참고: 반대 순서면 tokenizers 충돌)
from sentence_transformers import SentenceTransformer
import chromadb

import characters
from config import load_config

COLLECTION_NAME = "docs"


def chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """문단 단위로 자르되, 긴 문단은 overlap만큼 겹치게 슬라이딩해서 쪼갠다.

    겹침이 없으면 문장 중간에서 잘린 조각이 맥락을 잃는다 -- 프로필 문서 몇 조각일 땐
    티가 안 나지만, 소설 한 권처럼 수백~수천 조각이 되면 검색 품질을 크게 떨어뜨린다.
    """
    if overlap >= max_chars:
        raise ValueError(f"chunk_overlap({overlap})은 chunk_size({max_chars})보다 작아야 합니다.")

    chunks = []
    for paragraph in (p.strip() for p in text.split("\n\n")):
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
            continue

        step = max_chars - overlap
        for start in range(0, len(paragraph), step):
            chunks.append(paragraph[start : start + max_chars])
            if start + max_chars >= len(paragraph):
                break
    return chunks


def build_index(character: str, cfg: dict) -> int:
    docs_dir = characters.docs_dir(character)
    files = sorted(docs_dir.glob("*.md")) + sorted(docs_dir.glob("*.txt"))
    if not files:
        raise SystemExit(f"{docs_dir} 에 .md/.txt 문서가 없습니다.")

    ids, texts, metadatas = [], [], []
    for file in files:
        pieces = chunk_text(
            file.read_text(encoding="utf-8"),
            max_chars=cfg["chunk_size"],
            overlap=cfg["chunk_overlap"],
        )
        for idx, chunk in enumerate(pieces):
            ids.append(f"{file.stem}-{idx}")
            texts.append(chunk)
            metadatas.append({"source": file.name})

    print(f"[{character}] {len(files)}개 문서 -> {len(texts)}개 청크")

    embedder = SentenceTransformer(cfg["embedding_model"])
    embeddings = embedder.encode(texts, show_progress_bar=True).tolist()

    client = chromadb.PersistentClient(path=str(characters.chroma_dir(character)))
    if COLLECTION_NAME in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)
    collection = client.create_collection(COLLECTION_NAME)
    collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    print(f"[{character}] 인덱스 저장 완료: {characters.chroma_dir(character)}")
    return len(texts)


if __name__ == "__main__":
    cfg = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--character", default=cfg["active_character"])
    args = parser.parse_args()
    build_index(args.character, cfg)
