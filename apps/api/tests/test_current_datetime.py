from datetime import UTC, datetime, timedelta

import pytest
from pydantic_ai import ModelRetry

from hello_my_assistant_api.current_datetime import get_current_datetime


def test_get_current_datetime_returns_localized_current_datetime_when_timezone_is_valid():
    before = datetime.now(UTC)

    result = get_current_datetime("Asia/Seoul")

    after = datetime.now(UTC)
    result_in_utc = result.local_datetime.astimezone(UTC)

    assert result.timezone == "Asia/Seoul"
    assert result.local_datetime.utcoffset() == timedelta(hours=9)
    assert before <= result_in_utc <= after


def test_get_current_datetime_requests_retry_when_timezone_is_invalid():
    with pytest.raises(ModelRetry, match="Unknown IANA time zone: Asia/Seoull"):
        get_current_datetime("Asia/Seoull")
