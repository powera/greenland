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
    "chr": chr,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "Exception": Exception,
    "filter": filter,
    "float": float,
    "isinstance": isinstance,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "ord": ord,
    "pow": pow,
    "print": print,
    "range": range,
    "reversed": reversed,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "TypeError": TypeError,
    "type": type,
    "ValueError": ValueError,
    "zip": zip,
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

    def _evaluate_response(
        self, question_data: Dict[str, Any], response: Any
    ) -> tuple[int, list[dict[str, Any]]]:
        code = self._extract_code(response)
        safety_error = self._validate_ast_safety(code)
        if safety_error is not None:
            return 0, [{"error": safety_error}]

        function_name = question_data.get("correct_answer", {}).get("function_name")
        if not isinstance(function_name, str) or not function_name:
            return 0, [{"error": "Missing function_name in correct_answer"}]

        execution_globals: Dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
        try:
            exec(code, execution_globals)
        except Exception as error:
            return 0, [{"error": f"Execution failed: {error.__class__.__name__}"}]

        target_function = execution_globals.get(function_name)
        if not callable(target_function):
            return 0, [{"error": f"Function '{function_name}' is not callable"}]

        test_cases = question_data.get("correct_answer", {}).get("test_cases", [])
        if not isinstance(test_cases, list) or not test_cases:
            return 0, [{"error": "No valid test_cases were provided"}]

        passed_count = 0
        case_results: list[dict[str, Any]] = []

        for test_case_index, test_case in enumerate(test_cases):
            if not isinstance(test_case, dict):
                case_results.append(
                    {
                        "index": test_case_index,
                        "passed": False,
                        "error": "Invalid test case format",
                    }
                )
                continue
            args = test_case.get("args", [])
            expected_value = test_case.get("expected")
            expected_exception = test_case.get("expected_exception")
            allowed_exceptions: tuple[str, ...] = ()
            if isinstance(expected_exception, str):
                allowed_exceptions = (expected_exception,)
            elif isinstance(expected_exception, list) and all(
                isinstance(exception_name, str) for exception_name in expected_exception
            ):
                allowed_exceptions = tuple(expected_exception)

            if not isinstance(args, list):
                case_results.append(
                    {
                        "index": test_case_index,
                        "args": args,
                        "passed": False,
                        "error": "args must be a list",
                    }
                )
                continue

            capture_stdout = bool(test_case.get("capture_stdout", False))
            stdout_buffer = io.StringIO()
            case_result: dict[str, Any] = {
                "index": test_case_index,
                "args": args,
                "expected": expected_value,
                "expected_exception": expected_exception,
                "capture_stdout": capture_stdout,
                "passed": False,
            }

            try:
                with contextlib.redirect_stdout(stdout_buffer):
                    result = self._run_with_timeout(target_function, tuple(args))
            except _TimeoutError:
                case_result["error"] = "Execution timed out"
                case_results.append(case_result)
                continue
            except Exception as error:
                if error.__class__.__name__ in allowed_exceptions:
                    passed_count += 1
                    case_result["passed"] = True
                    case_result["actual_exception"] = error.__class__.__name__
                else:
                    case_result["actual_exception"] = error.__class__.__name__
                    case_result["error"] = str(error)
                case_results.append(case_result)
                continue

            if allowed_exceptions:
                case_result["result"] = result
                if len(allowed_exceptions) == 1:
                    case_result["error"] = (
                        f"Expected exception '{allowed_exceptions[0]}' but function returned normally"
                    )
                else:
                    expected_names = ", ".join(allowed_exceptions)
                    case_result["error"] = (
                        f"Expected one of [{expected_names}] but function returned normally"
                    )
                case_results.append(case_result)
                continue

            if capture_stdout:
                stdout_text = stdout_buffer.getvalue().strip()
                case_result["stdout"] = stdout_text
                if stdout_text == str(expected_value).strip():
                    passed_count += 1
                    case_result["passed"] = True
                case_results.append(case_result)
                continue

            case_result["result"] = result
            if result == expected_value:
                passed_count += 1
                case_result["passed"] = True
            case_results.append(case_result)

        score = int(round((passed_count / len(test_cases)) * 100))
        return score, case_results

    def score_response(self, question_data: Dict[str, Any], response: Any) -> int:
        score, _ = self._evaluate_response(question_data, response)
        return score

    def build_debug_info(
        self, question_data: Dict, response: Any, is_correct: bool
    ) -> Dict[str, Any]:
        model_answer = getattr(response, "response_text", response)
        score, test_case_results = self._evaluate_response(question_data, model_answer)
        return {
            "response": model_answer,
            "score": score,
            "correctness_threshold": self.CORRECTNESS_THRESHOLD,
            "is_correct": is_correct,
            "function_name": question_data.get("correct_answer", {}).get("function_name"),
            "test_case_results": test_case_results,
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
