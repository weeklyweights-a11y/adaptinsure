"""Adapter code generation engine."""

from __future__ import annotations

import ast
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from src.exceptions import GenerationError
from src.generator.codes import GEN_RENDER_FAILED, GEN_SYNTAX_INVALID
from src.generator.context_builder import build_template_context
from src.generator.name_utils import sanitize_client_name
from src.mapping.config import MappingConfig, collect_unique_transforms

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class GenerationResult(BaseModel):
    """Outcome of adapter code generation."""

    model_config = ConfigDict(strict=True)

    adapter_file: Annotated[Path, Field(description="Path to generated adapter module")]
    test_file: Annotated[Path, Field(description="Path to generated test module")]
    client_name: Annotated[str, Field(description="Client display name")]
    class_name: Annotated[str, Field(description="Generated adapter class name")]
    field_count: Annotated[int, Field(ge=0)]
    transform_count: Annotated[int, Field(ge=0)]
    gap_count: Annotated[int, Field(ge=0)]
    warnings: Annotated[list[str], Field(default_factory=list)]
    generated_at: Annotated[datetime, Field(description="Generation timestamp UTC")]
    syntax_valid: Annotated[bool, Field(description="True when ast.parse succeeded")]


class GeneratorEngine:
    """Render Jinja2 templates into adapter and test Python files."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        """Initialize Jinja2 environment."""
        template_path = templates_dir or _TEMPLATES_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(template_path)),
            autoescape=select_autoescape(enabled_extensions=()),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(
        self,
        config: MappingConfig,
        output_dir: Path,
        *,
        timestamp: datetime | None = None,
    ) -> GenerationResult:
        """Generate adapter and test files from a mapping config."""
        warnings: list[str] = []
        for gap in config.gaps:
            if gap.severity == "critical":
                warnings.append(f"Critical gap: {gap.field_name} — {gap.description}")
        if config.confidence_summary.requires_review:
            warnings.append("Mapping config requires manual review")

        generated_at = timestamp or datetime.now(UTC)
        try:
            context = build_template_context(
                config,
                timestamp=generated_at,
                warnings=warnings,
            )
        except Exception as exc:
            raise GenerationError(
                GEN_RENDER_FAILED,
                "Failed to build template context",
                details={"error": str(exc)},
            ) from exc

        warnings.extend(context.pop("warnings", []))

        _, _, file_stem, _ = sanitize_client_name(config.client_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        adapter_path = output_dir / f"{file_stem}.py"
        test_path = output_dir / f"test_{file_stem}.py"

        try:
            adapter_source = self._env.get_template("adapter_class.py.j2").render(**context)
            test_source = self._env.get_template("test_adapter.py.j2").render(**context)
        except Exception as exc:
            raise GenerationError(
                GEN_RENDER_FAILED,
                "Failed to render templates",
                details={"error": str(exc)},
            ) from exc

        adapter_path.write_text(adapter_source, encoding="utf-8")
        test_path.write_text(test_source, encoding="utf-8")

        syntax_valid = True
        try:
            ast.parse(adapter_source)
            ast.parse(test_source)
        except SyntaxError as exc:
            syntax_valid = False
            warnings.append(f"Generated code syntax error: {exc}")
            raise GenerationError(
                GEN_SYNTAX_INVALID,
                "Generated adapter code failed syntax validation",
                details={"error": str(exc)},
            ) from exc

        deduped = collect_unique_transforms(config.field_mappings)
        return GenerationResult(
            adapter_file=adapter_path,
            test_file=test_path,
            client_name=config.client_name,
            class_name=context["class_name"],
            field_count=len(context["field_mappings"]),
            transform_count=len(deduped),
            gap_count=len(config.gaps),
            warnings=warnings,
            generated_at=generated_at,
            syntax_valid=syntax_valid,
        )
