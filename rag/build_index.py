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


def _merge_headings(paragraphs: list[str]) -> list[str]:
    """마크다운 제목 줄을 바로 뒤 문단에 붙인다.

    제목만 있는 짧은 조각("# 제이 개츠비 인물 설정")은 내용이 거의 없어서 엉뚱한 질문에도
    높은 유사도가 나온다 -- 실제로 "오늘 서울 날씨" 질문이 이런 제목 조각에 0.949로 매칭됐다.
    """
    merged: list[str] = []
    pending_heading = ""
    for para in paragraphs:
        if para.startswith("#") and "\n" not in para:
            pending_heading = f"{pending_heading}\n{para}".strip()
            continue
        merged.append(f"{pending_heading}\n{para}".strip() if pending_heading else para)
        pending_heading = ""
    if pending_heading:
        merged.append(pending_heading)
    return merged


def chunk_text(text: str, max_chars: int, overlap: int, min_chars: int = 0) -> list[str]:
    """문단 단위로 자르되, 긴 문단은 overlap만큼 겹치게 슬라이딩해서 쪼갠다.

    겹침이 없으면 문장 중간에서 잘린 조각이 맥락을 잃는다 -- 프로필 문서 몇 조각일 땐
    티가 안 나지만, 소설 한 권처럼 수백~수천 조각이 되면 검색 품질을 크게 떨어뜨린다.
    """
    if overlap >= max_chars:
        raise ValueError(f"chunk_overlap({overlap})은 chunk_size({max_chars})보다 작아야 합니다.")

    paragraphs = _merge_headings([p.strip() for p in text.split("\n\n") if p.strip()])

    chunks = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
            continue

        step = max_chars - overlap
        for start in range(0, len(paragraph), step):
            chunks.append(paragraph[start : start + max_chars])
            if start + max_chars >= len(paragraph):
                break

    # 너무 짧은 조각은 내용이 없어 유사도가 불안정하므로 버린다
    return [c for c in chunks if len(c) >= min_chars]


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
            min_chars=cfg.get("min_chunk_chars", 0),
        )
        for idx, chunk in enumerate(pieces):
            ids.append(f"{file.stem}-{idx}")
            texts.append(chunk)
            metadatas.append({"source": file.name})

    print(f"[{character}] {len(files)}개 문서 -> {len(texts)}개 청크")

    embedder = SentenceTransformer(cfg["embedding_model"])
    # 정규화 + 코사인 거리로 맞춰야 distance = 1 - 유사도가 되어, 임계값을 사람이 해석할 수 있다
    embeddings = embedder.encode(texts, show_progress_bar=True, normalize_embeddings=True).tolist()

    client = chromadb.PersistentClient(path=str(characters.chroma_dir(character)))
    if COLLECTION_NAME in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)
    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    print(f"[{character}] 인덱스 저장 완료: {characters.chroma_dir(character)}")
    return len(texts)


if __name__ == "__main__":
    cfg = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--character", default=cfg["active_character"])
    args = parser.parse_args()
    build_index(args.character, cfg)
