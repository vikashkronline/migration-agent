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
    AgentInventoryInterpretationOutput,
    AgentPlanCritiqueOutput,
    AgentPlanningOutput,
    AgentRepairDiagnosisOutput,
    map_agent_critique_output_to_domain,
    map_agent_diagnosis_output_to_domain,
    map_agent_interpretation_output_to_domain,
    map_agent_output_to_domain,
    map_agent_plan_output_to_domain,
)
from migration_agent.domain import (
    AnalysisResult,
    InventoryInterpretation,
    InventoryInterpretationRequest,
    MigrationAnalysisOutput,
    MigrationAnalystRequest,
    MigrationStep,
    PlanCriticRequest,
    PlanCritique,
    ProjectInventory,
    RepairDiagnosis,
    RepairDiagnosticianRequest,
)
from migration_agent.ports import (
    AgentRuntimePort,
    AnalysisRequest,
    FileReaderPort,
    PlanningRequest,
    SpecialistRuntimePort,
)

# Remote Agents SDK trace export is disabled by default for privacy and local execution safety.
set_tracing_disabled(True)


class OpenAIAgentsRuntimeAdapter(AgentRuntimePort, SpecialistRuntimePort):
    """OpenAI Agents SDK adapter for analysis, planning, and specialists."""

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

    def interpret_inventory(
        self,
        request: InventoryInterpretationRequest,
    ) -> InventoryInterpretation:
        """Synthesize high-level domain insights and framework notes from repository inventory."""
        agent = self.create_inventory_interpreter_agent(request.inventory)
        user_prompt = (
            f"Interpret the repository inventory for '{request.inventory.repository.name}'. "
            "Synthesize an architectural summary, framework assessment notes, key migration risks, "
            "and a recommended high-level migration strategy."
        )
        run_config = RunConfig(tracing_disabled=True)
        run_result = Runner.run_sync(
            agent,
            user_prompt,
            max_turns=5,
            run_config=run_config,
        )
        raw_output = run_result.final_output
        if isinstance(raw_output, AgentInventoryInterpretationOutput):
            output = raw_output
        elif isinstance(raw_output, str):
            output = AgentInventoryInterpretationOutput.model_validate_json(raw_output)
        elif isinstance(raw_output, dict):
            output = AgentInventoryInterpretationOutput.model_validate(raw_output)
        else:
            raise TypeError(f"Unexpected interpreter output type: {type(raw_output)}")
        return map_agent_interpretation_output_to_domain(output)

    def analyze_migration(
        self,
        request: MigrationAnalystRequest,
        file_reader: FileReaderPort,
    ) -> MigrationAnalysisOutput:
        """Perform deep code-level migration analysis against eligible repository files."""
        analysis_req = AnalysisRequest(
            inventory=request.inventory,
            provider="openai",
            model="gpt-4o",
            max_turns=request.max_turns,
            dry_run=True,
        )
        res = self.analyze(analysis_req, file_reader)
        return MigrationAnalysisOutput(
            summary=res.summary,
            findings=res.findings,
            assumptions=res.assumptions,
            unsupported_constructs=res.unsupported_constructs,
            questions=res.questions,
        )

    def criticize_plan(
        self,
        request: PlanCriticRequest,
    ) -> PlanCritique:
        """Audit candidate migration plan for risk, missing dependencies, and quality issues."""
        agent = self.create_plan_critic_agent()
        plan_summary = [
            {
                "step_id": s.step_id,
                "title": s.title,
                "dependencies": s.dependencies,
                "expected_files": s.expected_files,
                "risk": s.risk.value,
            }
            for s in request.plan.steps
        ]
        repo = request.inventory.repository.name
        user_prompt = (
            f"Audit and critique the following migration plan for '{repo}':\n"
            f"{json.dumps(plan_summary, indent=2)}\n\n"
            "Identify missing dependencies, sequencing flaws, and provide an overall score."
        )
        run_config = RunConfig(tracing_disabled=True)
        run_result = Runner.run_sync(
            agent,
            user_prompt,
            max_turns=5,
            run_config=run_config,
        )
        raw_output = run_result.final_output
        if isinstance(raw_output, AgentPlanCritiqueOutput):
            output = raw_output
        elif isinstance(raw_output, str):
            output = AgentPlanCritiqueOutput.model_validate_json(raw_output)
        elif isinstance(raw_output, dict):
            output = AgentPlanCritiqueOutput.model_validate(raw_output)
        else:
            raise TypeError(f"Unexpected critic output type: {type(raw_output)}")
        return map_agent_critique_output_to_domain(output)

    def diagnose_repair(
        self,
        request: RepairDiagnosticianRequest,
    ) -> RepairDiagnosis:
        """Diagnose validation command failure and propose targeted, in-scope repair guidance."""
        agent = self.create_repair_diagnostician_agent()
        diag_input = {
            "command": request.failing_result.command,
            "exit_code": request.failing_result.exit_code,
            "diagnostics": list(request.failing_result.diagnostics),
            "output_preview": request.failing_result.sanitized_output[:500],
            "allowed_scope": list(request.allowed_scope),
            "previous_attempt_count": len(request.previous_attempts),
        }
        user_prompt = (
            f"Diagnose the following validation failure:\n{json.dumps(diag_input, indent=2)}\n\n"
            "Propose a targeted root-cause analysis and identify which file requires fixing."
        )
        run_config = RunConfig(tracing_disabled=True)
        run_result = Runner.run_sync(
            agent,
            user_prompt,
            max_turns=5,
            run_config=run_config,
        )
        raw_output = run_result.final_output
        if isinstance(raw_output, AgentRepairDiagnosisOutput):
            output = raw_output
        elif isinstance(raw_output, str):
            output = AgentRepairDiagnosisOutput.model_validate_json(raw_output)
        elif isinstance(raw_output, dict):
            output = AgentRepairDiagnosisOutput.model_validate(raw_output)
        else:
            raise TypeError(f"Unexpected diagnostician output type: {type(raw_output)}")
        return map_agent_diagnosis_output_to_domain(output)

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

    @classmethod
    def create_inventory_interpreter_agent(
        cls,
        inventory: ProjectInventory,
        model: str = "gpt-4o",
    ) -> Agent[None]:
        """Create the read-only inventory interpreter agent."""
        instructions = (
            "You are a specialized software architecture interpreter. Your task is to analyze\n"
            "the repository inventory (frameworks, dependencies, package boundaries, issues)\n"
            "and synthesize high-level architectural insights, framework assessment notes,\n"
            "critical migration risks, and a recommended migration strategy.\n\n"
            "You are strictly read-only and must produce output matching the required schema."
        )
        model_name = model or "gpt-4o"
        return Agent(
            name="InventoryInterpreterAgent",
            instructions=instructions,
            model=model_name,
            output_type=AgentInventoryInterpretationOutput,
        )

    @classmethod
    def create_plan_critic_agent(
        cls,
        model: str = "gpt-4o",
    ) -> Agent[None]:
        """Create the focused migration plan critic agent."""
        instructions = (
            "You are an adversarial, critical software migration plan reviewer. You audit\n"
            "candidate migration plans to uncover sequencing flaws, missing prerequisite\n"
            "dependencies, circular dependencies, oversized step scopes (>10 files), and\n"
            "unaddressed migration risks.\n\n"
            "Evaluate each step carefully, assign an overall plan quality score between\n"
            "0.0 and 1.0, and indicate whether approval is recommended or revisions are required.\n"
            "You are strictly read-only and must produce structured JSON output matching\n"
            "the required schema."
        )
        model_name = model or "gpt-4o"
        return Agent(
            name="PlanCriticAgent",
            instructions=instructions,
            model=model_name,
            output_type=AgentPlanCritiqueOutput,
        )

    @classmethod
    def create_repair_diagnostician_agent(
        cls,
        model: str = "gpt-4o",
    ) -> Agent[None]:
        """Create the validation failure repair diagnostician agent."""
        instructions = (
            "You are an expert diagnostic assistant specializing in build, compilation, lint,\n"
            "and test failures. Your role is to diagnose the root cause of a validation failure\n"
            "and identify which specific file within the pre-approved allowed_scope should be\n"
            "modified, along with a concise fix summary.\n\n"
            "Constraints:\n"
            "1. You must ONLY recommend files that exist in the provided allowed_scope.\n"
            "2. If the failure cannot be resolved within scope, indicate actionable=false.\n"
            "3. You are strictly read-only and do not perform file writes or run commands."
        )
        model_name = model or "gpt-4o"
        return Agent(
            name="RepairDiagnosticianAgent",
            instructions=instructions,
            model=model_name,
            output_type=AgentRepairDiagnosisOutput,
        )
