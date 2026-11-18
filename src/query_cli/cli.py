"""qcli: queries parametrizadas por región.

    qcli list
    qcli show orders_by_status
    qcli run orders_by_status -r cas -r carib -p status=PAID -p days=7
    qcli run orders_by_status -r all -o csv > pedidos.csv
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from . import __version__
from .errors import QueryCliError
from .output import FORMATTERS
from .queries import Query, load_queries
from .regions import load_regions, select_regions
from .render import render
from .runner import run


def _parse_params(pairs: tuple[str, ...]) -> dict[str, str]:
    params: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise click.BadParameter(f"'{pair}' debe tener la forma clave=valor.", param_hint="-p")
        params[key.strip()] = value
    return params


class Context:
    def __init__(self, queries_dir: Path, regions_file: Path) -> None:
        self.queries_dir = queries_dir
        self.regions_file = regions_file

    def query(self, name: str) -> Query:
        queries = load_queries(self.queries_dir)
        if name not in queries:
            raise QueryCliError(f"No existe la query '{name}'. Probá 'qcli list'.")
        return queries[name]


@click.group()
@click.version_option(__version__, prog_name="qcli")
@click.option("--queries", "queries_dir", type=click.Path(path_type=Path), default="queries",
              show_default=True, envvar="QCLI_QUERIES_DIR", help="Directorio de queries.")
@click.option("--regions", "regions_file", type=click.Path(path_type=Path),
              default="regions.yaml", show_default=True, envvar="QCLI_REGIONS_FILE",
              help="Archivo de regiones.")
@click.option("--env-file", type=click.Path(path_type=Path), default=".env", show_default=True,
              help="Archivo .env con las credenciales (si existe).")
@click.pass_context
def cli(ctx: click.Context, queries_dir: Path, regions_file: Path, env_file: Path) -> None:
    """Queries parametrizadas en MongoDB y Couchbase, por región."""
    if env_file.exists():
        load_dotenv(env_file, override=False)
    ctx.obj = Context(queries_dir, regions_file)


@cli.command("list")
@click.pass_obj
def list_cmd(obj: Context) -> None:
    """Lista las queries disponibles."""
    for q in load_queries(obj.queries_dir).values():
        flag = " [escritura]" if q.is_write else ""
        click.echo(f"{q.name:<28} {q.engine:<10} {q.description}{flag}")


@cli.command()
@click.argument("name")
@click.pass_obj
def show(obj: Context, name: str) -> None:
    """Muestra parámetros y plantilla de una query."""
    q = obj.query(name)
    click.echo(f"{q.name} ({q.engine}.{q.operation})\n{q.description}\n")
    for p in q.params.values():
        req = "obligatorio" if p.required and p.default is None else f"default={p.default!r}"
        choices = f" opciones={list(p.choices)}" if p.choices else ""
        click.echo(f"  -p {p.name}=<{p.type}>  {req}{choices}  {p.description}")
    click.echo(f"\n{q.template}")


@cli.command("run")
@click.argument("name")
@click.option("-r", "--region", "regions", multiple=True, help="Región (repetible) o 'all'.")
@click.option("-p", "--param", "params", multiple=True, help="Parámetro clave=valor (repetible).")
@click.option("-o", "--output", type=click.Choice(sorted(FORMATTERS)), default="table",
              show_default=True)
@click.option("--dry-run", is_flag=True, help="Solo muestra la query renderizada.")
@click.option("--allow-write", is_flag=True, help="Permite queries que modifican datos.")
@click.pass_obj
def run_cmd(obj: Context, name: str, regions: tuple[str, ...], params: tuple[str, ...],
            output: str, dry_run: bool, allow_write: bool) -> None:
    """Ejecuta una query en una o varias regiones."""
    q = obj.query(name)
    given = _parse_params(params)
    if dry_run:
        rendered = render(q, q.resolve_params(given))
        click.echo(json.dumps(rendered, ensure_ascii=False, indent=2, default=str))
        return

    selected = select_regions(load_regions(obj.regions_file), list(regions))
    if q.is_write and allow_write:
        names = ", ".join(r.name for r in selected)
        click.confirm(f"'{q.name}' va a modificar datos en: {names}. ¿Continuar?", abort=True)

    results = run(q, given, selected, allow_write=allow_write)
    click.echo(FORMATTERS[output](results))
    if not all(r.ok for r in results):
        sys.exit(2)


def main() -> None:
    try:
        cli(standalone_mode=False)
    except click.exceptions.Abort:
        click.echo("Cancelado.", err=True)
        sys.exit(1)
    except click.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except QueryCliError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
