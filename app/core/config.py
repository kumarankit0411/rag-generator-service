from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "rag-generator"
    app_env: str = "dev"
    app_port: int = 8000

    # RAG / vector store placeholders (no logic wired yet)
    chroma_persist_dir: str = "./data/chroma"
    embedding_model: str = "all-MiniLM-L6-v2"
    chunk_max_tokens: int = 500
    chunk_overlap_tokens: int = 50

    # ask / generation
    ask_top_k: int = 5
    ask_max_distance: float = 0.75
    llm_model: str = ""  # e.g. "gpt-4o-mini"; empty = extractive fallback (no LLM call)
    llm_temperature: float = 0.0

    # calibration
    eval_dir: str = "./evals"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
