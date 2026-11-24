"""Zero-dependency test runner for environments without pytest.

Emulates the two pytest fixtures the suite uses (tmp_path, capsys).
Canonical runner is still pytest: `python3 -m pytest tests/`.
"""

import contextlib
import importlib
import inspect
import io
import sys
import tempfile
import traceback
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))



class Capsys:
    def __init__(self, buf, err):
        self.buf, self.err = buf, err

    def readouterr(self):
        class R:
            pass
        r = R()
        r.out, r.err = self.buf.getvalue(), self.err.getvalue()
        self.err.seek(0)
        self.err.truncate()
        self.buf.seek(0)
        self.buf.truncate()
        return r


def run():
    modules = [importlib.import_module(path.stem)
               for path in sorted(Path(__file__).parent.glob("test_*.py"))]
    tests = [(f"{module.__name__}.{name}", fn) for module in modules
             for name, fn in vars(module).items()
             if name.startswith("test_") and callable(fn)
             and fn.__module__ == module.__name__]
    failed = 0
    for name, fn in tests:
        params = inspect.signature(fn).parameters
        kwargs, ctx = {}, contextlib.ExitStack()
        with ctx:
            if "tmp_path" in params:
                kwargs["tmp_path"] = Path(ctx.enter_context(tempfile.TemporaryDirectory())).resolve()
            buf, err = io.StringIO(), io.StringIO()
            if "capsys" in params:
                kwargs["capsys"] = Capsys(buf, err)
                ctx.enter_context(contextlib.redirect_stdout(buf))
                ctx.enter_context(contextlib.redirect_stderr(err))
            try:
                fn(**kwargs)
                status = "ok"
            except unittest.SkipTest as exc:
                status = f"skip ({exc})"
            except Exception:  # noqa: BLE001 — a runner reports every failure
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
