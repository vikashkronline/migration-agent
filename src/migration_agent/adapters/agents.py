"""OpenAI Agents SDK runtime adapter for read-only migration analysis and planning."""

import json
from typing import Any

from agents import (
    Agent,
    FunctionTool,
    RunConfig,
    Runner,
    function_tool,
    set_tracing_disabled,
)

from migration_agent.adapters.schemas import (
    AgentAnalysisOutput,
    AgentPlanningOutput,
    map_agent_output_to_domain,
    map_agent_plan_output_to_domain,
)
from migration_agent.domain import AnalysisResult, MigrationStep, ProjectInventory
from migration_agent.ports import (
    AgentRuntimePort,
    AnalysisRequest,
    FileReaderPort,
    PlanningRequest,
)

# Remote Agents SDK trace export is disabled by default for privacy and local execution safety.
set_tracing_disabled(True)


class OpenAIAgentsRuntimeAdapter(AgentRuntimePort):
    """Application-hosted OpenAI Agents SDK adapter for read-only analysis and planning."""

    def __init__(self) -> None:
        set_tracing_disabled(True)

    def analyze(
        self,
        request: AnalysisRequest,
        file_reader: FileReaderPort,
    ) -> AnalysisResult:
        """Run one read-only migration analysis agent against the repository inventory."""
        agent = self.create_analysis_agent(
            inventory=request.inventory,
            file_reader=file_reader,
            model=request.model,
            max_tool_chars=request.max_tool_chars,
        )

        user_prompt = (
            f"Analyze the repository '{request.inventory.repository.name}' for migration planning. "
            "Inspect the inventory and eligible files using your tools to identify architecture "
            "patterns, component constructs, framework dependencies, and migration risks. "
            "Produce structured findings following your instruction principles."
        )

        run_config = RunConfig(tracing_disabled=True)
        run_result = Runner.run_sync(
            agent,
            user_prompt,
            max_turns=request.max_turns,
            run_config=run_config,
        )

        raw_output = run_result.final_output
        if isinstance(raw_output, AgentAnalysisOutput):
            agent_output = raw_output
        elif isinstance(raw_output, str):
            agent_output = AgentAnalysisOutput.model_validate_json(raw_output)
        elif isinstance(raw_output, dict):
            agent_output = AgentAnalysisOutput.model_validate(raw_output)
        else:
            raise TypeError(f"Unexpected agent output type: {type(raw_output)}")

        return map_agent_output_to_domain(agent_output, request)

    def plan(
        self,
        request: PlanningRequest,
    ) -> list[MigrationStep]:
        """Generate structured migration steps using OpenAI Agents structured output."""
        agent = self.create_planning_agent(
            model=request.model,
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

        run_config = RunConfig(tracing_disabled=True)
        run_result = Runner.run_sync(
            agent,
            user_prompt,
            max_turns=request.max_turns,
            run_config=run_config,
        )

        raw_output = run_result.final_output
        if isinstance(raw_output, AgentPlanningOutput):
            planning_output = raw_output
        elif isinstance(raw_output, str):
            planning_output = AgentPlanningOutput.model_validate_json(raw_output)
        elif isinstance(raw_output, dict):
            planning_output = AgentPlanningOutput.model_validate(raw_output)
        else:
            raise TypeError(f"Unexpected planner agent output type: {type(raw_output)}")

        return map_agent_plan_output_to_domain(planning_output)

    @classmethod
    def create_analysis_agent(
        cls,
        inventory: ProjectInventory,
        file_reader: FileReaderPort,
        model: str,
        max_tool_chars: int = 20_000,
    ) -> Agent[None]:
        """Create the focused read-only analysis agent equipped with bounded tools."""
        eligible_paths = {f.path for f in inventory.files}

        def query_inventory(section: str = "summary") -> str:
            """Query the deterministic repository inventory.

            Sections: summary, frameworks, dependencies, files, boundaries, issues, exclusions.
            """
            section_clean = section.strip().lower()
            data: Any
            if section_clean == "summary":
                data = {
                    "repository": inventory.repository.name,
                    "eligible_files_count": len(inventory.files),
                    "dependencies_count": len(inventory.dependencies),
                    "frameworks": [f.framework_id for f in inventory.frameworks],
                    "issues_count": len(inventory.issues),
                }
            elif section_clean == "frameworks":
                data = [f.model_dump() for f in inventory.frameworks]
            elif section_clean == "dependencies":
                data = [d.model_dump() for d in inventory.dependencies]
            elif section_clean == "files":
                data = [f.model_dump() for f in inventory.files]
            elif section_clean == "package_boundaries":
                data = [b.model_dump() for b in inventory.package_boundaries]
            elif section_clean == "issues":
                data = [i.model_dump() for i in inventory.issues]
            elif section_clean == "exclusions":
                data = inventory.exclusions.model_dump()
            else:
                return (
                    f"Error: Unknown section '{section}'. Valid: summary, frameworks, "
                    "dependencies, files, package_boundaries, issues, exclusions."
                )

            result_str = json.dumps(data, indent=2, sort_keys=True)
            if len(result_str) > max_tool_chars:
                return (
                    result_str[:max_tool_chars]
                    + f"\n... [Truncated: exceeded {max_tool_chars} characters]"
                )
            return result_str

        def read_repository_file(path: str, start_line: int = 1, line_count: int = 200) -> str:
            """Read bounded text lines from an explicitly eligible repository file.

            Args:
                path: Repository-relative POSIX path of an eligible file in the inventory.
                start_line: 1-indexed line to start reading from (default 1).
                line_count: Number of lines to read (maximum 500).
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
            if len(result_text) > max_tool_chars:
                return (
                    result_text[:max_tool_chars]
                    + f"\n... [Truncated: exceeded {max_tool_chars} characters]"
                )
            return result_text

        query_tool: FunctionTool = function_tool(query_inventory)
        read_tool: FunctionTool = function_tool(read_repository_file)

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

        model_name = model or "gpt-4o"
        return Agent(
            name="MigrationAnalysisAgent",
            instructions=instructions,
            model=model_name,
            tools=[query_tool, read_tool],
            output_type=AgentAnalysisOutput,
        )

    @classmethod
    def create_planning_agent(
        cls,
        model: str,
    ) -> Agent[None]:
        """Create the focused migration planning agent."""
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

        model_name = model or "gpt-4o"
        return Agent(
            name="MigrationPlanningAgent",
            instructions=instructions,
            model=model_name,
            output_type=AgentPlanningOutput,
        )
