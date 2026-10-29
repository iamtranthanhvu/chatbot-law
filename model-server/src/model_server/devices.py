def resolve_device(
    setting: str, *, cuda_available: bool | None = None, mps_available: bool | None = None
) -> str:
    """Pick the inference device: an explicit setting wins, "auto" prefers cuda, then mps."""
    if setting != "auto":
        return setting
    if cuda_available is None or mps_available is None:
        import torch

        cuda_available = torch.cuda.is_available() if cuda_available is None else cuda_available
        mps_available = (
            torch.backends.mps.is_available() if mps_available is None else mps_available
        )
    if cuda_available:
        return "cuda"
    if mps_available:
        return "mps"
    return "cpu"
