#!/usr/bin/python3

"""
Exemplars - Framework for comparing responses from different AI models to specific questions.

Unlike benchmarks that test many questions with scoring, exemplars focus on qualitative 
comparison of responses from multiple models to the same prompt.
"""

import html
import json
import logging
import os
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Tuple

import constants
import benchmarks.datastore.common
from clients import unified_client
from clients.types import Response

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class ExemplarType(str, Enum):
    """Types of exemplar tasks."""

    TOKENIZATION = "tokenization"  # Tokenization tasks (e.g. counting letters)
    LINGUISTIC = "linguistic"  # Linguistic tasks (e.g., definitions, translations)
    CREATIVE = "creative"  # Creative writing, storytelling, etc.
    INSTRUCTION = "instruction"  # Following specific instructions
    KNOWLEDGE = "knowledge"  # Factual knowledge tasks
    CODING = "coding"  # Code generation tasks
    REASONING = "reasoning"  # Logical reasoning tasks
    ANALYSIS = "analysis"  # Data or content analysis


@dataclass
class ExemplarMetadata:
    """Metadata about an exemplar."""

    id: str  # Unique identifier (e.g., "metaphor_generation")
    name: str  # Display name (e.g., "Metaphor Generation")
    prompt: str  # The prompt to send to models
    description: Optional[str] = None  # Description of the exemplar
    type: ExemplarType = ExemplarType.CREATIVE  # Type of exemplar
    expected_output: Optional[str] = None  # Example of good output (optional)
    tags: List[str] = field(default_factory=list)  # Tags for categorization
    context: Optional[str] = None  # Optional system context for the prompt
    max_tokens: int = 1024  # Maximum tokens for response
    temperature: float = 0.7  # Temperature for generation
    structured_output: Optional[Dict] = None  # JSON schema for structured output

    def to_dict(self) -> Dict:
        """Convert to dictionary, handling enums and None values."""
        result = {}
        for k, v in asdict(self).items():
            if k == "type" and isinstance(v, ExemplarType):
                result[k] = v.value
            elif v is not None:
                result[k] = v
        return result


@dataclass
class ExemplarResult:
    """Result of running an exemplar with a specific model."""

    exemplar_id: str  # ID of the exemplar
    model_name: str  # Name of the model
    response_text: str  # Text response from the model
    structured_data: Dict  # Any structured data returned
    metadata: Dict = field(default_factory=dict)  # Additional metadata (timing, etc.)

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return asdict(self)


class ExemplarRegistry:
    """Registry for exemplars."""

    def __init__(self):
        """Initialize the registry."""
        self.exemplars: Dict[str, ExemplarMetadata] = {}

    def register_exemplar(self, exemplar: ExemplarMetadata) -> None:
        """Register an exemplar."""
        if exemplar.id in self.exemplars:
            logger.warning(f"Overwriting existing exemplar: {exemplar.id}")
        self.exemplars[exemplar.id] = exemplar
        logger.info(f"Registered exemplar: {exemplar.id}")

    def get_exemplar(self, exemplar_id: str) -> Optional[ExemplarMetadata]:
        """Get an exemplar by ID."""
        return self.exemplars.get(exemplar_id)

    def list_exemplars(self) -> List[ExemplarMetadata]:
        """List all registered exemplars."""
        return list(self.exemplars.values())


class ExemplarRunner:
    """Runner for executing exemplars against models."""

    def __init__(self, registry: ExemplarRegistry):
        """
        Initialize runner with exemplar registry.

        Args:
            registry: ExemplarRegistry instance
        """
        self.registry = registry
        self.session = datastore.common.create_dev_session()
        self._available_models = None  # Cache of available models

    def get_available_models(self) -> List[Dict]:
        """
        Get list of available models from the database.

        Returns:
            List of model dictionaries with 'codename' and 'displayname'
        """
        if self._available_models is None:
            self._available_models = datastore.common.list_all_models(self.session)
        return self._available_models

    def get_model_names(self) -> List[str]:
        """
        Get list of available model codenames from the database.

        Returns:
            List of model codenames
        """
        return [model["codename"] for model in self.get_available_models()]

    def run_exemplar(self, exemplar_id: str, model_name: str) -> ExemplarResult:
        """
        Run a single exemplar with a specific model.

        Args:
            exemplar_id: ID of the exemplar to run
            model_name: Name of the model to use

        Returns:
            ExemplarResult with the model's response

        Raises:
            ValueError: If exemplar_id is not registered
        """
        # Get exemplar metadata
        exemplar = self.registry.get_exemplar(exemplar_id)
        if not exemplar:
            raise ValueError(f"Exemplar not found: {exemplar_id}")

        logger.info(f"Running exemplar {exemplar_id} with model {model_name}")

        # Generate response
        try:
            response = unified_client.generate_chat(
                prompt=exemplar.prompt,
                model=model_name,
                json_schema=exemplar.structured_output,
                context=exemplar.context,
            )

            # Create result object
            result = ExemplarResult(
                exemplar_id=exemplar_id,
                model_name=model_name,
                response_text=response.response_text,
                structured_data=response.structured_data or {},
                metadata={
                    "timing_ms": response.usage.total_msec if response.usage else 0,
                    "tokens": response.usage.total_tokens if response.usage else 0,
                    "temperature": exemplar.temperature,
                },
            )

            logger.info(f"Exemplar {exemplar_id} completed successfully with model {model_name}")
            return result

        except Exception as e:
            logger.error(f"Error running exemplar {exemplar_id} with model {model_name}: {e}")

            # Return a result with error information
            return ExemplarResult(
                exemplar_id=exemplar_id,
                model_name=model_name,
                response_text=f"ERROR: {str(e)}",
                structured_data={},
                metadata={"error": str(e)},
            )

    def run_exemplar_with_models(
        self, exemplar_id: str, model_names: List[str]
    ) -> List[ExemplarResult]:
        """
        Run a single exemplar with multiple models.

        Args:
            exemplar_id: ID of the exemplar to run
            model_names: List of model names to use

        Returns:
            List of ExemplarResult objects, one per model
        """
        results = []
        for model_name in model_names:
            result = self.run_exemplar(exemplar_id, model_name)
            results.append(result)
        return results

    def run_all_exemplars(self, model_name: str, store_results=False) -> Dict[str, ExemplarResult]:
        """
        Run all registered exemplars with a specific model.

        Args:
            model_name: Name of the model to use

        Returns:
            Dictionary mapping exemplar IDs to their results
        """
        results = {}
        for exemplar_id in self.registry.exemplars:
            if report_generator.storage.load_result(exemplar_id, model_name):
                logger.info(f"Result already exists for {exemplar_id} with model {model_name}")
                continue
            result = self.run_exemplar(exemplar_id, model_name)
            if store_results:
                # Save result to storage
                storage.save_result(result)
            results[exemplar_id] = result
        return results


class ExemplarStorage:
    """Storage for exemplar results."""

    def __init__(self):
        """
        Initialize storage with base directory.

        Args:
            base_dir: Base directory for storing results
        """
        self.base_dir = os.path.join(constants.OUTPUT_DIR, "exemplar_results")
        os.makedirs(self.base_dir, exist_ok=True)

    def save_result(self, result: ExemplarResult) -> str:
        """
        Save an exemplar result to disk.

        Args:
            result: ExemplarResult to save

        Returns:
            Path to the saved file
        """
        # Create directory for this exemplar if it doesn't exist
        exemplar_dir = os.path.join(self.base_dir, result.exemplar_id)
        os.makedirs(exemplar_dir, exist_ok=True)

        # Generate filename based on model name
        filename = f"{result.model_name}.json".replace("/", "_").replace(
            ":", "_"
        )  # Replace colon and slashes to avoid path issues
        file_path = os.path.join(exemplar_dir, filename)

        # Save result as JSON
        with open(file_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.info(f"Saved result to {file_path}")
        return file_path

    def load_result(self, exemplar_id: str, model_name: str) -> Optional[ExemplarResult]:
        """
        Load an exemplar result from disk.

        Args:
            exemplar_id: ID of the exemplar
            model_name: Name of the model

        Returns:
            ExemplarResult if found, None otherwise
        """
        model_filename = model_name.replace("/", "_").replace(
            ":", "_"
        )  # Replace slashes and colons to avoid path issues
        file_path = os.path.join(self.base_dir, exemplar_id, f"{model_filename}.json")
        if not os.path.exists(file_path):
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return ExemplarResult(
            exemplar_id=data.get("exemplar_id"),
            model_name=data.get("model_name"),
            response_text=data.get("response_text", ""),
            structured_data=data.get("structured_data", {}),
            metadata=data.get("metadata", {}),
        )

    def list_results(self, exemplar_id: Optional[str] = None) -> Dict:
        """
        List all saved results, optionally filtered by exemplar ID.

        Args:
            exemplar_id: Optional exemplar ID to filter by

        Returns:
            Dictionary of results organized by exemplar ID and model name
        """
        results = {}

        if exemplar_id:
            # List results for a specific exemplar
            exemplar_dir = os.path.join(self.base_dir, exemplar_id)
            if os.path.exists(exemplar_dir):
                results[exemplar_id] = {}
                for filename in os.listdir(exemplar_dir):
                    if filename.endswith(".json"):
                        model_name = filename[:-5]  # Remove .json extension
                        result = self.load_result(exemplar_id, model_name)
                        if result:
                            results[exemplar_id][model_name] = result
        else:
            # List results for all exemplars
            for exemplar_dir in os.listdir(self.base_dir):
                if os.path.isdir(os.path.join(self.base_dir, exemplar_dir)):
                    results[exemplar_dir] = {}
                    for filename in os.listdir(os.path.join(self.base_dir, exemplar_dir)):
                        if filename.endswith(".json"):
                            model_name = filename[:-5]  # Remove .json extension
                            result = self.load_result(exemplar_dir, model_name)
                            if result:
                                results[exemplar_dir][model_name] = result

        return results


class ExemplarReportGenerator:
    """Generator for HTML reports from exemplar results."""

    def __init__(self, registry: ExemplarRegistry, storage: ExemplarStorage):
        """
        Initialize report generator.

        Args:
            registry: ExemplarRegistry instance
            storage: ExemplarStorage instance
            output_dir: Directory for output reports
        """
        self.registry = registry
        self.storage = storage
        self.output_dir = os.path.join(constants.OUTPUT_DIR, "exemplar_reports")
        os.makedirs(self.output_dir, exist_ok=True)
        self.session = datastore.common.create_dev_session()

    def get_model_sizes(self) -> Dict[str, int]:
        """
        Get model sizes from the database.

        Returns:
            Dictionary mapping model names (in filename-safe format) to sizes
        """
        models = datastore.common.list_all_models(self.session)
        model_sizes = {}

        for model in models:
            # Store the key in the same format used for filenames
            filename_safe_key = model["codename"].replace("/", "_").replace(":", "_")
            model_sizes[filename_safe_key] = model.get("filesize_mb", 0) or 0

            # Also store with the original key for direct lookups
            model_sizes[model["codename"]] = model.get("filesize_mb", 0) or 0

        return model_sizes

    def _sort_results_by_size(
        self, results: Dict[str, ExemplarResult]
    ) -> List[Tuple[str, ExemplarResult]]:
        """
        Sort results by model size.

        Args:
            results: Dictionary mapping model names to ExemplarResult objects

        Returns:
            List of (model_name, result) tuples sorted by model size (ascending)
        """
        model_sizes = self.get_model_sizes()

        def get_model_size(model_name):
            # The model_name here is already in filename-safe format,
            # so we should be able to look it up directly in model_sizes
            if model_name in model_sizes:
                return model_sizes[model_name]

            # Default to 0 for unknown models
            return 0

        # Create list of (model_name, result) tuples sorted by model size
        sorted_results = sorted(results.items(), key=lambda x: get_model_size(x[0]))

        return sorted_results

    def generate_exemplar_report(self, exemplar_id: str) -> str:
        """
        Generate a report for a specific exemplar with all model results.

        Args:
            exemplar_id: ID of the exemplar

        Returns:
            Path to the generated report
        """
        # Get exemplar metadata
        exemplar = self.registry.get_exemplar(exemplar_id)
        if not exemplar:
            raise ValueError(f"Exemplar not found: {exemplar_id}")

        # Load all results for this exemplar
        results = self.storage.list_results(exemplar_id).get(exemplar_id, {})
        if not results:
            logger.warning(f"No results found for exemplar: {exemplar_id}")
            return ""

        # Generate simple HTML report
        report_path = os.path.join(self.output_dir, f"{exemplar_id}.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(
                f"""<!DOCTYPE html>
<html>
<head>
    <title>Exemplar Report: {exemplar.name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .model-response {{ margin-bottom: 30px; border: 1px solid #ddd; padding: 15px; }}
        .prompt {{ background-color: #f5f5f5; padding: 10px; margin-bottom: 20px; }}
        pre {{ white-space: pre-wrap; }}
    </style>
    <meta charset="UTF-8">
</head>
<body>
    <h1>Exemplar: {exemplar.name}</h1>
    <p>{exemplar.description or ""}</p>
    
    <div class="prompt">
        <h3>Prompt:</h3>
        <pre>{exemplar.prompt}</pre>
    </div>
    
    {self._generate_model_sections(results)}
</body>
</html>
"""
            )

        logger.info(f"Generated report at {report_path}")
        return report_path

    def _generate_model_sections(self, results: Dict[str, ExemplarResult]) -> str:
        """Generate HTML sections for each model result, sorted by model size."""
        sections = []

        # Get model sizes and sort results
        sorted_results = self._sort_results_by_size(results)
        model_sizes = self.get_model_sizes()

        for model_name, result in sorted_results:
            if result.structured_data:
                response = html.escape(
                    json.dumps(result.structured_data, indent=2, ensure_ascii=False)
                )
            else:
                response = html.escape(result.response_text)

            # Get model size (handle model names that might have been normalized in filenames)
            model_size = model_sizes.get(model_name, "Unknown")

            # Create section for this model
            sections.append(
                f"""
    <div class="model-response">
        <h2>Model: {model_name} ({model_size} MB)</h2>
        <div class="metadata">
            <p>Tokens: {result.metadata.get("tokens", "N/A")}</p>
            <p>Time: {result.metadata.get("timing_ms", "N/A")}ms</p>
        </div>
        <h3>Response:</h3>
        <pre>{response}</pre>
    </div>
"""
            )

        return "\n".join(sections)

    def generate_all_reports(self) -> List[str]:
        """
        Generate reports for all exemplars.

        Returns:
            List of paths to generated reports
        """
        report_paths = []
        for exemplar in self.registry.list_exemplars():
            try:
                path = self.generate_exemplar_report(exemplar.id)
                if path:
                    report_paths.append(path)
            except Exception as e:
                logger.error(f"Error generating report for exemplar {exemplar.id}: {e}")
        return report_paths

    def generate_index_report(self) -> str:
        """
        Generate an index report listing all exemplars.

        Returns:
            Path to the generated index report
        """
        exemplars = self.registry.list_exemplars()
        if not exemplars:
            logger.warning("No exemplars registered")
            return ""

        # Generate HTML table of exemplars
        rows = []
        for exemplar in exemplars:
            rows.append(
                f"""
    <tr>
        <td>{exemplar.name}</td>
        <td>{exemplar.id}</td>
        <td>{exemplar.type.value if hasattr(exemplar.type, "value") else exemplar.type}</td>
        <td>{exemplar.description or ""}</td>
        <td><a href="{exemplar.id}.html">View Report</a></td>
    </tr>
"""
            )

        # Write index report
        index_path = os.path.join(self.output_dir, "index.html")
        with open(index_path, "w") as f:
            f.write(
                f"""<!DOCTYPE html>
<html>
<head>
    <title>Exemplar Reports</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>Exemplar Reports</h1>
    
    <table>
        <tr>
            <th>Name</th>
            <th>ID</th>
            <th>Type</th>
            <th>Description</th>
            <th>Report</th>
        </tr>
        {"".join(rows)}
    </table>
</body>
</html>
"""
            )

        logger.info(f"Generated index report at {index_path}")
        return index_path


# Create global instances for easy use
registry = ExemplarRegistry()
storage = ExemplarStorage()
runner = ExemplarRunner(registry)
report_generator = ExemplarReportGenerator(registry, storage)


def register_exemplar(
    id: str,
    name: str,
    prompt: str,
    description: Optional[str] = None,
    type: Union[ExemplarType, str] = ExemplarType.CREATIVE,
    expected_output: Optional[str] = None,
    tags: Optional[List[str]] = None,
    context: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    structured_output: Optional[Dict] = None,
) -> None:
    """
    Register an exemplar with the global registry.

    Args:
        id: Unique identifier
        name: Display name
        prompt: Prompt text to send to models
        description: Optional description
        type: Type of exemplar (default: OPEN_ENDED)
        expected_output: Optional example of expected output
        tags: Optional list of tags
        context: Optional system context
        max_tokens: Maximum tokens for response
        temperature: Temperature for generation
        structured_output: Optional JSON schema for structured output
    """
    # Convert string type to enum if needed
    if isinstance(type, str):
        type = ExemplarType(type)

    exemplar = ExemplarMetadata(
        id=id,
        name=name,
        prompt=prompt,
        description=description,
        type=type,
        expected_output=expected_output,
        tags=tags or [],
        context=context,
        max_tokens=max_tokens,
        temperature=temperature,
        structured_output=structured_output,
    )

    registry.register_exemplar(exemplar)


def run_exemplar(exemplar_id: str, model_name: str) -> ExemplarResult:
    """Run an exemplar with a model and save the result."""
    result = runner.run_exemplar(exemplar_id, model_name)
    storage.save_result(result)
    return result


def run_exemplar_for_all_models(exemplar_id: str) -> Dict[str, ExemplarResult]:
    """Run an exemplar with all available models and save the results."""
    model_names = runner.get_model_names()
    results = {}
    for model in model_names:
        if report_generator.storage.load_result(exemplar_id, model):
            logger.info(f"Result already exists for {exemplar_id} with model {model}")
            continue
        results[model] = runner.run_exemplar(exemplar_id, model)
        storage.save_result(results[model])
    return results


def run_all_exemplars_for_all_models(min_size=2400, max_size=36000) -> Dict[str, ExemplarResult]:
    """Run all registered exemplars with all available models and save the results."""
    model_names = runner.get_model_names()
    sizes = report_generator.get_model_sizes()
    results = {}
    for model in model_names:
        model_filename = model.replace("/", "_").replace(
            ":", "_"
        )  # Replace slashes and colons to avoid path issues
        if model_filename in sizes and (
            sizes[model_filename] < min_size or sizes[model_filename] > max_size
        ):
            logger.info(
                f"Skipping model {model} due to size constraints: {sizes[model_filename]} MB"
            )
            continue
        runner.run_all_exemplars(model, store_results=True)
    report_generator.generate_all_reports()
    report_generator.generate_index_report()


def compare_models(exemplar_id: str, model_names: List[str]) -> List[ExemplarResult]:
    """Run an exemplar with multiple models and save the results."""
    results = runner.run_exemplar_with_models(exemplar_id, model_names)
    for result in results:
        storage.save_result(result)
    report_generator.generate_exemplar_report(exemplar_id)
    return results


def generate_report(exemplar_id: str) -> str:
    """Generate a report for an exemplar."""
    return report_generator.generate_exemplar_report(exemplar_id)


def generate_all_reports() -> None:
    """Generate reports for all exemplars and create an index."""
    report_generator.generate_all_reports()
    report_generator.generate_index_report()
