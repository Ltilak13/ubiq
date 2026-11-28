"""The `runtime` marker: run a test only where a feature's declared runtime is met.

    @pytest.mark.runtime(python=">=3.11", extra="jsonpath", module="jsonpath_ng")

The keywords are those of `ubiq.support.unmet`; an unmet requirement skips the
test with the same actionable message a user would see.
"""

import pytest

from ubiq.support import skip_reason


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "runtime(python=None, extra=None, module=None, feature=None): skip unless the "
        "declared Python version, pip extra, or module is available")


def pytest_runtest_setup(item):
    for marker in item.iter_markers("runtime"):
        reason = skip_reason(*marker.args, **marker.kwargs)
        if reason:
            pytest.skip(reason)
