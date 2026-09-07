"""RAG + (있으면) QLoRA 어댑터를 붙인, 특정 캐릭터와 대화하는 CLI 챗봇.

질문 -> rag/retriever.py로 그 캐릭터의 문서 검색 -> 검색 결과를 프롬프트에 주입 ->
configs/model.yaml에 지정된 모델(+ 캐릭터 어댑터가 있으면 적용)로, 그 캐릭터의
persona.md 말투로 답변 생성.

실행: python agent/app.py [--character odysseus]
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Windows 콘솔은 기본 코드페이지(cp949 등)로 stdin/stdout을 열어서, 리다이렉트/파이프로
# UTF-8 한글 입력이 들어오면 깨진 서로게이트 문자로 디코딩됨 -> 강제로 UTF-8 지정.
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

import characters
from config import load_config
from rag.retriever import retrieve


def load_model(cfg: dict, character: str):
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"])

    if cfg["load_in_4bit"]:
        from transformers import BitsAndBytesConfig

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model = AutoModelForCausalLM.from_pretrained(
            cfg["base_model"], quantization_config=bnb_config, device_map="auto"
        )
    else:
        # device_map="auto"는 GPU가 없으면 accelerate가 불필요하게 디스크 오프로드를 시도해서
        # 느려지고 오작동할 수 있음 -> CUDA 없을 땐 device_map 없이 그냥 CPU에 로드.
        if torch.cuda.is_available():
            model = AutoModelForCausalLM.from_pretrained(
                cfg["base_model"], dtype=torch.bfloat16, device_map="auto"
            )
        else:
            model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], dtype=torch.float32)

    adapter_dir = characters.adapter_dir(character)
    if adapter_dir.exists():
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(adapter_dir))
        print(f"[{character}] 파인튜닝 어댑터 적용됨: {adapter_dir}")
    else:
        print(f"[{character}] base 모델만 사용 중 (어댑터 없음: {adapter_dir})")

    return model, tokenizer


def build_prompt(tokenizer, persona: str, question: str, context_chunks: list[str]) -> str:
    context = "\n\n".join(f"[문서 {i+1}] {c}" for i, c in enumerate(context_chunks))
    user_content = f"참고 문서:\n{context}\n\n질문: {question}"
    messages = [
        {"role": "system", "content": persona},
        {"role": "user", "content": user_content},
    ]
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def main(character: str):
    cfg = load_config()
    persona = characters.load_persona(character)
    model, tokenizer = load_model(cfg, character)
    device = next(model.parameters()).device

    print(f"[{character}] 질문을 입력하세요 (종료: exit)")
    while True:
        question = input("\n> ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue

        context_chunks = retrieve(question, character, cfg)
        prompt = build_prompt(tokenizer, persona, question, context_chunks)
        inputs = tokenizer(prompt, return_tensors="pt").to(device)

        output = model.generate(
            **inputs,
            max_new_tokens=cfg["max_new_tokens"],
            do_sample=False,
        )
        answer = tokenizer.decode(output[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
        print(f"\n{answer}")


if __name__ == "__main__":
    cfg = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--character", default=cfg["active_character"])
    args = parser.parse_args()
    main(args.character)
