"""캐릭터 '하나'가 아니라, 여러 캐릭터의 (persona, instruction, response) 예시를 섞어서
"주어진 페르소나를 잘 따라가는 능력" 자체를 학습시킨다.

캐릭터 한 명만 학습시키면 그 캐릭터 전용 어댑터가 되어 새 캐릭터엔 쓸모가 없다. 이쪽은 persona.md를 프롬프트에 직접 포함시켜서 "어떤 페르소나가 주어지든
따라가는 법"을 배우게 하는 것 -> 결과물은 특정 캐릭터 소유가 아니라 범용 어댑터라
adapters/persona_skill/ 에 저장한다. 학습에 없던 새 캐릭터에도 이 능력이 적용되는지가
이 접근의 핵심 가설이다 (0.6B로는 이 일반화가 잘 보이지 않을 수 있음 -> 배관 검증용).

실행: python finetune/train_persona_skill.py [--characters odysseus,nostradamus,sejong,yi_bangwon]
(옵션 생략 시 characters/ 밑에 persona.md + train.jsonl이 둘 다 있는 캐릭터를 전부 사용)
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

from core import characters
from core.config import load_config

OUTPUT_DIR = REPO_ROOT / "adapters" / "persona_skill"


def load_model_and_tokenizer(cfg: dict):
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"])

    if cfg["load_in_4bit"]:
        from peft import prepare_model_for_kbit_training
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
        model = prepare_model_for_kbit_training(model)
    else:
        if torch.cuda.is_available():
            model = AutoModelForCausalLM.from_pretrained(
                cfg["base_model"], dtype=torch.bfloat16, device_map="auto"
            )
        else:
            model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], dtype=torch.float32)

    return model, tokenizer


def build_pooled_dataset(character_names: list[str]) -> Dataset:
    """여러 캐릭터의 train.jsonl을 (persona, instruction, response) 형태로 하나로 합친다."""
    rows = []
    for name in character_names:
        persona = characters.load_persona(name)
        with open(characters.train_data_path(name), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                example = json.loads(line)
                rows.append(
                    {
                        "persona": persona,
                        "instruction": example["instruction"],
                        "response": example["response"],
                    }
                )
    return Dataset.from_list(rows)


def main(character_names: list[str]):
    cfg = load_config()
    if len(character_names) < 2:
        raise SystemExit(
            "캐릭터가 1개뿐이면 '페르소나를 따라가는 능력'을 일반화해서 배울 수 없습니다. "
            "최소 2개 이상(서로 톤이 다른 캐릭터일수록 좋음)이 필요합니다."
        )

    print(f"학습에 쓰는 캐릭터: {character_names}")
    dataset = build_pooled_dataset(character_names).shuffle(seed=42)
    print(f"총 예시 수: {len(dataset)}")

    model, tokenizer = load_model_and_tokenizer(cfg)

    def formatting_func(example):
        messages = [
            {"role": "system", "content": example["persona"]},
            {"role": "user", "content": example["instruction"]},
            {"role": "assistant", "content": example["response"]},
        ]
        return tokenizer.apply_chat_template(messages, tokenize=False)

    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )

    sft_config = SFTConfig(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=3,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        logging_steps=1,
        save_strategy="no",
        report_to=[],
        bf16=torch.cuda.is_available(),
        fp16=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=dataset,
        peft_config=lora_config,
        formatting_func=formatting_func,
    )
    trainer.train()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))
    print(f"범용 페르소나 어댑터 저장 완료: {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--characters", default=None, help="쉼표로 구분한 캐릭터 이름들 (기본: 전부)")
    args = parser.parse_args()
    names = args.characters.split(",") if args.characters else characters.list_characters()
    main(names)
