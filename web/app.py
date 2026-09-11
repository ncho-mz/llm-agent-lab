"""캐릭터 대화 웹 앱 (Gradio).

원래 구상한 화면 구성 그대로:
  - 왼쪽 위: 캐릭터 스크립트(persona.md) 편집
  - 왼쪽 아래: 참고 문서 업로드 -> RAG 인덱스 재생성
  - 오른쪽: 캐릭터와의 대화 (대화 기억 유지)
여기에 실험용으로 파인튜닝 어댑터 ON/OFF 토글을 추가했다.

실행: python web/app.py [--adapter adapters/persona_skill] [--port 8111]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import gradio as gr

import characters
from agent.engine import CharacterEngine
from config import load_config
from rag.build_index import build_index

engine: CharacterEngine | None = None
cfg = load_config()


def list_characters() -> list[str]:
    names = sorted(d.name for d in characters.CHARACTERS_DIR.iterdir() if d.is_dir())
    return names or [cfg["active_character"]]


def load_persona_text(character: str) -> str:
    path = characters.persona_path(character)
    return path.read_text(encoding="utf-8") if path.exists() else ""


def save_persona(character: str, text: str) -> str:
    if not text.strip():
        return "⚠️ 페르소나가 비어 있습니다."
    characters.persona_path(character).write_text(text, encoding="utf-8")
    return "✅ 저장했습니다. 다음 대화부터 바로 반영됩니다."


def upload_docs(character: str, files: list | None) -> str:
    if not files:
        return "⚠️ 업로드할 파일을 선택하세요."
    docs_dir = characters.docs_dir(character)
    docs_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        src = Path(f.name if hasattr(f, "name") else f)
        if src.suffix.lower() not in {".md", ".txt"}:
            continue
        shutil.copy(src, docs_dir / src.name)
        saved.append(src.name)

    if not saved:
        return "⚠️ .md 또는 .txt 파일만 업로드할 수 있습니다."
    return f"✅ {len(saved)}개 저장: {', '.join(saved)}\n아래 '인덱스 재생성'을 눌러야 검색에 반영됩니다."


def reindex(character: str) -> str:
    try:
        n = build_index(character, cfg)
    except SystemExit as e:
        return f"⚠️ {e}"
    return f"✅ 인덱스 재생성 완료 — {n}개 청크"


def list_docs(character: str) -> str:
    docs_dir = characters.docs_dir(character)
    if not docs_dir.exists():
        return "(문서 없음)"
    names = sorted(p.name for p in docs_dir.iterdir() if p.suffix.lower() in {".md", ".txt"})
    return "\n".join(f"• {n}" for n in names) or "(문서 없음)"


def on_character_change(character: str):
    return load_persona_text(character), list_docs(character), []


def respond(message: str, history: list[dict], character: str, use_adapter: bool):
    if not message.strip():
        return history, ""
    answer = engine.chat(character, message, history, use_adapter=use_adapter)
    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ]
    return history, ""


def build_ui() -> gr.Blocks:
    names = list_characters()
    default = cfg["active_character"] if cfg["active_character"] in names else names[0]

    with gr.Blocks(title="Character Chat") as demo:
        gr.Markdown("# 캐릭터와 대화하기")

        with gr.Row():
            character = gr.Dropdown(names, value=default, label="캐릭터", scale=3)
            use_adapter = gr.Checkbox(
                value=engine.has_adapter if engine else False,
                label="파인튜닝 어댑터 사용",
                interactive=bool(engine and engine.has_adapter),
                scale=1,
            )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 캐릭터 스크립트")
                persona = gr.Textbox(
                    value=load_persona_text(default), lines=10, label="persona.md", show_label=False
                )
                save_btn = gr.Button("페르소나 저장")
                persona_status = gr.Markdown()

                gr.Markdown("### 참고 문서 (RAG)")
                doc_list = gr.Textbox(
                    value=list_docs(default), lines=4, label="등록된 문서", interactive=False
                )
                uploader = gr.File(file_count="multiple", file_types=[".md", ".txt"], label="업로드")
                with gr.Row():
                    upload_btn = gr.Button("문서 저장")
                    reindex_btn = gr.Button("인덱스 재생성", variant="primary")
                doc_status = gr.Markdown()

            with gr.Column(scale=2):
                # gradio 6부터는 messages 형식(role/content 딕셔너리)이 기본이라 type 인자가 없다
                chatbot = gr.Chatbot(height=520, label="대화")
                msg = gr.Textbox(placeholder="캐릭터에게 말을 걸어보세요...", show_label=False)
                with gr.Row():
                    send_btn = gr.Button("보내기", variant="primary")
                    clear_btn = gr.Button("대화 기억 지우기")

        character.change(on_character_change, character, [persona, doc_list, chatbot])
        save_btn.click(save_persona, [character, persona], persona_status)
        upload_btn.click(upload_docs, [character, uploader], doc_status).then(
            list_docs, character, doc_list
        )
        reindex_btn.click(reindex, character, doc_status)

        msg.submit(respond, [msg, chatbot, character, use_adapter], [chatbot, msg])
        send_btn.click(respond, [msg, chatbot, character, use_adapter], [chatbot, msg])
        clear_btn.click(lambda: [], None, chatbot)

    return demo


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default=None, help="어댑터 경로 (예: adapters/persona_skill)")
    parser.add_argument("--port", type=int, default=8111)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    engine = CharacterEngine(cfg, args.adapter)
    build_ui().launch(server_name=args.host, server_port=args.port)
