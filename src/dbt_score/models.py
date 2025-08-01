"""Objects related to loading the dbt manifest."""

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, TypeAlias, Union

from dbt_score.dbt_utils import dbt_ls

logger = logging.getLogger(__name__)


@dataclass
class Constraint:
    """Constraint for a model or a column.

    Attributes:
        type: The type of the constraint, e.g. `foreign_key`.
        name: The name of the constraint.
        expression: The expression of the constraint, e.g. `schema.other_table`.
        columns: The columns for the constraint (only for model-level constraints).
        _raw_values: The raw values of the constraint in the manifest.
    """

    type: str
    name: str | None = None
    expression: str | None = None
    columns: list[str] | None = None
    _raw_values: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw_values(cls, raw_values: dict[str, Any]) -> "Constraint":
        """Create a constraint object from a constraint node in the manifest."""
        return cls(
            type=raw_values["type"],
            name=raw_values["name"],
            expression=raw_values["expression"],
            columns=raw_values.get("columns"),
            _raw_values=raw_values,
        )


@dataclass
class Test:
    """Test for a column, model, source or snapshot.

    Attributes:
        name: The name of the test.
        type: The type of the test, e.g. `unique`.
        kwargs: The kwargs of the test.
        tags: The list of tags attached to the test.
        _raw_values: The raw values of the test in the manifest.
    """

    name: str
    type: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    _raw_values: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_node(cls, test_node: dict[str, Any]) -> "Test":
        """Create a test object from a test node in the manifest."""
        return cls(
            name=test_node["name"],
            type=test_node.get("test_metadata", {}).get("name", "generic"),
            kwargs=test_node.get("test_metadata", {}).get("kwargs", {}),
            tags=test_node.get("tags", []),
            _raw_values=test_node,
        )


@dataclass
class Column:
    """Represents a column.

    Attributes:
        name: The name of the column.
        description: The description of the column.
        data_type: The data type of the column.
        meta: The metadata attached to the column.
        constraints: The list of constraints attached to the column.
        tags: The list of tags attached to the column.
        tests: The list of tests attached to the column.
        _raw_values: The raw values of the column as defined in the node.
        _raw_test_values: The raw test values of the column as defined in the node.
    """

    name: str
    description: str
    data_type: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    constraints: list[Constraint] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    tests: list[Test] = field(default_factory=list)
    _raw_values: dict[str, Any] = field(default_factory=dict)
    _raw_test_values: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_node_values(
        cls, values: dict[str, Any], test_values: list[dict[str, Any]]
    ) -> "Column":
        """Create a column object from raw values."""
        return cls(
            name=values["name"],
            description=values["description"],
            data_type=values["data_type"],
            meta=values["meta"],
            constraints=[
                Constraint.from_raw_values(constraint)
                for constraint in values["constraints"]
            ],
            tags=values["tags"],
            tests=[Test.from_node(test) for test in test_values],
            _raw_values=values,
            _raw_test_values=test_values,
        )


class HasColumnsMixin:
    """Common methods for resource types that have columns."""

    columns: list[Column]

    def get_column(self, column_name: str) -> Column | None:
        """Get a column by name."""
        for column in self.columns:
            if column.name == column_name:
                return column

        return None

    @staticmethod
    def _get_columns(
        node_values: dict[str, Any], test_values: list[dict[str, Any]]
    ) -> list[Column]:
        """Get columns from a node and its tests in the manifest."""
        return [
            Column.from_node_values(
                values,
                [
                    test
                    for test in test_values
                    if test.get("test_metadata", {})
                    .get("kwargs", {})
                    .get("column_name", "")
                    .strip("`")  # BigQuery connector when "quote: true"
                    == name
                ],
            )
            for name, values in node_values.get("columns", {}).items()
        ]


# Type annotation for parent references
ParentType = Union["Model", "Source", "Snapshot", "Seed"]
ChildType = Union["Model", "Snapshot", "Exposure"]


@dataclass
class Model(HasColumnsMixin):
    """Represents a dbt model.

    Attributes:
        unique_id: The id of the model, e.g. `model.package.model_name`.
        name: The name of the model.
        relation_name: The relation name of the model, e.g. `db.schema.model_name`.
        description: The full description of the model.
        original_file_path: The sql path of the model, `e.g. model_dir/dir/file.sql`.
        config: The config of the model.
        meta: The meta of the model.
        columns: The list of columns of the model.
        package_name: The package name of the model.
        database: The database name of the model.
        schema: The schema name of the model.
        raw_code: The raw code of the model.
        language: The language of the model, e.g. sql.
        access: The access level of the model, e.g. public.
        group: The group the model is in.
        alias: The alias of the model.
        patch_path: The yml path of the model, e.g. `package://model_dir/dir/file.yml`.
        tags: The list of tags attached to the model.
        tests: The list of tests attached to the model.
        depends_on: Dictionary of models/sources/macros that the model depends on.
        parents: The list of models, sources, and snapshots this model depends on.
        children: The list of models and snapshots that depend on this model.
        _raw_values: The raw values of the model (node) in the manifest.
        _raw_test_values: The raw test values of the model (node) in the manifest.
    """

    unique_id: str
    name: str
    relation_name: str
    description: str
    original_file_path: str
    config: dict[str, Any]
    meta: dict[str, Any]
    columns: list[Column]
    package_name: str
    database: str
    schema: str
    raw_code: str
    language: str
    access: str
    group: str
    alias: str | None = None
    patch_path: str | None = None
    tags: list[str] = field(default_factory=list)
    tests: list[Test] = field(default_factory=list)
    depends_on: dict[str, list[str]] = field(default_factory=dict)
    constraints: list[Constraint] = field(default_factory=list)
    parents: list[ParentType] = field(default_factory=list)
    children: list[ChildType] = field(default_factory=list)
    _raw_values: dict[str, Any] = field(default_factory=dict)
    _raw_test_values: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_node(
        cls, node_values: dict[str, Any], test_values: list[dict[str, Any]]
    ) -> "Model":
        """Create a model object from a node and it's tests in the manifest."""
        return cls(
            unique_id=node_values["unique_id"],
            name=node_values["name"],
            relation_name=node_values["relation_name"],
            description=node_values["description"],
            original_file_path=node_values["original_file_path"],
            config=node_values["config"],
            meta=node_values["meta"],
            columns=cls._get_columns(node_values, test_values),
            package_name=node_values["package_name"],
            database=node_values["database"],
            schema=node_values["schema"],
            raw_code=node_values["raw_code"],
            language=node_values["language"],
            access=node_values["access"],
            group=node_values["group"],
            alias=node_values["alias"],
            patch_path=node_values["patch_path"],
            tags=node_values["tags"],
            tests=[
                Test.from_node(test)
                for test in test_values
                if not test.get("test_metadata", {})
                .get("kwargs", {})
                .get("column_name")
            ],
            depends_on=node_values["depends_on"],
            constraints=[
                Constraint.from_raw_values(constraint)
                for constraint in node_values["constraints"]
            ],
            parents=[],  # Will be populated later
            _raw_values=node_values,
            _raw_test_values=test_values,
        )

    def __hash__(self) -> int:
        """Compute a unique hash for a model."""
        return hash(self.unique_id)


@dataclass
class Duration:
    """Represents a duration used in SourceFreshness.

    This is referred to as `Time` in the dbt JSONSchema.

    Attributes:
        count: a positive integer
        period: "minute" | "hour" | "day"
    """

    count: int | None = None
    period: Literal["minute", "hour", "day"] | None = None


@dataclass
class SourceFreshness:
    """Represents a source freshness configuration.

    This is referred to as `FreshnessThreshold` in the dbt JSONSchema.

    Attributes:
        warn_after: The threshold after which the dbt source freshness check should
            soft-fail with a warning.
        error_after: The threshold after which the dbt source freshness check should
            fail.
        filter: An optional filter to apply to the input data before running
            source freshness check.
    """

    warn_after: Duration
    error_after: Duration
    filter: str | None = None


@dataclass
class Source(HasColumnsMixin):
    """Represents a dbt source table.

    Attributes:
        unique_id: The id of the source table,
            e.g. 'source.package.source_name.source_table_name'.
        name: The alias of the source table.
        description: The full description of the source table.
        source_name: The source namespace.
        source_description: The description for the source namespace.
        original_file_path: The yml path to the source definition.
        config: The config of the source definition.
        meta: Any meta-attributes on the source table.
        source_meta: Any meta-attribuets on the source namespace.
        columns: The list of columns for the source table.
        package_name: The dbt package name for the source table.
        database: The database name of the source table.
        schema: The schema name of the source table.
        identifier: The actual source table name, i.e. not an alias.
        loader: The tool used to load the source table into the warehouse.
        freshness: A set of time thresholds after which data may be considered stale.
        patch_path: The yml path of the source definition.
        tags: The list of tags attached to the source table.
        tests: The list of tests attached to the source table.
        children: The list of models and snapshots that depend on this source.
        _raw_values: The raw values of the source definition in the manifest.
        _raw_test_values: The raw test values of the source definition in the manifest.
    """

    unique_id: str
    name: str
    description: str
    source_name: str
    source_description: str
    original_file_path: str
    config: dict[str, Any]
    meta: dict[str, Any]
    source_meta: dict[str, Any]
    columns: list[Column]
    package_name: str
    database: str
    schema: str
    identifier: str
    loader: str
    freshness: SourceFreshness
    patch_path: str | None = None
    tags: list[str] = field(default_factory=list)
    tests: list[Test] = field(default_factory=list)
    children: list[ChildType] = field(default_factory=list)
    _raw_values: dict[str, Any] = field(default_factory=dict)
    _raw_test_values: list[dict[str, Any]] = field(default_factory=list)

    @property
    def selector_name(self) -> str:
        """Returns the name used by the dbt `source` method selector.

        Note: This is also the format output by `dbt ls --output name` for sources.

        https://docs.getdbt.com/reference/node-selection/methods#the-source-method
        """
        return f"{self.source_name}.{self.name}"

    @classmethod
    def from_node(
        cls, node_values: dict[str, Any], test_values: list[dict[str, Any]]
    ) -> "Source":
        """Create a source object from a node and it's tests in the manifest."""
        return cls(
            unique_id=node_values["unique_id"],
            name=node_values["name"],
            description=node_values["description"],
            source_name=node_values["source_name"],
            source_description=node_values["source_description"],
            original_file_path=node_values["original_file_path"],
            config=node_values["config"],
            meta=node_values["meta"],
            source_meta=node_values["source_meta"],
            columns=cls._get_columns(node_values, test_values),
            package_name=node_values["package_name"],
            database=node_values["database"],
            schema=node_values["schema"],
            identifier=node_values["identifier"],
            loader=node_values["loader"],
            freshness=node_values["freshness"],
            patch_path=node_values["patch_path"],
            tags=node_values["tags"],
            tests=[
                Test.from_node(test)
                for test in test_values
                if not test.get("test_metadata", {})
                .get("kwargs", {})
                .get("column_name")
            ],
            _raw_values=node_values,
            _raw_test_values=test_values,
        )

    def __hash__(self) -> int:
        """Compute a unique hash for a source."""
        return hash(self.unique_id)


@dataclass
class Snapshot(HasColumnsMixin):
    """Represents a dbt snapshot.

    Attributes:
        unique_id: The id of the snapshot, e.g. `snapshot.package.snapshot_name`.
        name: The name of the snapshot.
        relation_name: The relation name of the snapshot,
        e.g. `db.schema.snapshot_name`.
        description: The full description of the snapshot.
        original_file_path: The sql path of the snapshot,
        `e.g. snapshot_dir/dir/file.sql`.
        config: The config of the snapshot.
        meta: The meta of the snapshot.
        columns: The list of columns of the snapshot.
        package_name: The package name of the snapshot.
        database: The database name of the snapshot.
        schema: The schema name of the snapshot.
        raw_code: The raw code of the snapshot.
        language: The language of the snapshot, e.g. sql.
        alias: The alias of the snapshot.
        patch_path: The yml path of the snapshot, e.g.
        `package://snapshot_dir/dir/file.yml`.
        tags: The list of tags attached to the snapshot.
        tests: The list of tests attached to the snapshot.
        depends_on: Dictionary of models/sources/macros that the model depends on.
        strategy: The strategy of the snapshot.
        unique_key: The unique key of the snapshot.
        parents: The list of models, sources, and snapshots this snapshot depends on.
        children: The list of models and snapshots that depend on this snapshot.
        _raw_values: The raw values of the snapshot (node) in the manifest.
        _raw_test_values: The raw test values of the snapshot (node) in the manifest.
    """

    unique_id: str
    name: str
    relation_name: str
    description: str
    original_file_path: str
    config: dict[str, Any]
    meta: dict[str, Any]
    columns: list[Column]
    package_name: str
    database: str
    schema: str
    raw_code: str
    language: str
    alias: str | None = None
    patch_path: str | None = None
    tags: list[str] = field(default_factory=list)
    tests: list[Test] = field(default_factory=list)
    depends_on: dict[str, list[str]] = field(default_factory=dict)
    strategy: str | None = None
    unique_key: list[str] | None = None
    parents: list[ParentType] = field(default_factory=list)
    children: list[ChildType] = field(default_factory=list)
    _raw_values: dict[str, Any] = field(default_factory=dict)
    _raw_test_values: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_node(
        cls, node_values: dict[str, Any], test_values: list[dict[str, Any]]
    ) -> "Snapshot":
        """Create a snapshot object from a node and its tests in the manifest."""
        return cls(
            unique_id=node_values["unique_id"],
            name=node_values["name"],
            relation_name=node_values["relation_name"],
            description=node_values["description"],
            original_file_path=node_values["original_file_path"],
            config=node_values["config"],
            meta=node_values["meta"],
            columns=cls._get_columns(node_values, test_values),
            package_name=node_values["package_name"],
            database=node_values["database"],
            schema=node_values["schema"],
            raw_code=node_values["raw_code"],
            language=node_values["language"],
            alias=node_values["alias"],
            patch_path=node_values["patch_path"],
            tags=node_values["tags"],
            tests=[
                Test.from_node(test)
                for test in test_values
                if not test.get("test_metadata", {})
                .get("kwargs", {})
                .get("column_name")
            ],
            depends_on=node_values["depends_on"],
            parents=[],  # Will be populated later
            _raw_values=node_values,
            _raw_test_values=test_values,
        )

    def __hash__(self) -> int:
        """Compute a unique hash for a snapshot."""
        return hash(self.unique_id)


@dataclass
class Exposure:
    """Represents a dbt exposure.

    Attributes:
        unique_id: The unique id of the exposure (e.g. `exposure.package.exposure1`).
        name: The name of the exposure.
        description: The description of the exposure.
        label: The label of the exposure.
        url: The url of the exposure.
        maturity: The maturity of the exposure.
        original_file_path: The path to the exposure file
            (e.g. `models/exposures/exposures.yml`).
        type: The type of the exposure, e.g. `application`.
        owner: The owner of the exposure,
            e.g. `{"name": "owner", "email": "owner@email.com"}`.
        config: The config of the exposure.
        meta: The meta of the exposure.
        tags: The list of tags attached to the exposure.
        depends_on: The depends_on of the exposure.
        parents: The list of models, sources, and snapshot this exposure depends on.
        _raw_values: The raw values of the exposure in the manifest.
    """

    unique_id: str
    name: str
    description: str
    label: str
    url: str
    maturity: str
    original_file_path: str
    type: str
    owner: dict[str, Any]
    config: dict[str, Any]
    meta: dict[str, Any]
    tags: list[str]
    depends_on: dict[str, list[str]] = field(default_factory=dict)
    parents: list[ParentType] = field(default_factory=list)
    _raw_values: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_node(cls, node_values: dict[str, Any]) -> "Exposure":
        """Create an exposure object from a node in the manifest."""
        return cls(
            unique_id=node_values["unique_id"],
            name=node_values["name"],
            description=node_values["description"],
            label=node_values["label"],
            url=node_values["url"],
            maturity=node_values["maturity"],
            original_file_path=node_values["original_file_path"],
            type=node_values["type"],
            owner=node_values["owner"],
            config=node_values["config"],
            meta=node_values["meta"],
            tags=node_values["tags"],
            depends_on=node_values["depends_on"],
            _raw_values=node_values,
        )

    def __hash__(self) -> int:
        """Compute a unique hash for an exposure."""
        return hash(self.unique_id)


@dataclass
class Seed(HasColumnsMixin):
    """Represents a dbt seed.

    Attributes:
        unique_id: The id of the seed, e.g. `seed.package.seed_name`.
        name: The name of the seed.
        relation_name: The relation name of the seed, e.g. `db.schema.seed_name`.
        description: The full description of the seed.
        original_file_path: The seed path, e.g. `data/seed_name.csv`.
        config: The config of the seed.
        meta: The meta of the seed.
        columns: The list of columns of the seed.
        package_name: The package name of the seed.
        database: The database name of the seed.
        schema: The schema name of the seed.
        alias: The alias of the seed.
        patch_path: The yml path of the seed, e.g. `seeds.yml`.
        tags: The list of tags attached to the seed.
        tests: The list of tests attached to the seed.
        children: The list of models and snapshots that depend on this seed.
        _raw_values: The raw values of the seed (node) in the manifest.
        _raw_test_values: The raw test values of the seed (node) in the manifest.
    """

    unique_id: str
    name: str
    relation_name: str
    description: str
    original_file_path: str
    config: dict[str, Any]
    meta: dict[str, Any]
    columns: list[Column]
    package_name: str
    database: str
    schema: str
    alias: str | None = None
    patch_path: str | None = None
    tags: list[str] = field(default_factory=list)
    tests: list[Test] = field(default_factory=list)
    children: list[ChildType] = field(default_factory=list)
    _raw_values: dict[str, Any] = field(default_factory=dict)
    _raw_test_values: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_node(
        cls, node_values: dict[str, Any], test_values: list[dict[str, Any]]
    ) -> "Seed":
        """Create a seed object from a node and its tests in the manifest."""
        return cls(
            unique_id=node_values["unique_id"],
            name=node_values["name"],
            relation_name=node_values["relation_name"],
            description=node_values["description"],
            original_file_path=node_values["original_file_path"],
            config=node_values["config"],
            meta=node_values["meta"],
            columns=cls._get_columns(node_values, test_values),
            package_name=node_values["package_name"],
            database=node_values["database"],
            schema=node_values["schema"],
            alias=node_values["alias"],
            patch_path=node_values["patch_path"],
            tags=node_values["tags"],
            tests=[
                Test.from_node(test)
                for test in test_values
                if not test.get("test_metadata", {})
                .get("kwargs", {})
                .get("column_name")
            ],
            _raw_values=node_values,
            _raw_test_values=test_values,
        )

    def __hash__(self) -> int:
        """Compute a unique hash for a seed."""
        return hash(self.unique_id)


Evaluable: TypeAlias = Model | Source | Snapshot | Seed | Exposure


class ManifestLoader:
    """Load the evaluables from the manifest."""

    def __init__(self, file_path: Path, select: Iterable[str] | None = None):
        """Initialize the ManifestLoader.

        Args:
            file_path: The file path of the JSON manifest.
            select: An optional dbt selection.
        """
        self.raw_manifest = json.loads(file_path.read_text(encoding="utf-8"))
        self.project_name = self.raw_manifest["metadata"]["project_name"]
        self.raw_nodes = {
            node_id: node_values
            for node_id, node_values in self.raw_manifest.get("nodes", {}).items()
            if node_values["package_name"] == self.project_name
        }
        self.raw_sources = {
            source_id: source_values
            for source_id, source_values in self.raw_manifest.get("sources", {}).items()
            if source_values["package_name"] == self.project_name
        }
        self.raw_exposures = {
            exposure_id: exposure_values
            for exposure_id, exposure_values in self.raw_manifest.get(
                "exposures", {}
            ).items()
            if exposure_values["package_name"] == self.project_name
        }

        self.models: dict[str, Model] = {}
        self.tests: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.sources: dict[str, Source] = {}
        self.snapshots: dict[str, Snapshot] = {}
        self.exposures: dict[str, Exposure] = {}
        self.seeds: dict[str, Seed] = {}

        self._reindex_tests()
        self._load_models()
        self._load_sources()
        self._load_snapshots()
        self._load_exposures()
        self._load_seeds()
        self._populate_relatives()

        if select:
            self._filter_evaluables(select)

        if (
            len(self.models)
            + len(self.sources)
            + len(self.snapshots)
            + len(self.seeds)
            + len(self.exposures)
        ) == 0:
            logger.warning("Nothing to evaluate!")

    def _load_models(self) -> None:
        """Load the models from the manifest."""
        for node_id, node_values in self.raw_nodes.items():
            if node_values.get("resource_type") == "model":
                model = Model.from_node(node_values, self.tests.get(node_id, []))
                self.models[node_id] = model

    def _load_sources(self) -> None:
        """Load the sources from the manifest."""
        for source_id, source_values in self.raw_sources.items():
            if source_values.get("resource_type") == "source":
                source = Source.from_node(source_values, self.tests.get(source_id, []))
                self.sources[source_id] = source

    def _load_snapshots(self) -> None:
        """Load the snapshots from the manifest."""
        for node_id, node_values in self.raw_nodes.items():
            if node_values.get("resource_type") == "snapshot":
                snapshot = Snapshot.from_node(node_values, self.tests.get(node_id, []))
                self.snapshots[node_id] = snapshot

    def _load_exposures(self) -> None:
        """Load the exposures from the manifest."""
        for node_id, node_values in self.raw_exposures.items():
            if node_values.get("resource_type") == "exposure":
                exposure = Exposure.from_node(node_values)
                self.exposures[node_id] = exposure

    def _load_seeds(self) -> None:
        """Load the seeds from the manifest."""
        for node_id, node_values in self.raw_nodes.items():
            if node_values.get("resource_type") == "seed":
                seed = Seed.from_node(node_values, self.tests.get(node_id, []))
                self.seeds[node_id] = seed

    def _reindex_tests(self) -> None:
        """Index tests based on their associated evaluable."""
        for node_values in self.raw_nodes.values():
            if node_values.get("resource_type") == "test":
                # Tests for models have a non-null value for `attached_node`
                if attached_node := node_values.get("attached_node"):
                    self.tests[attached_node].append(node_values)

                # Tests for sources or separate tests will have `attached_node` == null.
                # They need to be attributed to the node id
                # based on the `depends_on` field.
                elif node_unique_id := next(
                    iter(node_values.get("depends_on", {}).get("nodes", [])), None
                ):
                    self.tests[node_unique_id].append(node_values)

    def _populate_relatives(self) -> None:
        """Populate `parents` and `children` for all evaluables."""
        for node in (
            list(self.models.values())
            + list(self.snapshots.values())
            + list(self.exposures.values())
        ):
            for parent_id in node.depends_on.get("nodes", []):
                if parent_id in self.models:
                    node.parents.append(self.models[parent_id])
                    self.models[parent_id].children.append(node)
                elif parent_id in self.snapshots:
                    node.parents.append(self.snapshots[parent_id])
                    self.snapshots[parent_id].children.append(node)
                elif parent_id in self.sources:
                    node.parents.append(self.sources[parent_id])
                    self.sources[parent_id].children.append(node)
                elif parent_id in self.seeds:
                    node.parents.append(self.seeds[parent_id])
                    self.seeds[parent_id].children.append(node)

    def _filter_evaluables(self, select: Iterable[str]) -> None:
        """Filter evaluables like dbt's --select."""
        single_model_select = re.compile(r"[a-zA-Z0-9_]+")

        if all(single_model_select.fullmatch(x) for x in select):
            # Using '--select my_model' is a common case, which can easily be sped up by
            # not invoking dbt
            selected = select
        else:
            # Use dbt's implementation of --select
            selected = dbt_ls(select)

        self.models = {k: m for k, m in self.models.items() if m.name in selected}
        self.sources = {
            k: s for k, s in self.sources.items() if s.selector_name in selected
        }
        self.snapshots = {k: s for k, s in self.snapshots.items() if s.name in selected}
        self.exposures = {k: e for k, e in self.exposures.items() if e.name in selected}
        self.seeds = {k: s for k, s in self.seeds.items() if s.name in selected}
