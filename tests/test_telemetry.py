import logging
from unittest.mock import Mock

import pytest
from fastapi import FastAPI

import app.telemetry as telemetry


_STATE = (
    "_logger_provider",
    "_meter_provider",
    "_tracer_provider",
    "_logging_handler",
)


class FakeLoggingHandler(logging.NullHandler):
    def __init__(self, level, logger_provider):
        super().__init__(level)
        self.logger_provider = logger_provider


@pytest.fixture
def isolated_telemetry_state(monkeypatch):
    root_logger = logging.getLogger()
    existing_handler = telemetry._logging_handler
    if existing_handler is not None:
        root_logger.removeHandler(existing_handler)
    for name in _STATE:
        monkeypatch.setattr(telemetry, name, None)

    yield

    handler = telemetry._logging_handler
    if handler is not None:
        root_logger.removeHandler(handler)
    for name in _STATE:
        setattr(telemetry, name, None)


def test_telemetry_is_disabled_without_an_endpoint(
    monkeypatch, isolated_telemetry_state
):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    telemetry.configure_telemetry(FastAPI())

    assert all(getattr(telemetry, name) is None for name in _STATE)


def test_telemetry_rejects_reconfiguration(
    monkeypatch, isolated_telemetry_state
):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector.example")
    monkeypatch.setattr(telemetry, "_tracer_provider", Mock())

    with pytest.raises(RuntimeError, match="already been configured"):
        telemetry.configure_telemetry(FastAPI())


@pytest.mark.parametrize(
    ("service_name", "expected_name"),
    [
        pytest.param(None, "taskboard", id="default-service-name"),
        pytest.param("taskboard-test", "taskboard-test", id="configured-service-name"),
    ],
)
def test_telemetry_configures_exporters_and_instrumentation(
    monkeypatch, isolated_telemetry_state, service_name, expected_name
):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector.example")
    if service_name is None:
        monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    else:
        monkeypatch.setenv("OTEL_SERVICE_NAME", service_name)

    resource = object()
    tracer_provider = Mock()
    meter_provider = Mock()
    logger_provider = Mock()
    logging_handler = FakeLoggingHandler(
        level=logging.INFO,
        logger_provider=logger_provider,
    )
    span_exporter = object()
    metric_exporter = object()
    log_exporter = object()
    span_processor = object()
    metric_reader = object()
    log_processor = object()
    sqlite_instrumentor = Mock()
    meter_provider_factory = Mock(return_value=meter_provider)

    resource_create = Mock(return_value=resource)
    set_tracer_provider = Mock()
    instrument_app = Mock()
    monkeypatch.setattr(telemetry.Resource, "create", resource_create)
    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", set_tracer_provider)
    monkeypatch.setattr(telemetry, "TracerProvider", Mock(return_value=tracer_provider))
    monkeypatch.setattr(
        telemetry, "OTLPSpanExporter", Mock(return_value=span_exporter)
    )
    monkeypatch.setattr(
        telemetry, "BatchSpanProcessor", Mock(return_value=span_processor)
    )
    monkeypatch.setattr(
        telemetry,
        "OTLPMetricExporter",
        Mock(return_value=metric_exporter),
    )
    monkeypatch.setattr(
        telemetry,
        "PeriodicExportingMetricReader",
        Mock(return_value=metric_reader),
    )
    monkeypatch.setattr(telemetry, "MeterProvider", meter_provider_factory)
    monkeypatch.setattr(telemetry, "LoggerProvider", Mock(return_value=logger_provider))
    monkeypatch.setattr(telemetry, "OTLPLogExporter", Mock(return_value=log_exporter))
    monkeypatch.setattr(
        telemetry, "BatchLogRecordProcessor", Mock(return_value=log_processor)
    )
    monkeypatch.setattr(telemetry, "LoggingHandler", Mock(return_value=logging_handler))
    monkeypatch.setattr(
        telemetry.FastAPIInstrumentor,
        "instrument_app",
        instrument_app,
    )
    monkeypatch.setattr(
        telemetry,
        "SQLite3Instrumentor",
        Mock(return_value=sqlite_instrumentor),
    )

    telemetry.configure_telemetry(FastAPI())

    resource_create.assert_called_once_with(
        {telemetry.SERVICE_NAME: expected_name}
    )
    set_tracer_provider.assert_called_once_with(tracer_provider)
    tracer_provider.add_span_processor.assert_called_once_with(span_processor)
    meter_provider_factory.assert_called_once_with(
        resource=resource,
        metric_readers=[metric_reader],
    )
    logger_provider.add_log_record_processor.assert_called_once_with(log_processor)
    instrument_app.assert_called_once()
    sqlite_instrumentor.instrument.assert_called_once_with(
        tracer_provider=tracer_provider
    )
    assert logging_handler in logging.getLogger().handlers

    telemetry.shutdown_telemetry()

    assert logging_handler not in logging.getLogger().handlers
    logger_provider.shutdown.assert_called_once()
    meter_provider.shutdown.assert_called_once()
    tracer_provider.shutdown.assert_called_once()


def test_telemetry_shutdown_is_safe_when_not_configured(
    isolated_telemetry_state,
):
    telemetry.shutdown_telemetry()

    assert all(getattr(telemetry, name) is None for name in _STATE)
