"""CLI interface."""

import logging
import traceback
from pathlib import Path
from typing import Final, Literal

import click
from click.core import ParameterSource

from dbt_score.config import Config
from dbt_score.dbt_utils import (
    DbtParseException,
    dbt_parse,
    get_default_manifest_path,
)
from dbt_score.lint import lint_dbt_project
from dbt_score.rule_catalog import display_catalog

logger = logging.getLogger(__name__)

BANNER: Final[str] = r"""
          __ __     __
     ____/ // /_   / /_        _____ _____ ____   _____ ___
    / __  // __ \ / __/______ / ___// ___// __ \ / ___// _ \
   / /_/ // /_/ // /_ /_____/(__  )/ /__ / /_/ // /   /  __/
   \__,_//_.___/ \__/       /____/ \___/ \____//_/    \___/
    """


@click.version_option(message="%(version)s")
@click.group(
    help=f"\b{BANNER}",
    invoke_without_command=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
def cli() -> None:
    """CLI entrypoint."""


@cli.command()
@click.option(
    "--format",
    "-f",
    help="Output format. Plain is suitable for terminals, manifest for rich "
    "documentation, json for machine-readable output.",
    type=click.Choice(["plain", "manifest", "ascii", "json"]),
    default="plain",
)
@click.option(
    "--select",
    "-s",
    help="Specify the nodes to include.",
    multiple=True,
)
@click.option(
    "--namespace",
    "-n",
    help="Namespace to look for rules.",
    default=None,
    multiple=True,
)
@click.option(
    "--disabled-rule",
    help="Rule to disable.",
    default=None,
    multiple=True,
)
@click.option(
    "--selected-rule",
    help="Rule to select.",
    default=None,
    multiple=True,
)
@click.option(
    "--manifest",
    "-m",
    help="Manifest filepath.",
    type=click.Path(path_type=Path),
    default=get_default_manifest_path(),
)
@click.option(
    "--run-dbt-parse",
    "-p",
    help="Run dbt parse.",
    is_flag=True,
    default=False,
)
@click.option(
    "--fail-project-under",
    help="Fail if the project score is under this value.",
    type=float,
    is_flag=False,
    default=None,
)
@click.option(
    "--fail-any-item-under",
    help="Fail if any evaluable item is under this value.",
    type=float,
    is_flag=False,
    default=None,
)
@click.option(
    "--show",
    help="Type of output which should be shown "
    "when using `plain` as `--format`. "
    "`all` shows all items and all rules. "
    "`failing-items` shows failing rules of failing items. "
    "`failing-rules` shows failing rules of all items. "
    "Default is --failing-rules.",
    type=click.Choice(["all", "failing-items", "failing-rules"]),
    is_flag=False,
    default="failing-rules",
)
@click.option(
    "--debug",
    "-d",
    help="Jump in a debugger in case of rule failure to evaluate.",
    type=bool,
    is_flag=True,
    default=False,
)
@click.pass_context
def lint(  # noqa: PLR0912, PLR0913, C901
    ctx: click.Context,
    format: Literal["plain", "manifest", "ascii"],
    select: tuple[str],
    namespace: list[str],
    disabled_rule: list[str],
    selected_rule: list[str],
    manifest: Path,
    run_dbt_parse: bool,
    fail_project_under: float,
    fail_any_item_under: float,
    show: Literal["all", "failing-items", "failing-rules"],
    debug: bool,
) -> None:
    """Lint dbt metadata."""
    manifest_provided = (
        click.get_current_context().get_parameter_source("manifest")
        != ParameterSource.DEFAULT
    )
    if manifest_provided and run_dbt_parse:
        raise click.UsageError("--run-dbt-parse cannot be used with --manifest.")

    if len(selected_rule) > 0 and len(disabled_rule) > 0:
        raise click.UsageError(
            "--disabled-rule and --selected-rule cannot be used together."
        )

    config = Config()
    config.load()
    if namespace:
        config.overload({"rule_namespaces": namespace})
    if disabled_rule:
        config.overload({"disabled_rules": disabled_rule})
    if selected_rule:
        config.overload({"selected_rules": selected_rule})
    if fail_project_under:
        config.overload({"fail_project_under": fail_project_under})
    if fail_any_item_under:
        config.overload({"fail_any_item_under": fail_any_item_under})
    if show:
        config.overload({"show": show})
    if debug:
        config.overload({"debug": debug})

    try:
        if run_dbt_parse:
            dbt_parse()
        evaluation = lint_dbt_project(
            manifest_path=manifest, config=config, format=format, select=select
        )

    except FileNotFoundError:
        logger.error(
            "dbt's manifest.json could not be found. If you're in a dbt project, be "
            "sure to run 'dbt parse' first, or use the option '--run-dbt-parse'."
        )
        ctx.exit(2)

    except DbtParseException as exc:
        logger.error(exc)
        ctx.exit(2)

    except Exception:
        logger.error(traceback.format_exc())
        ctx.exit(2)

    if (
        any(x.value < config.fail_any_item_under for x in evaluation.scores.values())
        or evaluation.project_score.value < config.fail_project_under
    ):
        ctx.exit(1)


@cli.command(name="list")
@click.option(
    "--namespace",
    "-n",
    help="Namespace.",
    default=None,
    multiple=True,
)
@click.option(
    "--disabled-rule",
    help="Rule to disable.",
    default=None,
    multiple=True,
)
@click.option(
    "--selected-rule",
    help="Rule to select.",
    default=None,
    multiple=True,
)
@click.option(
    "--title",
    help="Page title (Markdown only).",
    default=None,
)
@click.option(
    "--format",
    "-f",
    help="Output format.",
    type=click.Choice(["terminal", "markdown"]),
    default="terminal",
)
def list_command(
    namespace: list[str],
    disabled_rule: list[str],
    selected_rule: list[str],
    title: str,
    format: str,
) -> None:
    """Display rules list."""
    if len(selected_rule) > 0 and len(disabled_rule) > 0:
        raise click.UsageError(
            "--disabled-rule and --selected-rule cannot be used together."
        )

    config = Config()
    config.load()
    if namespace:
        config.overload({"rule_namespaces": namespace})
    if disabled_rule:
        config.overload({"disabled_rules": disabled_rule})
    if selected_rule:
        config.overload({"selected_rules": selected_rule})

    display_catalog(config, title, format)
