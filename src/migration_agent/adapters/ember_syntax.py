"""Bounded Ember syntax translation; unsupported semantics never become empty scaffolds."""

import ast
import json
import re
from dataclasses import dataclass, field

from migration_agent.ports.transformation import IntermediateComponent


def _unsupported(detail: str) -> ValueError:
    return ValueError(
        f"EMBER_CONSTRUCT_UNSUPPORTED: {detail}; use a grounded implementation proposal."
    )


def _parts(text: str, separator: str) -> list[str]:
    parts, start, depth = [], 0, []
    quote = ""
    escaped = False
    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
        elif char == "`":
            raise _unsupported("template literals require semantic review")
        elif char in "({[":
            depth.append(char)
        elif char in ")}]":
            if not depth or "({["[")}]".index(char)] != depth.pop():
                raise _unsupported("unbalanced JavaScript syntax")
        elif char == separator and not depth:
            parts.append(text[start:index].strip())
            start = index + 1
    if quote or depth:
        raise _unsupported("unbalanced JavaScript syntax")
    return [part for part in (*parts, text[start:].strip()) if part]


def _literal(value: str) -> tuple[str, str]:
    if value in {"true", "false"}:
        return "boolean", value
    if re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?", value):
        return "number", value
    if value.startswith(("'", '"')):
        try:
            literal = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            raise _unsupported("invalid string literal") from None
        if isinstance(literal, str):
            return "string", json.dumps(literal, ensure_ascii=False)
    if value in {"[]", "A()"}:
        return "unknown[]", "[]"
    raise _unsupported("computed properties, object state or nonliteral defaults")


@dataclass(frozen=True)
class EmberSemantics:
    defaults: dict[str, str] = field(default_factory=dict)
    types: dict[str, str] = field(default_factory=dict)
    bodies: dict[str, str] = field(default_factory=dict)


def component_semantics(source: str) -> EmberSemantics:
    # Comments are rejected rather than stripped inside strings or expressions.
    match = re.search(
        r"export\s+default\s+Component\.extend\(\s*\{(.*)\}\s*\)\s*;?\s*$", source, re.DOTALL
    )
    if match is None:
        raise _unsupported("only a single plain Component.extend object is mechanically supported")
    prefix = source[: match.start()]
    for imported in re.findall(r"import\s+([^;]+);", prefix):
        if not re.fullmatch(
            r"(?:Component\s+from\s+['\"]@ember/component['\"]"
            r"|\{\s*A\s*\}\s+from\s+['\"]@ember/array['\"]"
            r"|\{\s*inject\s+as\s+service\s*\}\s+from\s+['\"]@ember/service['\"])",
            imported.strip(),
        ):
            raise _unsupported("unknown imports or import side effects")
    if re.sub(r"import\s+[^;]+;\s*", "", prefix).strip():
        raise _unsupported("top-level side effects or custom component inheritance")
    defaults: dict[str, str] = {}
    types: dict[str, str] = {}
    methods: dict[str, str] = {}

    def method(value: str) -> None:
        found = re.fullmatch(r"([A-Za-z_$][\w$]*)\s*\(\s*\)\s*\{(.*)\}", value, re.DOTALL)
        if found is None:
            raise _unsupported("parameterized methods or nonstandard action syntax")
        name, body = found.groups()
        if name in {
            "init",
            "didInsertElement",
            "willDestroyElement",
            "didReceiveAttrs",
            "didUpdateAttrs",
            "didUpdate",
        }:
            raise _unsupported(f"lifecycle hook {name}")
        if name in methods:
            raise _unsupported("duplicate action/method names")
        methods[name] = body

    for member in _parts(match.group(1), ","):
        if re.match(r"[A-Za-z_$][\w$]*\s*\(", member):
            method(member)
            continue
        entry = re.fullmatch(r"([A-Za-z_$][\w$]*)\s*:\s*(.*)", member, re.DOTALL)
        if entry is None:
            raise _unsupported("spread, shorthand or nonstandard properties")
        name, value = entry.groups()
        if name == "actions":
            if not value.startswith("{") or not value.endswith("}"):
                raise _unsupported("action object syntax")
            for action in _parts(value[1:-1], ","):
                method(action)
        elif re.fullmatch(
            r"(?:Ember\.)?(?:inject\.)?service\(\s*(?:['\"][^'\"]+['\"])?\s*\)", value
        ):
            continue
        else:
            if name in defaults or name in {
                "tagName",
                "classNames",
                "classNameBindings",
                "attributeBindings",
            }:
                raise _unsupported("duplicate properties or custom host attributes")
            types[name], defaults[name] = _literal(value)
    bodies = {}
    for name, body in methods.items():
        statements = []
        for statement in _parts(body, ";"):
            toggle = re.fullmatch(r"this\.toggleProperty\(['\"]([\w$]+)['\"]\)", statement)
            setting = re.fullmatch(
                r"this\.set\(['\"]([\w$]+)['\"]\s*,\s*(.*)\)", statement, re.DOTALL
            )
            if toggle and types.get(toggle.group(1)) == "boolean":
                statements.append(f"this.{toggle.group(1)}.update((current) => !current);")
            elif setting and setting.group(1) in types:
                literal_type, literal = _literal(setting.group(2).strip())
                if literal_type != types[setting.group(1)]:
                    raise _unsupported("state assignment changes its declared type")
                statements.append(f"this.{setting.group(1)}.set({literal});")
            else:
                raise _unsupported(f"method {name} contains unsupported statements")
        bodies[name] = "\n".join(statements)
    return EmberSemantics(defaults, types, bodies)


def translate_template(component: IntermediateComponent) -> str:
    raw = component.template_raw
    if "{{{" in raw or "}}}" in raw:
        raise _unsupported("unescaped triple-brace template content")
    parts = re.split(r"(\{\{.*?\}\})", raw, flags=re.DOTALL)
    unmatched = re.sub(r"\{\{.*?\}\}", "", raw, flags=re.DOTALL)
    if "{{" in unmatched or "}}" in unmatched:
        raise _unsupported("unterminated template construct")
    stack: list[str] = []
    output = []
    consumed = 0

    def expression(value: str) -> str:
        if value.startswith("@") and value[1:] in component.inputs:
            return value[1:] + "()"
        name = value.removeprefix("this.")
        if name in component.state_properties or name in component.inputs:
            return name + "()"
        raise _unsupported(f"template expression {value[:80]!r}")

    for part in parts:
        prefix = raw[:consumed]
        consumed += len(part)
        if not part.startswith("{{"):
            output.append(part.replace("@", "&#64;").replace("{", "&#123;").replace("}", "&#125;"))
            continue
        token = part[2:-2].strip()
        if token.startswith(("#if ", "#unless ")):
            kind, value = token[1:].split(maxsplit=1)
            stack.append(kind)
            output.append(f"@if ({'!' if kind == 'unless' else ''}{expression(value)}) {{")
        elif token == "else":
            if not stack:
                raise _unsupported("else without a matching conditional")
            output.append("} @else {")
        elif token in {"/if", "/unless"}:
            if not stack or stack.pop() != token[1:]:
                raise _unsupported("mismatched template conditional")
            output.append("}")
        elif token.startswith("action "):
            tag = prefix[prefix.rfind("<") :]
            if (
                prefix.rfind("<") <= prefix.rfind(">")
                or not re.match(r"<[A-Za-z][\w-]*(?:\s|$)", tag)
                or re.search(r"=['\"][^'\"]*$", tag)
            ):
                raise _unsupported("action helpers require an opening element modifier position")
            action = re.fullmatch(r"action\s+['\"]([\w$]+)['\"]", token)
            if action is None or action.group(1) not in component.methods:
                raise _unsupported("unknown or parameterized template action")
            output.append(f'(click)="{action.group(1)}()"')
        elif token.startswith("!"):
            continue
        else:
            output.append("{{ " + expression(token) + " }}")
    if stack or "{{" in re.sub(r"\{\{.*?\}\}", "", raw, flags=re.DOTALL):
        raise _unsupported("unterminated template construct")
    return "".join(output)
