"""Local-only Qwen3 inference helpers. No network calls or API keys are used."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

DEFAULT_MODEL_PATH = Path(r"D:\qwen-spec\models\Qwen3-4B")


class LocalQwen:
    def __init__(self, model_path: str | Path = DEFAULT_MODEL_PATH):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.path = Path(model_path).expanduser().resolve()
        if not self.path.is_dir() or not (self.path / "config.json").exists():
            raise FileNotFoundError(f"Локальная модель не найдена: {self.path}")
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.path), local_files_only=True, trust_remote_code=False)
        offload_dir = Path(tempfile.gettempdir()) / "qwen3_hw2_offload"
        offload_dir.mkdir(parents=True, exist_ok=True)
        if torch.cuda.is_available():
            # 4 GiB for weights leaves roughly 2 GiB free on the detected 6 GiB GPU
            # for activations and the KV cache; the remaining weights stay on CPU.
            gpu_budget = os.getenv("QWEN3_GPU_MEMORY", "4GiB")
            cpu_budget = os.getenv("QWEN3_CPU_MEMORY", "24GiB")
            try:
                self.model = AutoModelForCausalLM.from_pretrained(
                    str(self.path),
                    local_files_only=True,
                    trust_remote_code=False,
                    torch_dtype=torch.float16,
                    low_cpu_mem_usage=True,
                    device_map="auto",
                    max_memory={0: gpu_budget, "cpu": cpu_budget},
                    offload_folder=str(offload_dir),
                    offload_state_dict=True,
                )
            except OSError as exc:
                if getattr(exc, "winerror", None) == 1455 or "paging file is too small" in str(exc).lower():
                    raise RuntimeError(
                        "Windows не хватило виртуальной памяти для загрузки Qwen3-4B (ошибка 1455). "
                        "Включите системное управление файлом подкачки или увеличьте его размер, "
                        "перезагрузите Windows и повторите запуск. Освободите место на системном диске."
                    ) from exc
                raise
        else:
            self.model = AutoModelForCausalLM.from_pretrained(
                str(self.path), local_files_only=True, trust_remote_code=False,
                torch_dtype=torch.float32, low_cpu_mem_usage=True,
            )
            self.model.to("cpu")
        self.model.eval()
        self.input_device = self.model.get_input_embeddings().weight.device

    def generate(self, messages: list[dict[str, str]], *, max_new_tokens: int, seed: int) -> dict:
        torch = self.torch
        try:
            rendered = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
        except TypeError:
            rendered = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        encoded = self.tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
        input_ids = encoded["input_ids"].to(self.input_device)
        attention_mask = encoded["attention_mask"].to(self.input_device)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        with torch.inference_mode():
            output = self.model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.25,
                top_p=0.85,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                use_cache=True,
            )
        new_ids = output[0, input_ids.shape[-1]:]
        return {
            "text": self.tokenizer.decode(new_ids, skip_special_tokens=True).strip(),
            "input_tokens": int(input_ids.shape[-1]),
            "output_tokens": int(new_ids.shape[-1]),
        }

