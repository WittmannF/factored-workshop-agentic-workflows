import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / '.env'
OPIK_PROJECT = 'total-loss-investigator'
OPENROUTER_MODEL = 'qwen/qwen3.5-flash-02-23'

_SETTINGS: 'Settings | None' = None


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str | None
    openrouter_model: str
    env_path: Path


def _load_env(path: Path) -> None:
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=False)
    except ImportError:
        for raw in path.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            name, value = line.split('=', 1)
            os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def get_settings() -> Settings:
    global _SETTINGS
    if _SETTINGS is not None:
        return _SETTINGS
    _load_env(ENV_PATH)
    os.environ.setdefault('OPIK_URL_OVERRIDE', 'http://localhost:5173/api')
    os.environ.setdefault('OPIK_WORKSPACE', 'default')
    os.environ['OPIK_PROJECT_NAME'] = OPIK_PROJECT
    key = os.environ.get('OPENROUTER_API_KEY')
    if key:
        key = key.strip().strip('"').strip("'") or None
    _SETTINGS = Settings(
        openrouter_api_key=key,
        openrouter_model=OPENROUTER_MODEL,
        env_path=ENV_PATH,
    )
    return _SETTINGS


def require_live_settings() -> Settings:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError(
            f'Set OPENROUTER_API_KEY in {settings.env_path} or in the environment.'
        )
    return settings
