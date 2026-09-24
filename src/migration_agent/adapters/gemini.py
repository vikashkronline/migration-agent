"""Google Gemini runtime adapter for read-only migration analysis and planning."""

import json
import os
from typing import Any

from google import genai
from google.genai import types

from migration_agent.adapters.schemas import (
    AgentAnalysisOutput,
    AgentPlanningOutput,
    map_agent_output_to_domain,
    map_agent_plan_output_to_domain,
)
from migration_agent.domain import AnalysisResult, MigrationStep
from migration_agent.ports import (
    AgentRuntimePort,
    AnalysisRequest,
    FileReaderPort,
    PlanningRequest,
)


class GeminiRuntimeAdapter(AgentRuntimePort):
    """Google Gemini runtime adapter utilizing the official Google GenAI SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    def _get_api_key(self) -> str:
        key = self._api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise ValueError("Neither GEMINI_API_KEY nor GOOGLE_API_KEY is set in environment.")
        return key

    def analyze(
        self,
        request: AnalysisRequest,
        file_reader: FileReaderPort,
    ) -> AnalysisResult:
        """Run read-only analysis using Google Gemini and return typed findings."""
        key = self._get_api_key()
        client = genai.Client(api_key=key)
        eligible_paths = {f.path for f in request.inventory.files}

        def query_inventory(section: str = "summary") -> str:
            """Query the deterministic repository inventory.

            Sections: summary, frameworks, dependencies, files, boundaries, issues, exclusions.
            """
            section_clean = section.strip().lower()
            data: Any
            if section_clean == "summary":
                data = {
                    "repository": request.inventory.repository.name,
                    "eligible_files_count": len(request.inventory.files),
                    "dependencies_count": len(request.inventory.dependencies),
                    "frameworks": [f.framework_id for f in request.inventory.frameworks],
                    "issues_count": len(request.inventory.issues),
                }
            elif section_clean == "frameworks":
                data = [f.model_dump() for f in request.inventory.frameworks]
            elif section_clean == "dependencies":
                data = [d.model_dump() for d in request.inventory.dependencies]
            elif section_clean == "files":
                data = [f.model_dump() for f in request.inventory.files]
            elif section_clean == "package_boundaries":
                data = [b.model_dump() for b in request.inventory.package_boundaries]
            elif section_clean == "issues":
                data = [i.model_dump() for i in request.inventory.issues]
            elif section_clean == "exclusions":
                data = request.inventory.exclusions.model_dump()
            else:
                return (
                    f"Error: Unknown section '{section}'. Valid: summary, frameworks, "
                    "dependencies, files, package_boundaries, issues, exclusions."
                )

            result_str = json.dumps(data, indent=2, sort_keys=True)
            if len(result_str) > request.max_tool_chars:
                return (
                    result_str[: request.max_tool_chars]
                    + f"\n... [Truncated: exceeded {request.max_tool_chars} characters]"
                )
            return result_str

        def read_repository_file(path: str, start_line: int = 1, line_count: int = 200) -> str:
            """Read bounded text lines from an eligible repository file.

            Args:
                path: Repository-relative POSIX path of an eligible file in inventory.
                start_line: 1-indexed line to start reading from.
                line_count: Number of lines to read (max 500).
            """
            normalized = path.replace("\\", "/").strip().lstrip("/")
            if normalized not in eligible_paths:
                return (
                    f"Error: Path '{path}' is not an eligible inventory text file. Access denied."
                )

            try:
                content = file_reader.read_file(normalized)
            except Exception as exc:
                return f"Error reading file '{normalized}': {exc}"

            lines = content.splitlines()
            start_idx = max(0, start_line - 1)
            bounded_count = min(max(1, line_count), 500)
            selected_lines = lines[start_idx : start_idx + bounded_count]

            result_text = "\n".join(
                f"{idx + start_idx + 1}: {line}" for idx, line in enumerate(selected_lines)
            )
            if len(result_text) > request.max_tool_chars:
                return (
                    result_text[: request.max_tool_chars]
                    + f"\n... [Truncated: exceeded {request.max_tool_chars} characters]"
                )
            return result_text

        instructions = (
            "You are a read-only code migration analysis agent. You interpret the repository "
            "inventory and inspect eligible text files to produce high-integrity structured "
            "migration findings.\n\n"
            "Core principles you must follow strictly:\n"
            "1. Never claim full coverage. You only analyze observed files.\n"
            "2. Never invent files, symbols, framework APIs, or dependencies. Only reference paths "
            "returned by tools.\n"
            "3. Separate observed facts from inferences.\n"
            "4. Cite concrete evidence (exact repository-relative POSIX path) for each finding.\n"
            "5. Return unsupported/uncertain when confidence is inadequate.\n"
            "6. You are strictly read-only. You cannot write files or execute commands.\n\n"
            "Always produce output matching the required structured schema."
        )

        user_prompt = (
            f"Analyze the repository '{request.inventory.repository.name}' for migration planning. "
            "Inspect the inventory and eligible files using your tools to identify architecture "
            "patterns, component constructs, framework dependencies, and migration risks. "
            "Produce structured findings following your instruction principles."
        )

        config = types.GenerateContentConfig(
            system_instruction=instructions,
            tools=[query_inventory, read_repository_file],
            response_mime_type="application/json",
            response_schema=AgentAnalysisOutput,
        )

        model_name = request.model or "gemini-2.5-pro"
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=config,
        )

        raw_parsed = getattr(response, "parsed", None)
        if isinstance(raw_parsed, AgentAnalysisOutput):
            agent_output = raw_parsed
        elif response.text:
            agent_output = AgentAnalysisOutput.model_validate_json(response.text)
        else:
            raise ValueError("Gemini model returned empty response without structured output.")

        return map_agent_output_to_domain(agent_output, request)

    def plan(
        self,
        request: PlanningRequest,
    ) -> list[MigrationStep]:
        """Generate structured migration steps using Google Gemini structured output."""
        key = self._get_api_key()
        client = genai.Client(api_key=key)

        instructions = (
            "You are a code migration planning agent. You convert repository inventory "
            "and analysis findings into an ordered sequence of discrete migration steps.\n\n"
            "Principles you must follow strictly:\n"
            "1. Each step must have a unique stable ID (e.g. 'step-001', 'step-002').\n"
            "2. Establish step dependencies to avoid cycles and form a valid DAG.\n"
            "3. Every step must have a concrete, actionable validation strategy.\n"
            "4. Only reference real evidence paths from analysis findings.\n"
            "5. Include clear rollback notes and acceptance criteria.\n"
            "6. Output must conform to the requested JSON schema."
        )

        findings_summary = [
            {
                "id": f.id,
                "title": f.title,
                "category": f.category.value,
                "severity": f.severity.value,
                "evidence": [e.path for e in f.evidence_references],
            }
            for f in request.analysis.findings
        ]

        user_prompt = (
            f"Generate an ordered migration plan for '{request.inventory.repository.name}'.\n\n"
            f"Analysis Findings:\n{json.dumps(findings_summary, indent=2)}\n\n"
            "Produce structured migration steps following the planning instructions."
        )

        config = types.GenerateContentConfig(
            system_instruction=instructions,
            response_mime_type="application/json",
            response_schema=AgentPlanningOutput,
        )

        model_name = request.model or "gemini-2.5-pro"
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=config,
        )

        raw_parsed = getattr(response, "parsed", None)
        if isinstance(raw_parsed, AgentPlanningOutput):
            planning_output = raw_parsed
        elif response.text:
            planning_output = AgentPlanningOutput.model_validate_json(response.text)
        else:
            raise ValueError("Gemini model returned empty planning response.")

        return map_agent_plan_output_to_domain(planning_output)
