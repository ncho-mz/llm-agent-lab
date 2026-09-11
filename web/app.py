"""캐릭터 대화 웹 앱 (Gradio).

화면 구성:
  - 상단: 캐릭터 선택 (가장 눈에 띄는 자리)
  - 왼쪽: 캐릭터 스크립트(persona.md) 편집 + 참고 문서 업로드 -> RAG 인덱스 재생성
  - 오른쪽: 캐릭터와의 대화 (대화 기억 유지)
  - 접힌 섹션: 어댑터/외부검색 토글 (파인튜닝 효과 A/B 비교용 실험 스위치)

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

from agent.engine import CharacterEngine
from core import characters
from core.config import load_config
from rag.build_index import build_index
from rag.ingest import fetch_url_to_docs
from web import avatar

engine: CharacterEngine | None = None
cfg = load_config()


def character_choices() -> list[tuple[str, str]]:
    """(화면에 보이는 한글 이름, 폴더 이름) 목록."""
    folders = sorted(d.name for d in characters.CHARACTERS_DIR.iterdir() if d.is_dir())
    folders = folders or [cfg["active_character"]]
    return [(characters.load_display_name(f), f) for f in folders]


def load_persona_text(character: str) -> str:
    path = characters.persona_path(character)
    return path.read_text(encoding="utf-8") if path.exists() else ""


def save_persona(character: str, label: str, text: str) -> str:
    if not text.strip():
        return "⚠️ 페르소나가 비어 있습니다."
    characters.persona_path(character).write_text(text, encoding="utf-8")
    if label.strip():
        characters.save_display_name(character, label)
    return "✅ 저장했습니다. 다음 대화부터 반영됩니다. (이름 변경은 새로고침 후 목록에 보여요)"


def upload_docs(character: str, files: list | None) -> str:
    """파일을 저장하고 곧바로 검색 인덱스까지 다시 만든다.

    인덱싱을 사용자가 따로 눌러야 하면, 올려놓고 왜 답에 반영이 안 되는지 헷갈리게 된다.
    """
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
    return f"✅ {len(saved)}개 추가: {', '.join(saved)}\n\n{reindex(character)}"


def add_link(character: str, url: str) -> str:
    """링크의 본문을 가져와 자료로 저장하고 곧바로 인덱싱한다."""
    if not url or not url.strip():
        return "⚠️ 주소를 입력하세요."
    ok, message = fetch_url_to_docs(url, characters.docs_dir(character))
    if not ok:
        return message
    return f"{message}\n\n{reindex(character)}"


def reindex(character: str) -> str:
    try:
        n = build_index(character, cfg)
    except SystemExit as e:
        return f"⚠️ {e}"
    return f"✅ 이제 이 자료를 참고해서 답합니다 ({n}개 조각으로 정리됨)"


def index_status(character: str) -> str:
    if characters.chroma_dir(character).exists():
        return ""
    return "⚠️ 아직 자료가 정리되지 않았습니다. 아래 '자료 다시 정리'를 눌러주세요."


def on_character_change(character: str):
    return (
        avatar.render(character),
        characters.load_display_name(character),
        load_persona_text(character),
        index_status(character),
        [],
    )


def respond(
    message: str, history: list[dict], character: str, use_adapter: bool, allow_external: bool
):
    if not message.strip():
        return history, ""
    answer = engine.chat(
        character, message, history, use_adapter=use_adapter, allow_external=allow_external
    )
    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ]
    return history, ""


def build_ui() -> gr.Blocks:
    choices = character_choices()
    default = cfg["active_character"]
    if default not in [value for _, value in choices]:
        default = choices[0][1]

    with gr.Blocks(title="Character Chat") as demo:
        gr.Markdown("# 캐릭터와 대화하기")
        character = gr.Radio(
            choices=choices, value=default, label="대화할 캐릭터를 고르세요", container=True
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 캐릭터 스크립트")
                display_name = gr.Textbox(
                    value=characters.load_display_name(default), label="표시 이름", max_lines=1
                )
                persona = gr.Textbox(
                    value=load_persona_text(default), lines=9, label="성격·말투 (persona.md)"
                )
                save_btn = gr.Button("저장")
                persona_status = gr.Markdown()

                with gr.Accordion("배경 지식 자료 (선택)", open=False):
                    gr.Markdown(
                        "이 캐릭터가 사실로 알고 있어야 할 내용을 올리세요. "
                        "질문마다 관련된 부분만 찾아서 답변에 반영됩니다."
                    )
                    link = gr.Textbox(
                        label="링크로 추가", placeholder="https://...", max_lines=1
                    )
                    link_btn = gr.Button("링크 가져오기", variant="primary")
                    uploader = gr.File(
                        file_count="multiple", file_types=[".md", ".txt"], label="파일로 추가 (.md/.txt)"
                    )
                    upload_btn = gr.Button("파일 올리기")
                    reindex_btn = gr.Button("자료 다시 정리", size="sm")
                    doc_status = gr.Markdown(value=index_status(default))

            with gr.Column(scale=2):
                avatar_view = gr.HTML(value=avatar.render(default))
                # gradio 6부터는 messages 형식(role/content 딕셔너리)이 기본이라 type 인자가 없다
                chatbot = gr.Chatbot(height=420, label="대화")
                msg = gr.Textbox(placeholder="캐릭터에게 말을 걸어보세요...", show_label=False)
                with gr.Row():
                    send_btn = gr.Button("보내기", variant="primary")
                    clear_btn = gr.Button("대화 기억 지우기")

        # 일반 사용자는 건드릴 일이 없지만, 파인튜닝 효과를 A/B로 비교하려면 필요해서 남겨둔다
        with gr.Accordion("실험 설정", open=False):
            use_adapter = gr.Checkbox(
                value=engine.has_adapter if engine else False,
                label="파인튜닝 어댑터 사용 (끄면 base 모델과 비교할 수 있어요)",
                interactive=bool(engine and engine.has_adapter),
            )
            allow_external = gr.Checkbox(
                value=True, label="외부 검색 보조 (문서로 답이 부족할 때 책/웹 검색)"
            )

        character.change(
            on_character_change,
            character,
            [avatar_view, display_name, persona, doc_status, chatbot],
        )
        save_btn.click(save_persona, [character, display_name, persona], persona_status).then(
            avatar.render, character, avatar_view
        )
        upload_btn.click(upload_docs, [character, uploader], doc_status)
        link_btn.click(add_link, [character, link], doc_status)
        reindex_btn.click(reindex, character, doc_status)

        msg.submit(respond, [msg, chatbot, character, use_adapter, allow_external], [chatbot, msg])
        send_btn.click(
            respond, [msg, chatbot, character, use_adapter, allow_external], [chatbot, msg]
        )
        clear_btn.click(lambda: [], None, chatbot)

    return demo


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default=None, help="어댑터 경로 (예: adapters/persona_skill)")
    parser.add_argument("--port", type=int, default=8111)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    engine = CharacterEngine(cfg, args.adapter)
    build_ui().launch(server_name=args.host, server_port=args.port, css=avatar.CSS)
