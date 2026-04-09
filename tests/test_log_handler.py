"""Unit tests for RingBufferHandler enhancements."""
from __future__ import annotations

import logging

from flexloop.admin.log_handler import RingBufferHandler


def _make_logger(name: str, handler: RingBufferHandler) -> logging.Logger:
    logger = logging.getLogger(f"{name}.{id(handler)}")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger


class TestRecordIds:
    def test_records_have_sequential_ids(self) -> None:
        handler = RingBufferHandler(capacity=100)
        logger = _make_logger("test.ids", handler)

        try:
            logger.info("first")
            logger.info("second")
            logger.info("third")

            records = handler.get_records()
            ids = [record["id"] for record in records]
            assert ids == [0, 1, 2]
        finally:
            logger.removeHandler(handler)


class TestSinceFilter:
    def test_since_filters_old_records(self) -> None:
        handler = RingBufferHandler(capacity=100)
        logger = _make_logger("test.since", handler)

        try:
            logger.info("old")
            first_ts = handler.get_records()[0]["timestamp"]

            logger.info("new")

            records = handler.get_records(since=first_ts)
            assert [record["message"] for record in records] == ["old", "new"]
        finally:
            logger.removeHandler(handler)


class TestGetRecordsAfter:
    def test_returns_records_after_id(self) -> None:
        handler = RingBufferHandler(capacity=100)
        logger = _make_logger("test.after", handler)

        try:
            logger.info("a")
            logger.info("b")
            logger.info("c")

            records = handler.get_records_after(0)

            assert [record["message"] for record in records] == ["b", "c"]
        finally:
            logger.removeHandler(handler)

    def test_returns_empty_when_no_new(self) -> None:
        handler = RingBufferHandler(capacity=100)
        logger = _make_logger("test.after2", handler)

        try:
            logger.info("only")

            records = handler.get_records_after(0)
            assert records == []
        finally:
            logger.removeHandler(handler)

    def test_respects_level_filter(self) -> None:
        handler = RingBufferHandler(capacity=100)
        logger = _make_logger("test.after3", handler)

        try:
            logger.debug("debug msg")
            logger.warning("warn msg")

            records = handler.get_records_after(-1, min_level="WARNING")
            assert [record["message"] for record in records] == ["warn msg"]
        finally:
            logger.removeHandler(handler)


class TestGetLatestId:
    def test_returns_neg1_when_empty(self) -> None:
        handler = RingBufferHandler(capacity=100)
        assert handler.get_latest_id() == -1

    def test_returns_last_id(self) -> None:
        handler = RingBufferHandler(capacity=100)
        logger = _make_logger("test.latest", handler)

        try:
            logger.info("a")
            logger.info("b")

            assert handler.get_latest_id() == 1
        finally:
            logger.removeHandler(handler)
