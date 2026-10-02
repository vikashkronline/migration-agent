"""Structured diagnostic models and compiler/spec diagnostic parsers."""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DiagnosticCategory(StrEnum):
    """Categorization of validation, compiler, and runtime diagnostics."""

    MISSING_IMPORT = "MISSING_IMPORT"
    SIGNAL_CALL_MISSING = "SIGNAL_CALL_MISSING"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    SPEC_MOCK_MISSING = "SPEC_MOCK_MISSING"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    LINT_FORMAT = "LINT_FORMAT"
    UNKNOWN = "UNKNOWN"


class StructuredDiagnostic(BaseModel):
    """Immutable, typed diagnostic finding extracted from compiler, linter, or test output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file_path: str = Field(default="")
    line: int | None = None
    column: int | None = None
    error_code: str = Field(default="")
    category: DiagnosticCategory = DiagnosticCategory.UNKNOWN
    message: str = Field(min_length=1)
    symbol: str | None = None
    suggested_fix: str = ""


# Regular expressions for compiler and test output diagnostics

# 1. TypeScript compiler: file.ts(line,col): error TS2304: Cannot find name 'Foo'.
# or file.ts:line:col - error TS2304: Cannot find name 'Foo'.
_TSC_PATTERN_PAREN = re.compile(r"^([a-zA-Z0-9_./\\-]+)\((\d+),(\d+)\):\s*error\s*(TS\d+):\s*(.*)$")
_TSC_PATTERN_COLON = re.compile(r"^([a-zA-Z0-9_./\\-]+):(\d+):(\d+)\s*-\s*error\s*(TS\d+):\s*(.*)$")

# 2. Jasmine / Karma / Angular TestBed NullInjectorError
_NULL_INJECTOR_PATTERN = re.compile(
    r"NullInjectorError:\s*(?:R3InjectorError\([^)]*\):\s*)*No provider for\s+([a-zA-Z0-9_]+)!"
)

# 3. ESLint: file.ts:line:col: 'Foo' is not defined. [Error/no-undef]
_ESLINT_PATTERN = re.compile(
    r"^([a-zA-Z0-9_./\\-]+):(\d+):(\d+):\s*(.*?)\s*\[(Error|Warning)/([a-zA-Z0-9_-]+)\]$"
)


def _categorize_typescript_error(
    error_code: str, message: str
) -> tuple[DiagnosticCategory, str | None, str]:
    """Classify TypeScript error code and message into category and target symbol."""
    # TS2304: Cannot find name 'X'.
    name_match = re.search(r"Cannot find name ['\"]([a-zA-Z0-9_]+)['\"]", message)
    if name_match:
        sym = name_match.group(1)
        return (
            DiagnosticCategory.MISSING_IMPORT,
            sym,
            f"Import '{sym}' from appropriate module.",
        )

    # TS2551: Property 'name' does not exist on type 'X'. Did you mean 'name()'?
    did_you_mean = re.search(
        r"Property ['\"]([a-zA-Z0-9_]+)['\"] does not exist on type"
        r".*Did you mean ['\"]([a-zA-Z0-9_()]+)['\"]",
        message,
    )
    if did_you_mean:
        prop = did_you_mean.group(1)
        suggestion = did_you_mean.group(2)
        if "()" in suggestion:
            return (
                DiagnosticCategory.SIGNAL_CALL_MISSING,
                prop,
                f"Invoke signal function: change '{prop}' to '{suggestion}'.",
            )
        return DiagnosticCategory.TYPE_MISMATCH, prop, f"Use property '{suggestion}'."

    # TS2339: Property 'X' does not exist on type 'Y'
    no_prop = re.search(r"Property ['\"]([a-zA-Z0-9_]+)['\"] does not exist on type", message)
    if no_prop:
        prop = no_prop.group(1)
        return (
            DiagnosticCategory.SIGNAL_CALL_MISSING,
            prop,
            f"Check if property '{prop}' is a signal or missing member.",
        )

    # TS2322: Type '...' is not assignable to type '...'
    if error_code == "TS2322":
        if "InputSignal" in message or "Signal" in message or "() =>" in message:
            return (
                DiagnosticCategory.SIGNAL_CALL_MISSING,
                None,
                "Invoke signal with () to access its unwrapped value.",
            )
        return DiagnosticCategory.TYPE_MISMATCH, None, "Fix type mismatch."

    # Syntax errors: TS1005 (';' expected), TS1128, TS1109
    if error_code in ("TS1005", "TS1128", "TS1109", "TS1161"):
        return DiagnosticCategory.SYNTAX_ERROR, None, "Correct TypeScript syntax error."

    return DiagnosticCategory.UNKNOWN, None, ""


def parse_diagnostics(
    output: str,
    diagnostics: tuple[str, ...] | list[str] = (),
) -> list[StructuredDiagnostic]:
    """Parse raw validation output and diagnostic strings into structured diagnostic records."""
    results: list[StructuredDiagnostic] = []
    lines: list[str] = []

    if output:
        lines.extend(output.splitlines())
    for d in diagnostics:
        if d not in lines:
            lines.append(d)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check TypeScript parenthesized format: foo.ts(10,5): error TS2304: ...
        m_tsc_paren = _TSC_PATTERN_PAREN.match(stripped)
        if m_tsc_paren:
            file_path = m_tsc_paren.group(1).replace("\\", "/")
            line_num = int(m_tsc_paren.group(2))
            col_num = int(m_tsc_paren.group(3))
            err_code = m_tsc_paren.group(4)
            msg = m_tsc_paren.group(5)
            cat, sym, fix = _categorize_typescript_error(err_code, msg)
            results.append(
                StructuredDiagnostic(
                    file_path=file_path,
                    line=line_num,
                    column=col_num,
                    error_code=err_code,
                    category=cat,
                    message=msg,
                    symbol=sym,
                    suggested_fix=fix,
                )
            )
            continue

        # Check TypeScript colon format: foo.ts:10:5 - error TS2304: ...
        m_tsc_colon = _TSC_PATTERN_COLON.match(stripped)
        if m_tsc_colon:
            file_path = m_tsc_colon.group(1).replace("\\", "/")
            line_num = int(m_tsc_colon.group(2))
            col_num = int(m_tsc_colon.group(3))
            err_code = m_tsc_colon.group(4)
            msg = m_tsc_colon.group(5)
            cat, sym, fix = _categorize_typescript_error(err_code, msg)
            results.append(
                StructuredDiagnostic(
                    file_path=file_path,
                    line=line_num,
                    column=col_num,
                    error_code=err_code,
                    category=cat,
                    message=msg,
                    symbol=sym,
                    suggested_fix=fix,
                )
            )
            continue

        # Check Jasmine / Angular NullInjectorError
        m_null_inj = _NULL_INJECTOR_PATTERN.search(stripped)
        if m_null_inj:
            sym = m_null_inj.group(1)
            results.append(
                StructuredDiagnostic(
                    file_path="",
                    error_code="NullInjectorError",
                    category=DiagnosticCategory.SPEC_MOCK_MISSING,
                    message=stripped,
                    symbol=sym,
                    suggested_fix=f"Provide '{sym}' or testing provider in TestBed configuration.",
                )
            )
            continue

        # Check ESLint format
        m_eslint = _ESLINT_PATTERN.match(stripped)
        if m_eslint:
            file_path = m_eslint.group(1).replace("\\", "/")
            line_num = int(m_eslint.group(2))
            col_num = int(m_eslint.group(3))
            msg = m_eslint.group(4)
            rule_id = m_eslint.group(6)

            cat = DiagnosticCategory.UNKNOWN
            sym = None
            if rule_id == "no-undef":
                cat = DiagnosticCategory.MISSING_IMPORT
                sym_match = re.search(r"['\"]([a-zA-Z0-9_]+)['\"]", msg)
                if sym_match:
                    sym = sym_match.group(1)
            elif rule_id == "semi":
                cat = DiagnosticCategory.SYNTAX_ERROR
            elif rule_id in ("no-trailing-spaces", "eol-last"):
                cat = DiagnosticCategory.LINT_FORMAT

            results.append(
                StructuredDiagnostic(
                    file_path=file_path,
                    line=line_num,
                    column=col_num,
                    error_code=rule_id,
                    category=cat,
                    message=msg,
                    symbol=sym,
                    suggested_fix=f"Resolve ESLint rule '{rule_id}'.",
                )
            )
            continue

        # Generic / unformatted diagnostic check
        name_search = re.search(r"Cannot find name ['\"]([a-zA-Z0-9_]+)['\"]", stripped)
        if name_search:
            sym = name_search.group(1)
            results.append(
                StructuredDiagnostic(
                    file_path="",
                    error_code="TS2304",
                    category=DiagnosticCategory.MISSING_IMPORT,
                    message=stripped,
                    symbol=sym,
                    suggested_fix=f"Import '{sym}' from appropriate module.",
                )
            )
            continue

        if "missing semicolon" in stripped.lower() or "semi" in stripped.lower():
            results.append(
                StructuredDiagnostic(
                    file_path="",
                    error_code="semi",
                    category=DiagnosticCategory.SYNTAX_ERROR,
                    message=stripped,
                    suggested_fix="Ensure statement concludes with a semicolon.",
                )
            )

    return results
