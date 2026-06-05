"""
JARVIS Workflow Engine — execute multi-step AI workflows with checkpointing.

Allows JARVIS to run long sequences of tool calls and AI reasoning steps
that survive provider timeouts and can be resumed.
"""
import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Callable, Awaitable
from loguru import logger

class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class WorkflowStep:
    id: str
    name: str
    instruction: str          # What to tell the AI for this step
    depends_on: list[str] = field(default_factory=list)  # step IDs that must complete first
    status: StepStatus = StepStatus.PENDING
    result: str = ""
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    max_retries: int = 1       # how many times to retry on failure
    duration_s: float = 0.0   # wall-clock duration of the last successful (or final) run

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowStep:
        data = dict(data)
        if isinstance(data.get("status"), str):
            data["status"] = StepStatus(data["status"])
        # Strip unknown keys so old checkpoints can be loaded after schema changes
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        data = {k: v for k, v in data.items() if k in known}
        return cls(**data)

@dataclass
class Workflow:
    id: str
    name: str
    description: str
    steps: list[WorkflowStep]
    created_at: float = field(default_factory=time.time)
    status: StepStatus = StepStatus.PENDING
    checkpoint_path: str = ""  # path to save/restore state

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "status": self.status.value,
            "checkpoint_path": self.checkpoint_path,
        })

    @classmethod
    def from_json(cls, data: str) -> Workflow:
        obj = json.loads(data)
        steps = [WorkflowStep.from_dict(s) for s in obj.get("steps", [])]
        status = StepStatus(obj.get("status", "pending"))
        return cls(
            id=obj["id"],
            name=obj["name"],
            description=obj["description"],
            steps=steps,
            created_at=obj.get("created_at", time.time()),
            status=status,
            checkpoint_path=obj.get("checkpoint_path", ""),
        )

    def save_checkpoint(self) -> None:
        """Save current state to checkpoint_path."""
        if not self.checkpoint_path:
            return
        try:
            Path(self.checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.checkpoint_path, "w") as f:
                f.write(self.to_json())
            logger.debug(f"Saved workflow checkpoint: {self.checkpoint_path}")
        except Exception as e:
            logger.error(f"Failed to save workflow checkpoint: {e}")

    @classmethod
    def load_checkpoint(cls, path: str) -> Workflow | None:
        """Load workflow from checkpoint file."""
        try:
            with open(path, "r") as f:
                return cls.from_json(f.read())
        except Exception as e:
            logger.error(f"Failed to load workflow checkpoint: {e}")
            return None

class WorkflowEngine:
    def __init__(self, checkpoint_dir: str = "data/workflows"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._active_workflows: dict[str, Workflow] = {}
        self._on_step_start: list[Callable] = []
        self._on_step_done: list[Callable] = []
        self._on_workflow_done: list[Callable] = []

    def on_step_start(self, callback: Callable[[WorkflowStep], None]) -> None:
        self._on_step_start.append(callback)

    def on_step_done(self, callback: Callable[[WorkflowStep], None]) -> None:
        self._on_step_done.append(callback)

    def on_workflow_done(self, callback: Callable[[Workflow], None]) -> None:
        self._on_workflow_done.append(callback)

    async def create_workflow(
        self,
        name: str,
        steps: list[dict],  # [{"name": ..., "instruction": ..., "depends_on": [...]}]
        description: str = "",
    ) -> Workflow:
        """Create a new workflow from step definitions."""
        wf_id = f"wf_{int(time.time())}"
        wf_steps = []
        for i, s in enumerate(steps):
            wf_steps.append(WorkflowStep(
                id=f"step_{i}",
                name=s.get("name", f"Step {i+1}"),
                instruction=s["instruction"],
                depends_on=s.get("depends_on", []),
            ))
        wf = Workflow(
            id=wf_id,
            name=name,
            description=description,
            steps=wf_steps,
            checkpoint_path=str(self.checkpoint_dir / f"{wf_id}.json"),
        )
        self._active_workflows[wf_id] = wf
        wf.save_checkpoint()
        logger.info(f"Created workflow: {name} ({wf_id})")
        return wf

    def _topological_sort(self, steps: list[WorkflowStep]) -> list[WorkflowStep]:
        """Sort steps by dependencies using topological sort."""
        step_map = {s.id: s for s in steps}
        visited = set()
        result = []

        def visit(step_id: str) -> None:
            if step_id in visited:
                return
            visited.add(step_id)
            step = step_map.get(step_id)
            if step:
                for dep_id in step.depends_on:
                    visit(dep_id)
                result.append(step)

        for step in steps:
            visit(step.id)
        return result

    async def execute_workflow(
        self,
        workflow_id: str,
        ai_executor: Callable[[str, str], Awaitable[str]],  # async (step_name, instruction) -> result
        on_progress: Callable[[str, int, int], None] | None = None,  # (msg, current, total)
    ) -> dict:
        """
        Execute a workflow.
        ai_executor is called for each step with (step_name, instruction).
        Returns {"status": "done"|"failed", "results": {step_id: result}, "errors": [...]}
        """
        wf = self._active_workflows.get(workflow_id)
        if not wf:
            return {"status": "failed", "results": {}, "errors": ["Workflow not found"]}

        wf.status = StepStatus.RUNNING
        wf.save_checkpoint()

        sorted_steps = self._topological_sort(wf.steps)
        results: dict[str, str] = {}
        errors: list[str] = []
        step_count = len(sorted_steps)
        completed_durations: list[float] = []  # track per-step durations for ETA

        for idx, step in enumerate(sorted_steps):
            # Check if dependencies are met
            dep_failed = False
            for dep_id in step.depends_on:
                dep_step = next((s for s in wf.steps if s.id == dep_id), None)
                if dep_step and dep_step.status == StepStatus.FAILED:
                    dep_failed = True
                    break

            if dep_failed:
                step.status = StepStatus.SKIPPED
                logger.warning(f"Skipped {step.name} due to failed dependency")
                if on_progress:
                    on_progress(f"Skipped: {step.name}", idx + 1, step_count)
                continue

            step.status = StepStatus.RUNNING
            step.started_at = time.time()
            wf.save_checkpoint()

            # Call step start callbacks
            for callback in self._on_step_start:
                try:
                    callback(step)
                except Exception as e:
                    logger.error(f"Step start callback error: {e}")

            if on_progress:
                on_progress(f"Running: {step.name}", idx + 1, step_count)

            # Execute with retry logic
            last_exc: Exception | None = None
            succeeded = False
            for attempt in range(step.max_retries + 1):
                if attempt > 0:
                    logger.info(f"Retrying step '{step.name}' (attempt {attempt + 1}/{step.max_retries + 1})")
                    await asyncio.sleep(2)
                try:
                    result = await ai_executor(step.name, step.instruction)
                    step.result = result
                    step.status = StepStatus.DONE
                    results[step.id] = result
                    succeeded = True
                    logger.info(f"Step '{step.name}' completed (attempt {attempt + 1})")
                    break
                except Exception as e:
                    last_exc = e
                    logger.warning(f"Step '{step.name}' attempt {attempt + 1} failed: {e}")

            if not succeeded and last_exc is not None:
                step.error = str(last_exc)
                step.status = StepStatus.FAILED
                errors.append(f"{step.name}: {last_exc}")
                logger.error(f"Step '{step.name}' failed after {step.max_retries + 1} attempt(s): {last_exc}")

            step.finished_at = time.time()
            step.duration_s = step.finished_at - step.started_at
            if succeeded:
                completed_durations.append(step.duration_s)

            # Compute and report ETA
            remaining = step_count - (idx + 1)
            if completed_durations and remaining > 0:
                avg_duration = sum(completed_durations) / len(completed_durations)
                eta_s = avg_duration * remaining
                eta_msg = f" (ETA ~{eta_s:.0f}s remaining)"
            else:
                eta_msg = ""

            if on_progress:
                status_label = "Done" if succeeded else "Failed"
                on_progress(f"{status_label}: {step.name}{eta_msg}", idx + 1, step_count)

            wf.save_checkpoint()

            # Call step done callbacks
            for callback in self._on_step_done:
                try:
                    callback(step)
                except Exception as e:
                    logger.error(f"Step done callback error: {e}")

        # Determine final status
        all_done = all(s.status in (StepStatus.DONE, StepStatus.SKIPPED) for s in wf.steps)
        wf.status = StepStatus.DONE if all_done else StepStatus.FAILED
        wf.save_checkpoint()

        # Call workflow done callbacks
        for callback in self._on_workflow_done:
            try:
                callback(wf)
            except Exception as e:
                logger.error(f"Workflow done callback error: {e}")

        return {
            "status": "done" if all_done else "failed",
            "results": results,
            "errors": errors,
        }

    def list_workflows(self) -> list[dict]:
        """List all saved workflows with status."""
        workflows = []
        for file_path in self.checkpoint_dir.glob("wf_*.json"):
            wf = Workflow.load_checkpoint(str(file_path))
            if wf:
                workflows.append({
                    "id": wf.id,
                    "name": wf.name,
                    "status": wf.status.value,
                    "step_count": len(wf.steps),
                    "created_at": wf.created_at,
                    "checkpoint_path": wf.checkpoint_path,
                })
        return sorted(workflows, key=lambda w: w["created_at"], reverse=True)

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        """Get a workflow by ID."""
        if workflow_id in self._active_workflows:
            return self._active_workflows[workflow_id]

        file_path = self.checkpoint_dir / f"{workflow_id}.json"
        return Workflow.load_checkpoint(str(file_path))

    async def resume_workflow(
        self,
        workflow_id: str,
        ai_executor: Callable[[str, str], Awaitable[str]],
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> dict:
        """Resume a failed/interrupted workflow from checkpoint."""
        wf = self.get_workflow(workflow_id)
        if not wf:
            return {"status": "failed", "results": {}, "errors": ["Workflow not found"]}

        self._active_workflows[workflow_id] = wf
        return await self.execute_workflow(workflow_id, ai_executor, on_progress)

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow and its checkpoint."""
        self._active_workflows.pop(workflow_id, None)
        file_path = self.checkpoint_dir / f"{workflow_id}.json"
        try:
            if file_path.exists():
                file_path.unlink()
            logger.info(f"Deleted workflow: {workflow_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete workflow: {e}")
            return False
