"""Run upstream's unchanged shim against this installation's mode-specific daemon."""
import os
from pathlib import Path

from origin_pro_mcp.shim import ShimClient, build_shim_server


def main():
    attach = os.environ.get("ORIGIN_PLOT_SESSION") == "attach"
    mode = "attach" if attach else "isolated"
    state = Path(os.environ["LOCALAPPDATA"]) / "OriginPlot" / "upstream-1e9741a" / mode
    state.mkdir(parents=True, exist_ok=True)
    # These flags belong to this private daemon. Never change a user's other MCP clients.
    os.environ.update(ORIGIN_PRO_MCP_ATTACH="1" if attach else "0",
                      ORIGIN_PRO_MCP_REAP_CLOSE="0" if attach else "1",
                      ORIGIN_PRO_MCP_AUTOSAVE="0", ORIGIN_PRO_MCP_AUTOSAVE_INTERVAL="0",
                      ORIGIN_PRO_MCP_SWEEP_ORPHANS="0", ORIGIN_PRO_MCP_DIALOG_AUTODISMISS="0",
                      ORIGIN_PRO_MCP_RECOVERY_DIR=str(state / "recovery"))
    client = ShimClient(lockfile_path=str(state / "daemon.json"))
    try:
        build_shim_server(client).run(transport="stdio")
    finally:
        client.close()


if __name__ == "__main__":
    main()
