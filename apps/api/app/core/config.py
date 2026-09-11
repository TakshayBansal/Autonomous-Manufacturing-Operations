from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    scm_enabled: bool = True
    demo_bootstrap_enabled: bool = True
    app_env: str = "development"
    database_url: str = "sqlite:///./genuinegigs_dev.db"
    redis_url: str = "redis://localhost:6379/0"
    object_storage_endpoint: str = "http://localhost:9000"
    object_storage_bucket: str = "genuinegigs-documents"
    object_storage_quarantine_bucket: str = "genuinegigs-quarantine"
    object_storage_evidence_bucket: str = "genuinegigs-evidence"
    object_storage_region: str = "us-east-1"
    object_storage_secure: bool = False
    object_storage_access_key: str | None = None
    object_storage_secret_key: str | None = None
    session_secret: str = "dev-session-secret"
    session_ttl_seconds: int = 36000
    cookie_samesite: str = "lax"
    web_base_url: str = 'http://localhost:3000'
    ai_provider: str = "disabled"
    agent_enabled: bool = False
    agent_primary_model: str = "openai/gpt-oss-120b"
    agent_fast_model: str = "llama-3.1-8b-instant"
    agent_extraction_model: str = "openai/gpt-oss-120b"
    agent_extraction_max_completion_tokens: int = 8192
    agent_extraction_retry_max_completion_tokens: int = 16384
    agent_extraction_reasoning_effort: str = "low"
    quotation_extraction_provider: str = "groq"
    groq_quotation_extraction_model: str = "openai/gpt-oss-20b"
    groq_quotation_extraction_max_completion_tokens: int = 3072
    groq_quotation_extraction_retry_max_completion_tokens: int = 4096
    groq_quotation_extraction_reasoning_effort: str = "low"
    gemini_api_key: str | None = None
    gemini_extraction_model: str = "gemini-3.6-flash"
    gemini_extraction_max_output_tokens: int = 4096
    agent_default_token_budget: int = 8000
    agent_planning_max_output_tokens: int = 1200
    agent_response_max_output_tokens: int = 350
    agent_provider_request_target_tokens: int = 6800
    agent_recent_raw_turns: int = 4
    agent_default_monthly_token_budget: int = 1_000_000
    agent_max_run_seconds: int = 45
    agent_max_handoffs: int = 8
    agent_max_delegation_depth: int = 3
    agent_conversation_retention_days: int = 365
    agent_max_graph_steps: int = 6
    agent_max_tool_calls: int = 5
    agent_max_business_mutations: int = 1
    agent_max_controlled_proposals: int = 1
    agent_max_candidates: int = 3
    agent_max_task_rows: int = 5
    agent_max_synchronous_document_seconds: int = 12
    agent_max_context_bytes: int = 250000
    agent_checkpoint_retention_days: int = 30
    retention_enforcement_enabled: bool = False
    agent_requests_per_minute: int = 20
    agent_external_email_enabled: bool = False
    agent_erp_posting_enabled: bool = False
    agent_trace_content_policy: str = 'metadata_only'
    agent_deterministic_test_provider: bool = False
    groq_api_key: str | None = None
    llama_cloud_api_key: str | None = None
    llamaparse_base_url: str = "https://api.cloud.llamaindex.ai"
    llamaparse_poll_interval_seconds: float = 1.0
    llamaparse_timeout_seconds: int = 120
    embedding_service_url: str | None = None
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    agent_trace_export_enabled: bool = False
    agent_allow_deterministic_fallback: bool = True
    smtp_host: str | None = None
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "procurement@genuinegigs.local"
    oracle_base_url: str | None = None
    oracle_client_id: str | None = None
    oracle_client_secret: str | None = None
    oracle_token_url: str | None = None
    oracle_scope: str | None = None
    oracle_procurement_bu: str | None = None
    oracle_requisitioning_bu: str | None = None
    oracle_receipt_resource: str = "/fscmRestApi/resources/11.13.18.05/receivingReceiptRequests"
    integration_timeout_seconds: int = 30
    sap_base_url: str | None = None
    sap_client_id: str | None = None
    sap_client_secret: str | None = None
    erp_provider: str = "local"
    erp_write_mode: str = "simulation"
    erp_live_enabled: bool = False
    smtp_mode: str = "simulation"
    secure_cookies: bool = False
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    max_upload_bytes: int = 10 * 1024 * 1024
    parser_timeout_seconds: int = 60
    ocr_timeout_seconds: int = 180
    download_url_ttl_seconds: int = 300
    celery_task_always_eager: bool = False
    log_level: str = "INFO"
    upload_dir: Path = Path("uploads")
    opa_url: str = "http://opa:8181"
    opa_decision_path: str = "/v1/data/genuinegigs/decision"
    opa_mode: str = "shadow"
    opa_timeout_seconds: float = 2.0
    opa_policy_version: str = "agentic-procurement-v1"
    sandbox_provider: str = "local"
    sandbox_service_url: str = "http://sandbox-runner:8090"
    sandbox_root: Path = Path("/tmp/genuinegigs-sandboxes")
    sandbox_default_ttl_seconds: int = 900
    sandbox_max_output_bytes: int = 5 * 1024 * 1024
    temporal_enabled: bool = False
    temporal_address: str = "temporal:7233"
    temporal_task_queue: str = "procurement-cycles"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    def validate_runtime_safety(self) -> None:
        if self.agent_planning_max_output_tokens >= self.agent_provider_request_target_tokens:
            raise RuntimeError("Planning output tokens must be below the total provider request target")
        if self.agent_recent_raw_turns < 1:
            raise RuntimeError("At least one recent agent turn must be retained")
        if self.cookie_samesite not in {"lax", "strict", "none"}:
            raise RuntimeError("COOKIE_SAMESITE must be lax, strict, or none")
        if self.cookie_samesite == "none" and not self.secure_cookies:
            raise RuntimeError("SameSite=None cookies must be secure")
        if self.app_env.lower() == "production":
            if not self.secure_cookies:
                raise RuntimeError("SECURE_COOKIES must be enabled in production")
            if self.session_secret in {"dev-session-secret", "replace-with-local-secret"} or len(self.session_secret) < 32:
                raise RuntimeError("SESSION_SECRET must be a strong production secret")
            if self.erp_write_mode == "live" and not self.erp_live_enabled:
                raise RuntimeError("ERP live mode requires ERP_LIVE_ENABLED=true")
            if "*" in self.cors_origins:
                raise RuntimeError("Wildcard CORS origins are not allowed in production")
            if self.ai_provider == "groq" and not self.groq_api_key and not self.agent_allow_deterministic_fallback:
                raise RuntimeError("GROQ_API_KEY is required when Groq is enabled without degraded fallback")
        if self.opa_mode not in {"disabled", "shadow", "enforce"}:
            raise RuntimeError("OPA_MODE must be disabled, shadow, or enforce")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
