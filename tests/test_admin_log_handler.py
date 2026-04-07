import logging

import pytest

from flexloop.admin.log_handler import RingBufferHandler


def test_handler_captures_records():
    handler = RingBufferHandler(capacity=100)
    logger = logging.getLogger("test.ringbuffer")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    logger.info("hello world")
    logger.warning("danger")

    records = handler.get_records()
    assert len(records) == 2
    assert records[0]["level"] == "INFO"
    assert records[0]["message"] == "hello world"
    assert records[1]["level"] == "WARNING"
    assert records[1]["message"] == "danger"
    assert records[0]["logger"] == "test.ringbuffer"
    assert "timestamp" in records[0]

    logger.removeHandler(handler)


def test_handler_respects_capacity():
    handler = RingBufferHandler(capacity=3)
    logger = logging.getLogger("test.ringbuffer_cap")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    for i in range(5):
        logger.info(f"msg {i}")

    records = handler.get_records()
    assert len(records) == 3
    assert records[0]["message"] == "msg 2"
    assert records[2]["message"] == "msg 4"

    logger.removeHandler(handler)


def test_handler_filters_by_level():
    handler = RingBufferHandler(capacity=100)
    logger = logging.getLogger("test.ringbuffer_filter")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    logger.debug("d")
    logger.info("i")
    logger.warning("w")
    logger.error("e")

    warning_up = handler.get_records(min_level="WARNING")
    assert [r["message"] for r in warning_up] == ["w", "e"]

    logger.removeHandler(handler)


def test_handler_filters_by_search_substring():
    handler = RingBufferHandler(capacity=100)
    logger = logging.getLogger("test.ringbuffer_search")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    logger.info("found needle in haystack")
    logger.info("just haystack")
    logger.info("also a needle")

    hits = handler.get_records(search="needle")
    assert len(hits) == 2

    logger.removeHandler(handler)


def test_handler_captures_exception_info():
    handler = RingBufferHandler(capacity=100)
    logger = logging.getLogger("test.ringbuffer_exc")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failure")

    records = handler.get_records()
    assert len(records) == 1
    assert "ValueError" in records[0]["exception"]
    assert "boom" in records[0]["exception"]

    logger.removeHandler(handler)
