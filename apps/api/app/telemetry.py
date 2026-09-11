"""Optional OpenTelemetry wiring for the isolated Developer Lab profile."""
from __future__ import annotations
import os


def configure_fastapi(app, engine) -> None:
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint: return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    provider=TracerProvider(resource=Resource.create({"service.name":os.getenv("OTEL_SERVICE_NAME","genuinegigs-api")}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/")+"/v1/traces")))
    trace.set_tracer_provider(provider); FastAPIInstrumentor.instrument_app(app,excluded_urls="/health/live,/metrics")
    SQLAlchemyInstrumentor().instrument(engine=engine)


def configure_celery() -> None:
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"): return
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    CeleryInstrumentor().instrument()
