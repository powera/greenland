#!/usr/bin/python3

"""Runners for Python coding benchmarks (0301-0305)."""

import ast
import contextlib
import io
import logging
import signal
from typing import Any, Callable, Dict, Optional, Tuple

from benchmarks.lib.runners.partial_credit_runner import PartialCreditRunner
from benchmarks.lib.utils.factory import runner

logger = logging.getLogger(__name__)

_SAFE_BUILTINS: Dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "Exception": Exception,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "set": set,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "TypeError": TypeError,
    "ValueError": ValueError,
}

_BANNED_CALL_NAMES = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "globals",
    "input",
    "locals",
    "open",
    "vars",
}

_BANNED_TOPLEVEL_NAMES = {
    "ctypes",
    "os",
    "pathlib",
    "requests",
    "shutil",
    "socket",
    "subprocess",
    "sys",
    "urllib",
}


class _TimeoutError(Exception):
    pass


class PythonCodingRunnerBase(PartialCreditRunner):
    """Shared runner logic for Python coding tasks."""

    CORRECTNESS_THRESHOLD = 100

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        return question_data["question_text"], None, None

    def _extract_code(self, response: Any) -> str:
        text = response if isinstance(response, str) else str(response)
        stripped = text.strip()
        if stripped.startswith("```"):
            segments = stripped.split("```")
            for segment in segments:
                normalized = segment.strip()
                if normalized.startswith("python"):
                    return normalized[len("python") :].strip()
                if normalized and "\n" in normalized:
                    return normalized
        return stripped

    def _validate_ast_safety(self, code: str) -> Optional[str]:
        try:
            syntax_tree = ast.parse(code)
        except SyntaxError as error:
            return f"SyntaxError: {error.msg}"

        for node in ast.walk(syntax_tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                return "Imports are not allowed"
            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                return "Dunder attribute access is not allowed"
            if isinstance(node, ast.Name) and node.id in _BANNED_TOPLEVEL_NAMES:
                return f"Use of '{node.id}' is not allowed"
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in _BANNED_CALL_NAMES:
                    return f"Call to '{node.func.id}' is not allowed"
                if isinstance(node.func, ast.Attribute) and node.func.attr in {
                    "remove",
                    "rmdir",
                    "rename",
                    "replace",
                    "unlink",
                    "write_bytes",
                    "write_text",
                    "system",
                    "popen",
                    "run",
                    "request",
                    "urlopen",
                    "post",
                    "get",
                }:
                    return f"Potentially dangerous call '{node.func.attr}' is not allowed"
        return None

    def _run_with_timeout(self, func: Callable[..., Any], args: tuple[Any, ...]) -> Any:
        def _handle_timeout(signum: int, frame: Any) -> None:
            raise _TimeoutError("Execution timed out")

        previous_handler = signal.signal(signal.SIGALRM, _handle_timeout)
        signal.setitimer(signal.ITIMER_REAL, 1.0)
        try:
            return func(*args)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            signal.signal(signal.SIGALRM, previous_handler)

    def score_response(self, question_data: Dict[str, Any], response: Any) -> int:
        code = self._extract_code(response)
        safety_error = self._validate_ast_safety(code)
        if safety_error is not None:
            return 0

        function_name = question_data.get("correct_answer", {}).get("function_name")
        if not isinstance(function_name, str) or not function_name:
            return 0

        execution_globals: Dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
        try:
            exec(code, execution_globals)
        except Exception:
            return 0

        target_function = execution_globals.get(function_name)
        if not callable(target_function):
            return 0

        test_cases = question_data.get("correct_answer", {}).get("test_cases", [])
        if not isinstance(test_cases, list) or not test_cases:
            return 0

        passed_count = 0

        for test_case in test_cases:
            if not isinstance(test_case, dict):
                continue
            args = test_case.get("args", [])
            expected = test_case.get("expected")
            expected_exception = test_case.get("expected_exception")

            if not isinstance(args, list):
                continue

            capture_stdout = bool(test_case.get("capture_stdout", False))
            stdout_buffer = io.StringIO()

            try:
                with contextlib.redirect_stdout(stdout_buffer):
                    result = self._run_with_timeout(target_function, tuple(args))
            except _TimeoutError:
                continue
            except Exception as error:
                if (
                    isinstance(expected_exception, str)
                    and error.__class__.__name__ == expected_exception
                ):
                    passed_count += 1
                continue

            if isinstance(expected_exception, str):
                continue

            if capture_stdout:
                if stdout_buffer.getvalue().strip() == str(expected).strip():
                    passed_count += 1
                continue

            if result == expected:
                passed_count += 1

        return int(round((passed_count / len(test_cases)) * 100))

    def build_debug_info(
        self, question_data: Dict, response: Any, is_correct: bool
    ) -> Dict[str, Any]:
        model_answer = getattr(response, "response_text", response)
        score = self.score_response(question_data, model_answer)
        return {
            "response": model_answer,
            "score": score,
            "correctness_threshold": self.CORRECTNESS_THRESHOLD,
            "is_correct": is_correct,
            "function_name": question_data.get("correct_answer", {}).get("function_name"),
        }


@runner("0301_python_hello_world")
class PythonHelloWorldRunner(PythonCodingRunnerBase):
    """Runner for benchmark 0301."""


@runner("0302_python_gcd")
class PythonGCDRunner(PythonCodingRunnerBase):
    """Runner for benchmark 0302."""


@runner("0303_python_letter_count")
class PythonLetterFrequencyRunner(PythonCodingRunnerBase):
    """Runner for benchmark 0303."""


@runner("0304_python_coin_change")
class PythonCoinChangeRunner(PythonCodingRunnerBase):
    """Runner for benchmark 0304."""


@runner("0305_python_prime_factorization")
class PythonPrimeFactorizationRunner(PythonCodingRunnerBase):
    """Runner for benchmark 0305."""
