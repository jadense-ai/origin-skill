from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from .runtime import Runtime


def application(runtime: Runtime):
    @asynccontextmanager
    async def lifespan(_):
        try:
            yield {}
        finally:
            await runtime.close()

    app = FastMCP("origin-plot", lifespan=lifespan)

    async def dispatch(method, values):
        values.pop("dispatch", None)
        async with runtime.lock:
            return await getattr(runtime, method)(**values)

    @app.tool()
    async def origin_plot_doctor(live: bool = False) -> dict:
        """Check local configuration. live=True verifies a real Origin session and its embedded Python."""
        return await dispatch("doctor", locals())

    @app.tool()
    async def origin_plot_render(recipe_id: str, data_path: str, output_dir: str,
                                 columns: dict | None = None, options: dict | None = None,
                                 title: str | None = None, sheet: str | None = None, journal: str | None = None,
                                 journal_options: dict | None = None, formats: list[str] | None = None,
                                 width: int | None = None, reopen: bool = True, template_path: str | None = None) -> dict:
        """Render a bundled recipe from CSV/TSV/XLSX, save a native OPJU, export and verify the reopened graph."""
        return await dispatch("render", locals())

    @app.tool()
    async def origin_plot_render_template(template_path: str, data_path: str, output_dir: str, x: str, y: str,
                                          plot_type: str | None = None, title: str | None = None, sheet: str | None = None,
                                          journal: str | None = None, journal_options: dict | None = None,
                                          formats: list[str] | None = None, width: int | None = None, reopen: bool = True) -> dict:
        """Bind numeric X/Y with the original template type. Optionally require line, scatter, line+symbol or column."""
        return await dispatch("render_template", locals())

    @app.tool()
    async def origin_plot_inspect(graph_name: str = "", project_path: str | None = None) -> dict:
        """Read native plot, axis and source information. Omit graph_name to inspect the active project's graphs."""
        return await dispatch("inspect", locals())

    @app.tool()
    async def origin_plot_edit(graph_name: str, output_dir: str, changes: dict | None = None,
                               project_path: str | None = None, journal: str | None = None,
                               journal_options: dict | None = None, formats: list[str] | None = None,
                               width: int | None = None, session_token: str | None = None, reopen: bool | None = None) -> dict:
        """Edit one named graph and save a new OPJU. changes accepts 1-based layer/plot, x_title, y_title,
        x_range, y_range, color (#RRGGBB), line_width, symbol_size, legend_text, long_name,
        width_mm, height_mm, bin_width, bin_count, bin_begin or bin_end.
        Attach-mode edits of the live GUI require the session_token returned by inspect."""
        return await dispatch("edit", locals())

    @app.tool()
    async def origin_plot_export(graph_name: str, output_dir: str, project_path: str | None = None,
                                 formats: list[str] | None = None, width: int = 1800) -> dict:
        """Export a named graph to raster or vector files and report validated file evidence."""
        return await dispatch("export", locals())

    @app.tool()
    async def origin_plot_save_template(graph_name: str, output_dir: str, project_path: str | None = None,
                                        old_format: bool = False) -> dict:
        """Save a named native Origin graph as OTPU, or as OTP when old_format=True."""
        return await dispatch("save_template", locals())

    @app.tool()
    async def origin_plot_reopen(project_path: str, graph_name: str = "") -> dict:
        """Open a private copy of an OPJU/OPJ in an isolated session and return native inspection evidence."""
        return await dispatch("reopen", locals())

    return app
