"""Zero-dependency test runner for environments without pytest.

Emulates the two pytest fixtures the suite uses (tmp_path, capsys).
Canonical runner is still pytest: `python3 -m pytest tests/`.
"""

import contextlib
import inspect
import io
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_ubiq  # noqa: E402


class Capsys:
    def __init__(self, buf):
        self.buf = buf

    def readouterr(self):
        class R:
            pass
        r = R()
        r.out, r.err = self.buf.getvalue(), ""
        self.buf.seek(0)
        self.buf.truncate()
        return r


def run():
    tests = [(n, f) for n, f in vars(test_ubiq).items()
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        params = inspect.signature(fn).parameters
        kwargs, ctx = {}, contextlib.ExitStack()
        with ctx:
            if "tmp_path" in params:
                kwargs["tmp_path"] = Path(ctx.enter_context(tempfile.TemporaryDirectory()))
            buf = io.StringIO()
            if "capsys" in params:
                kwargs["capsys"] = Capsys(buf)
                ctx.enter_context(contextlib.redirect_stdout(buf))
            try:
                fn(**kwargs)
                status = "ok"
            except Exception:
                status = "FAIL"
                failed += 1
                tb = traceback.format_exc()
        print(f"{status}  {name}")
        if status == "FAIL":
            print(tb)
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
