"""configs/model.yaml의 base_model을, 지정한 캐릭터의 characters/<name>/train.jsonl로 QLoRA(4bit) 파인튜닝한다.

- load_in_4bit: true  -> GPU 필요 (g4dn.xlarge / g5.xlarge), bitsandbytes로 4bit 양자화 학습
- load_in_4bit: false -> CPU에서도 동작 (소형 모델로 파이프라인 검증용, 매우 느림)

실행: python finetune/train_qlora.py [--character odysseus]
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

import characters
from config import load_config


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
        # device_map="auto"는 GPU가 없으면 accelerate가 불필요하게 디스크 오프로드를 시도해서
        # 느려지고 오작동할 수 있음 -> CUDA 없을 땐 device_map 없이 그냥 CPU에 로드.
        if torch.cuda.is_available():
            model = AutoModelForCausalLM.from_pretrained(
                cfg["base_model"], dtype=torch.bfloat16, device_map="auto"
            )
        else:
            model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], dtype=torch.float32)

    return model, tokenizer


def main(character: str):
    cfg = load_config()
    dataset_path = characters.train_data_path(character)
    if not dataset_path.exists():
        raise SystemExit(f"{dataset_path} 가 없습니다. characters/{character}/train.jsonl 을 먼저 작성하세요.")

    output_dir = characters.adapter_dir(character)

    model, tokenizer = load_model_and_tokenizer(cfg)
    dataset = load_dataset("json", data_files=str(dataset_path))["train"]

    def formatting_func(example):
        messages = [
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
        output_dir=str(output_dir),
        num_train_epochs=3,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        logging_steps=1,
        save_strategy="no",
        report_to=[],
        bf16=torch.cuda.is_available(),  # CPU 드라이런에선 bf16/fp16 다 꺼야 함
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

    output_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    print(f"[{character}] 어댑터 저장 완료: {output_dir}")
    print(f"agent/app.py --character {character} 실행하면 자동으로 이 어댑터를 씁니다.")


if __name__ == "__main__":
    cfg = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--character", default=cfg["active_character"])
    args = parser.parse_args()
    main(args.character)
