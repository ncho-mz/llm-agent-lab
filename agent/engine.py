"""캐릭터 대화 엔진. CLI(agent/app.py)와 웹(web/app.py)이 공유한다.

모델 로딩이 몇 분 걸리므로 프로세스당 한 번만 로드하고, 캐릭터 전환은 페르소나와 RAG
인덱스만 바꿔 끼운다. 어댑터는 재로딩 없이 껐다 켤 수 있어(A/B 비교용) 파인튜닝 효과를
바로 확인할 수 있다.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

import characters
import obs
from config import load_config
from rag.retriever import retrieve

SYSTEM_TEMPLATE = """{persona}

아래는 당신에 관한 참고 문서입니다. 사실관계는 이 문서에 근거해서 답하고, 문서에 없는
내용은 지어내지 마세요. 문서의 문장을 그대로 읽지 말고, 반드시 당신의 말투로 바꿔 말하세요.

[참고 문서]
{context}"""


class CharacterEngine:
    def __init__(self, cfg: dict | None = None, adapter_path: str | None = None):
        self.cfg = cfg or load_config()
        self.tokenizer = AutoTokenizer.from_pretrained(self.cfg["base_model"])
        self.model = self._load_model()
        self.has_adapter = self._attach_adapter(adapter_path)
        self.device = next(self.model.parameters()).device

    def _load_model(self):
        if self.cfg["load_in_4bit"]:
            from transformers import BitsAndBytesConfig

            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )
            return AutoModelForCausalLM.from_pretrained(
                self.cfg["base_model"], quantization_config=bnb_config, device_map="auto"
            )

        # device_map="auto"는 GPU가 없으면 불필요한 디스크 오프로드를 시도하므로 CPU에선 생략
        if torch.cuda.is_available():
            return AutoModelForCausalLM.from_pretrained(
                self.cfg["base_model"], dtype=torch.bfloat16, device_map="auto"
            )
        return AutoModelForCausalLM.from_pretrained(self.cfg["base_model"], dtype=torch.float32)

    def _attach_adapter(self, adapter_path: str | None) -> bool:
        if not adapter_path:
            print("[engine] 어댑터 없이 base 모델만 사용")
            return False

        path = Path(adapter_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.exists():
            print(f"[engine] 어댑터 경로가 없어 base 모델만 사용: {path}")
            return False

        from peft import PeftModel

        self.model = PeftModel.from_pretrained(self.model, str(path))
        print(f"[engine] 어댑터 적용됨: {path}")
        return True

    @obs.retrieval(name="rag_search")
    def _search(self, character: str, question: str) -> list[str]:
        return retrieve(question, character, self.cfg)

    def build_messages(
        self, character: str, question: str, history: list[dict] | None, context_chunks: list[str]
    ) -> list[dict]:
        context = "\n\n".join(f"[문서 {i + 1}] {c}" for i, c in enumerate(context_chunks)) or "(없음)"
        system = SYSTEM_TEMPLATE.format(
            persona=characters.load_persona(character), context=context
        )
        # 참고 문서는 매 턴 새로 검색되므로 시스템 메시지에만 넣는다. history에는 사용자/캐릭터의
        # 발화만 남겨서, 턴이 쌓여도 지난 턴의 문서가 프롬프트를 불리지 않게 한다.
        return [{"role": "system", "content": system}, *(history or []), {"role": "user", "content": question}]

    @obs.llm(model_name="qwen3", model_provider="huggingface", name="generate")
    def _generate(self, messages: list[dict], use_adapter: bool) -> str:
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)

        def run():
            output = self.model.generate(
                **inputs, max_new_tokens=self.cfg["max_new_tokens"], do_sample=False
            )
            return self.tokenizer.decode(
                output[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True
            )

        if self.has_adapter and not use_adapter:
            with self.model.disable_adapter():
                return run()
        return run()

    @obs.workflow(name="character_chat")
    def chat(
        self,
        character: str,
        question: str,
        history: list[dict] | None = None,
        use_adapter: bool = True,
    ) -> str:
        chunks = self._search(character, question)
        messages = self.build_messages(character, question, history, chunks)
        return self._generate(messages, use_adapter).strip()
