"""Unit tests for compiler, spec, and linter diagnostic parsing."""

from migration_agent.application.diagnostics import (
    DiagnosticCategory,
    parse_diagnostics,
)


def test_parse_typescript_parenthesized_error() -> None:
    output = (
        "src/app/components/user-profile/user-profile.component.ts(14,28): "
        "error TS2304: Cannot find name 'UserDataService'."
    )
    diags = parse_diagnostics(output)

    assert len(diags) == 1
    d = diags[0]
    assert d.file_path == "src/app/components/user-profile/user-profile.component.ts"
    assert d.line == 14
    assert d.column == 28
    assert d.error_code == "TS2304"
    assert d.category == DiagnosticCategory.MISSING_IMPORT
    assert d.symbol == "UserDataService"
    assert "Import 'UserDataService'" in d.suggested_fix


def test_parse_typescript_colon_signal_call_missing() -> None:
    output = (
        "src/app/components/user-profile/user-profile.component.ts:18:9 - "
        "error TS2551: Property 'name' does not exist on type 'UserProfileComponent'. "
        "Did you mean 'name()'?"
    )
    diags = parse_diagnostics(output)

    assert len(diags) == 1
    d = diags[0]
    assert d.file_path == "src/app/components/user-profile/user-profile.component.ts"
    assert d.line == 18
    assert d.column == 9
    assert d.error_code == "TS2551"
    assert d.category == DiagnosticCategory.SIGNAL_CALL_MISSING
    assert d.symbol == "name"
    assert "Invoke signal function" in d.suggested_fix


def test_parse_typescript_type_mismatch() -> None:
    output = (
        "src/app/components/user-badge/user-badge.component.ts(8,3): "
        "error TS2322: Type 'number' is not assignable to type 'string'."
    )
    diags = parse_diagnostics(output)

    assert len(diags) == 1
    d = diags[0]
    assert d.category == DiagnosticCategory.TYPE_MISMATCH
    assert d.error_code == "TS2322"
    assert d.line == 8
    assert d.column == 3


def test_parse_typescript_syntax_error() -> None:
    output = (
        "src/app/components/user-card/user-card.component.ts(5,12): error TS1005: ';' expected."
    )
    diags = parse_diagnostics(output)

    assert len(diags) == 1
    d = diags[0]
    assert d.category == DiagnosticCategory.SYNTAX_ERROR
    assert d.error_code == "TS1005"
    assert d.line == 5


def test_parse_jasmine_null_injector_error() -> None:
    output = (
        "NullInjectorError: R3InjectorError(Standalone[UserComponent]): "
        "NullInjectorError: No provider for HttpClient!"
    )
    diags = parse_diagnostics(output)

    assert len(diags) == 1
    d = diags[0]
    assert d.category == DiagnosticCategory.SPEC_MOCK_MISSING
    assert d.symbol == "HttpClient"
    assert d.error_code == "NullInjectorError"
    assert "Provide 'HttpClient'" in d.suggested_fix


def test_parse_eslint_no_undef_error() -> None:
    output = (
        "src/app/components/activity-feed/activity-feed.component.ts:12:5: "
        "'UserDataService' is not defined. [Error/no-undef]"
    )
    diags = parse_diagnostics(output)

    assert len(diags) == 1
    d = diags[0]
    assert d.file_path == "src/app/components/activity-feed/activity-feed.component.ts"
    assert d.line == 12
    assert d.column == 5
    assert d.category == DiagnosticCategory.MISSING_IMPORT
    assert d.symbol == "UserDataService"
    assert d.error_code == "no-undef"


def test_parse_loose_diagnostics_fallback() -> None:
    diags = parse_diagnostics("", diagnostics=("Cannot find name 'inject'", "Missing semicolon"))

    assert len(diags) == 2
    assert diags[0].category == DiagnosticCategory.MISSING_IMPORT
    assert diags[0].symbol == "inject"
    assert diags[1].category == DiagnosticCategory.SYNTAX_ERROR
