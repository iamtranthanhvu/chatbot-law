from huggingface_hub import snapshot_download

from model_server.config import Settings

# bge-m3 ships pytorch_model.bin plus colbert/sparse heads (*.pt); the reranker ships safetensors.
_WEIGHTS_AND_TOKENIZER = ["*.json", "*.safetensors", "pytorch_model.bin", "*.pt", "*.model"]


def main() -> None:
    settings = Settings()
    for name in (settings.embed_model, settings.rerank_model):
        path = snapshot_download(
            name,
            allow_patterns=_WEIGHTS_AND_TOKENIZER,
            ignore_patterns=["onnx/*", "imgs/*", "assets/*"],
        )
        print(f"{name} -> {path}")


if __name__ == "__main__":
    main()
