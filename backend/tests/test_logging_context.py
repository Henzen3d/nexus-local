"""O formatter exige user_id e conversation_id. Sem default, o log some."""
import io
import logging

import backend.logging_config as lc


def test_log_without_context_still_emits_message():
    buf = io.StringIO()
    root = logging.getLogger("nexuslocal")
    previous_handlers = list(root.handlers)
    previous_configured = lc._CONFIGURED
    lc._CONFIGURED = False
    root.handlers.clear()
    try:
        lc.configure_logging(stream=buf, level=logging.WARNING)
        logger = lc.get_logger("backend.providers.reflection")
        logger.warning(
            "Reflection HTTP 400 model=Beam stream=False request_id=req-1 duration_ms=12 msg=bad"
        )
        text = buf.getvalue()
    finally:
        root.handlers.clear()
        root.handlers.extend(previous_handlers)
        lc._CONFIGURED = previous_configured

    assert "Reflection HTTP 400" in text
    assert "user=-" in text
    assert "conv=-" in text
    assert "Logging error" not in text
