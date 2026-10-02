"""Deterministic surgical repair strategies for compiler, spec, and linter diagnostics."""

import os
import posixpath
import re
import uuid
from pathlib import Path
from typing import Protocol

from migration_agent.application.diagnostics import DiagnosticCategory, StructuredDiagnostic
from migration_agent.domain import ChangeSet, compute_file_sha256

# Well-known Angular and standard library exports mapped to package specifiers
_KNOWN_LIBRARY_EXPORTS: dict[str, str] = {
    # @angular/core
    "Component": "@angular/core",
    "Injectable": "@angular/core",
    "inject": "@angular/core",
    "signal": "@angular/core",
    "computed": "@angular/core",
    "input": "@angular/core",
    "output": "@angular/core",
    "model": "@angular/core",
    "viewChild": "@angular/core",
    "ChangeDetectionStrategy": "@angular/core",
    "OnInit": "@angular/core",
    "OnDestroy": "@angular/core",
    # @angular/common
    "CommonModule": "@angular/common",
    "DatePipe": "@angular/common",
    "DecimalPipe": "@angular/common",
    "CurrencyPipe": "@angular/common",
    # @angular/common/http
    "HttpClient": "@angular/common/http",
    "HttpParams": "@angular/common/http",
    "HttpHeaders": "@angular/common/http",
    "provideHttpClient": "@angular/common/http",
    # @angular/common/http/testing
    "HttpTestingController": "@angular/common/http/testing",
    "provideHttpClientTesting": "@angular/common/http/testing",
    # @angular/core/testing
    "TestBed": "@angular/core/testing",
    "ComponentFixture": "@angular/core/testing",
    # @angular/forms
    "FormsModule": "@angular/forms",
    "ReactiveFormsModule": "@angular/forms",
    "FormGroup": "@angular/forms",
    "FormControl": "@angular/forms",
    # @angular/router
    "Router": "@angular/router",
    "ActivatedRoute": "@angular/router",
    "provideRouter": "@angular/router",
    "RouterModule": "@angular/router",
    # rxjs
    "Observable": "rxjs",
    "of": "rxjs",
    "firstValueFrom": "rxjs",
    "Subject": "rxjs",
    "BehaviorSubject": "rxjs",
    "map": "rxjs",
    "switchMap": "rxjs",
    "catchError": "rxjs",
}


def _compute_relative_import_path(from_file: str, to_file: str) -> str:
    """Compute relative POSIX module import path from source file to target module."""
    from_dir = posixpath.dirname(from_file)
    rel = posixpath.relpath(to_file, from_dir)
    # Strip extension (.ts, .js)
    if rel.endswith(".ts") or rel.endswith(".js"):
        rel = rel[:-3]

    if not rel.startswith("."):
        rel = f"./{rel}"
    return rel


class RepairStrategy(Protocol):
    """Protocol for a deterministic surgical repair strategy."""

    def can_repair(
        self,
        diagnostic: StructuredDiagnostic,
        changeset: ChangeSet,
        allowed_scope: tuple[str, ...],
    ) -> bool:
        """Return True if strategy can address this diagnostic."""

    def repair(
        self,
        diagnostic: StructuredDiagnostic,
        changeset: ChangeSet,
        allowed_scope: tuple[str, ...],
        staging_dir: Path | None = None,
    ) -> ChangeSet | None:
        """Apply deterministic surgical patch and return updated ChangeSet."""


class AutoImportRepairStrategy:
    """Detects missing symbol diagnostics and adds missing import statements."""

    def can_repair(
        self,
        diagnostic: StructuredDiagnostic,
        changeset: ChangeSet,
        allowed_scope: tuple[str, ...],
    ) -> bool:
        if diagnostic.category != DiagnosticCategory.MISSING_IMPORT:
            return False
        return bool(diagnostic.symbol)

    def repair(
        self,
        diagnostic: StructuredDiagnostic,
        changeset: ChangeSet,
        allowed_scope: tuple[str, ...],
        staging_dir: Path | None = None,
    ) -> ChangeSet | None:
        symbol = diagnostic.symbol
        if not symbol:
            return None

        # Determine target file
        target_path = diagnostic.file_path
        if not target_path or target_path not in allowed_scope:
            # Try to identify file in changeset or allowed_scope referencing this symbol
            for c in changeset.changes:
                if c.path in allowed_scope and c.content_bytes:
                    text = c.content_bytes.decode("utf-8", errors="replace")
                    if symbol in text:
                        target_path = c.path
                        break

        if not target_path or target_path not in allowed_scope:
            return None

        target_change = next((c for c in changeset.changes if c.path == target_path), None)
        if target_change is None or target_change.content_bytes is None:
            return None

        file_text = target_change.content_bytes.decode("utf-8", errors="replace")

        # 1. Check if symbol is a known standard library export
        module_path: str | None = _KNOWN_LIBRARY_EXPORTS.get(symbol)

        # 2. If not standard library, search for symbol export in other changeset files or staging
        if not module_path:
            for c in changeset.changes:
                if c.path == target_path:
                    continue
                if c.content_bytes:
                    other_text = c.content_bytes.decode("utf-8", errors="replace")
                    export_pattern = rf"export\s+(?:class|const|interface|type|enum)\s+{symbol}\b"
                    if re.search(export_pattern, other_text):
                        module_path = _compute_relative_import_path(target_path, c.path)
                        break

        # 3. If still not found, check staging dir on disk
        if not module_path and staging_dir and staging_dir.exists():
            for root, _, files in os.walk(staging_dir):
                for f in files:
                    if f.endswith(".ts") and not f.endswith(".spec.ts"):
                        full_f = Path(root) / f
                        rel_posix = full_f.relative_to(staging_dir).as_posix()
                        if rel_posix == target_path:
                            continue
                        content = full_f.read_text(encoding="utf-8", errors="replace")
                        export_pattern = (
                            rf"export\s+(?:class|const|interface|type|enum)\s+{symbol}\b"
                        )
                        if re.search(export_pattern, content):
                            module_path = _compute_relative_import_path(target_path, rel_posix)
                            break
                if module_path:
                    break

        if not module_path:
            return None

        # Apply import to file_text
        # Check if module is already imported
        existing_import_match = re.search(
            rf"import\s*\{{([^}}]+)\}}\s*from\s*['\"]{re.escape(module_path)}['\"];?",
            file_text,
        )
        if existing_import_match:
            imported_symbols = [
                s.strip() for s in existing_import_match.group(1).split(",") if s.strip()
            ]
            if symbol not in imported_symbols:
                imported_symbols.append(symbol)
                imported_symbols.sort()
                new_import = f"import {{ {', '.join(imported_symbols)} }} from '{module_path}';"
                new_text = (
                    file_text[: existing_import_match.start()]
                    + new_import
                    + file_text[existing_import_match.end() :]
                )
            else:
                return None
        else:
            # Prepend new import statement at top of imports
            new_import_line = f"import {{ {symbol} }} from '{module_path}';\n"
            # Place after first group of imports or at file top
            first_import = re.search(r"import\s+.*?;?\n", file_text)
            if first_import:
                insert_pos = first_import.start()
                new_text = file_text[:insert_pos] + new_import_line + file_text[insert_pos:]
            else:
                new_text = new_import_line + file_text

        new_bytes = new_text.encode("utf-8")
        updated_change = target_change.model_copy(
            update={
                "content_bytes": new_bytes,
                "content_digest": compute_file_sha256(new_bytes),
            }
        )
        new_changes = [updated_change if c.path == target_path else c for c in changeset.changes]
        return changeset.model_copy(
            update={
                "changeset_id": f"cs-repair-{uuid.uuid4().hex[:8]}",
                "changes": tuple(new_changes),
            }
        )


class SignalCallRepairStrategy:
    """Repairs uninvoked signal access by appending () in TypeScript code or template bindings."""

    def can_repair(
        self,
        diagnostic: StructuredDiagnostic,
        changeset: ChangeSet,
        allowed_scope: tuple[str, ...],
    ) -> bool:
        return diagnostic.category == DiagnosticCategory.SIGNAL_CALL_MISSING

    def repair(
        self,
        diagnostic: StructuredDiagnostic,
        changeset: ChangeSet,
        allowed_scope: tuple[str, ...],
        staging_dir: Path | None = None,
    ) -> ChangeSet | None:
        target_path = diagnostic.file_path
        if not target_path or target_path not in allowed_scope:
            for c in changeset.changes:
                if c.path in allowed_scope and c.path.endswith(".ts") and c.content_bytes:
                    target_path = c.path
                    break

        if not target_path or target_path not in allowed_scope:
            return None

        target_change = next((c for c in changeset.changes if c.path == target_path), None)
        if target_change is None or target_change.content_bytes is None:
            return None

        file_text = target_change.content_bytes.decode("utf-8", errors="replace")
        symbol = diagnostic.symbol

        if symbol:
            # Replace this.symbol (not followed by '(') with this.symbol()
            pattern = rf"\bthis\.{re.escape(symbol)}\b(?!\s*\()"
            new_text, count = re.subn(pattern, f"this.{symbol}()", file_text)
            if count == 0 and target_path.endswith(".html"):
                html_pattern = rf"\{{\{{\s*{re.escape(symbol)}\s*\}}\}}"
                new_text, count = re.subn(html_pattern, f"{{{{ {symbol}() }}}}", file_text)
        else:
            return None

        if count == 0:
            return None

        new_bytes = new_text.encode("utf-8")
        updated_change = target_change.model_copy(
            update={
                "content_bytes": new_bytes,
                "content_digest": compute_file_sha256(new_bytes),
            }
        )
        new_changes = [updated_change if c.path == target_path else c for c in changeset.changes]
        return changeset.model_copy(
            update={
                "changeset_id": f"cs-repair-{uuid.uuid4().hex[:8]}",
                "changes": tuple(new_changes),
            }
        )


class SpecTestBedRepairStrategy:
    """Repairs Jasmine/Angular TestBed spec failures like NullInjectorError for HttpClient."""

    def can_repair(
        self,
        diagnostic: StructuredDiagnostic,
        changeset: ChangeSet,
        allowed_scope: tuple[str, ...],
    ) -> bool:
        return diagnostic.category == DiagnosticCategory.SPEC_MOCK_MISSING

    def repair(
        self,
        diagnostic: StructuredDiagnostic,
        changeset: ChangeSet,
        allowed_scope: tuple[str, ...],
        staging_dir: Path | None = None,
    ) -> ChangeSet | None:
        spec_change = next(
            (
                c
                for c in changeset.changes
                if c.path.endswith(".spec.ts") and c.path in allowed_scope
            ),
            None,
        )
        if spec_change is None or spec_change.content_bytes is None:
            return None

        spec_text = spec_change.content_bytes.decode("utf-8", errors="replace")

        # Check for NullInjectorError for HttpClient
        if "HttpClient" in (diagnostic.symbol or "") or "HttpClient" in diagnostic.message:
            has_http_client = "provideHttpClient" in spec_text
            has_http_testing = "provideHttpClientTesting" in spec_text

            if has_http_client and has_http_testing:
                return None

            new_text = spec_text
            # 1. Add imports if missing
            if not has_http_client:
                import_stmt = "import { provideHttpClient } from '@angular/common/http';\n"
                new_text = import_stmt + new_text
            if not has_http_testing:
                import_stmt_test = (
                    "import { provideHttpClientTesting } from '@angular/common/http/testing';\n"
                )
                new_text = import_stmt_test + new_text

            # 2. Add providers to TestBed.configureTestingModule
            providers_match = re.search(r"providers\s*:\s*\[([^\]]*)\]", new_text)
            if providers_match:
                existing_provs = providers_match.group(1).strip()
                additions: list[str] = []
                if "provideHttpClient()" not in existing_provs:
                    additions.append("provideHttpClient()")
                if "provideHttpClientTesting()" not in existing_provs:
                    additions.append("provideHttpClientTesting()")

                if additions:
                    sep = ", " if existing_provs else ""
                    new_provs = existing_provs + sep + ", ".join(additions)
                    new_text = (
                        new_text[: providers_match.start(1)]
                        + new_provs
                        + new_text[providers_match.end(1) :]
                    )
            else:
                tb_match = re.search(r"TestBed\.configureTestingModule\s*\(\s*\{", new_text)
                if tb_match:
                    insert_pos = tb_match.end()
                    providers_block = (
                        "\n      providers: [provideHttpClient(), provideHttpClientTesting()],"
                    )
                    new_text = new_text[:insert_pos] + providers_block + new_text[insert_pos:]

            new_bytes = new_text.encode("utf-8")
            updated_change = spec_change.model_copy(
                update={
                    "content_bytes": new_bytes,
                    "content_digest": compute_file_sha256(new_bytes),
                }
            )
            new_changes = [
                updated_change if c.path == spec_change.path else c for c in changeset.changes
            ]
            return changeset.model_copy(
                update={
                    "changeset_id": f"cs-repair-{uuid.uuid4().hex[:8]}",
                    "changes": tuple(new_changes),
                }
            )

        return None


class SyntaxLintRepairStrategy:
    """Repairs trivial syntax, semicolon, and formatting issues."""

    def can_repair(
        self,
        diagnostic: StructuredDiagnostic,
        changeset: ChangeSet,
        allowed_scope: tuple[str, ...],
    ) -> bool:
        return diagnostic.category in (
            DiagnosticCategory.SYNTAX_ERROR,
            DiagnosticCategory.LINT_FORMAT,
        )

    def repair(
        self,
        diagnostic: StructuredDiagnostic,
        changeset: ChangeSet,
        allowed_scope: tuple[str, ...],
        staging_dir: Path | None = None,
    ) -> ChangeSet | None:
        target_path = diagnostic.file_path
        if not target_path or target_path not in allowed_scope:
            target_path = changeset.changes[0].path if changeset.changes else ""

        if not target_path or target_path not in allowed_scope:
            return None

        target_change = next((c for c in changeset.changes if c.path == target_path), None)
        if target_change is None or target_change.content_bytes is None:
            return None

        text = target_change.content_bytes.decode("utf-8", errors="replace")
        lines = [line.rstrip() for line in text.splitlines()]

        is_syntax = diagnostic.category == DiagnosticCategory.SYNTAX_ERROR
        is_semi = (
            ";" in diagnostic.message
            or "semi" in diagnostic.message.lower()
            or diagnostic.error_code in ("TS1005", "semi")
        )
        if is_syntax and is_semi:
            if diagnostic.line and 1 <= diagnostic.line <= len(lines):
                target_idx = diagnostic.line - 1
                if not lines[target_idx].endswith(";"):
                    lines[target_idx] += ";"
            else:
                for idx in range(len(lines)):
                    l_str = lines[idx].strip()
                    if l_str and not l_str.endswith((";", "{", "}", ",", "(", ")", ":")):
                        lines[idx] += ";"
                        break

        new_text = "\n".join(lines) + "\n"
        new_bytes = new_text.encode("utf-8")
        if compute_file_sha256(new_bytes) == target_change.content_digest:
            return None

        updated_change = target_change.model_copy(
            update={
                "content_bytes": new_bytes,
                "content_digest": compute_file_sha256(new_bytes),
            }
        )
        new_changes = [updated_change if c.path == target_path else c for c in changeset.changes]
        return changeset.model_copy(
            update={
                "changeset_id": f"cs-repair-{uuid.uuid4().hex[:8]}",
                "changes": tuple(new_changes),
            }
        )


class DeterministicRepairEngine:
    """Orchestrates deterministic repair strategies against structured diagnostics."""

    def __init__(self) -> None:
        self.strategies: list[RepairStrategy] = [
            AutoImportRepairStrategy(),
            SignalCallRepairStrategy(),
            SpecTestBedRepairStrategy(),
            SyntaxLintRepairStrategy(),
        ]

    def attempt_repair(
        self,
        diagnostics: list[StructuredDiagnostic],
        changeset: ChangeSet,
        allowed_scope: tuple[str, ...],
        staging_dir: Path | None = None,
    ) -> ChangeSet | None:
        """Attempt deterministic repair across parsed diagnostics."""
        for diag in diagnostics:
            for strategy in self.strategies:
                if strategy.can_repair(diag, changeset, allowed_scope):
                    repaired = strategy.repair(diag, changeset, allowed_scope, staging_dir)
                    if repaired is not None:
                        return repaired
        return None
