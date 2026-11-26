import logging
import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


_logger_provider: LoggerProvider | None = None
_meter_provider: MeterProvider | None = None
_tracer_provider: TracerProvider | None = None
_logging_handler: LoggingHandler | None = None


def configure_telemetry(app: FastAPI) -> None:
    global _logger_provider, _meter_provider, _tracer_provider, _logging_handler

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return
    if _tracer_provider is not None:
        raise RuntimeError("OpenTelemetry has already been configured.")

    resource = Resource.create(
        {SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "taskboard")}
    )

    _tracer_provider = TracerProvider(resource=resource)
    _tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(_tracer_provider)

    metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    _meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
    )

    _logger_provider = LoggerProvider(resource=resource)
    _logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter())
    )
    _logging_handler = LoggingHandler(
        level=logging.INFO,
        logger_provider=_logger_provider,
    )
    logging.getLogger().addHandler(_logging_handler)

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=_tracer_provider,
        meter_provider=_meter_provider,
    )
    SQLite3Instrumentor().instrument(tracer_provider=_tracer_provider)


def shutdown_telemetry() -> None:
    root_logger = logging.getLogger()
    if _logging_handler is not None:
        root_logger.removeHandler(_logging_handler)

    if _logger_provider is not None:
        _logger_provider.shutdown()
    if _meter_provider is not None:
        _meter_provider.shutdown()
    if _tracer_provider is not None:
        _tracer_provider.shutdown()
