"""Load and validate config.toml. Secrets come from the environment, never from here."""


def load_config(path: str = "config.toml") -> dict:
    """Read and validate the TOML config into a typed structure."""
    raise NotImplementedError
