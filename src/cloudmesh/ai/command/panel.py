import json
import webbrowser
from pathlib import Path
from cloudmesh.ai.common.io import Editor
import http.server
import socketserver
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
import click
import importlib.metadata
from cloudmesh.ai.common.io import console
import importlib

# Plugin Registry
PLUGIN_REGISTRY = {}


def discover_plugins():
    """Dynamically discover and load plugins from entry points and workspace YAMLs."""
    global PLUGIN_REGISTRY
    
    # 1. Discover via entry points
    try:
        eps = importlib.metadata.entry_points(group="cloudmesh.ai.plugin")
        for ep in eps:
            try:
                plugin_class = ep.load()
                plugin_instance = plugin_class()
                PLUGIN_REGISTRY[plugin_instance.plugin_id] = plugin_instance
                print(f"[INFO] Dynamically loaded plugin via entry point: {plugin_instance.plugin_id}")
            except Exception as e:
                print(f"[ERROR] Failed to load plugin {ep.name}: {e}")
    except Exception as e:
        print(f"[ERROR] Entry point discovery failed: {e}")

    # 2. Discover via workspace YAML files (Development fallback)
    try:
        import yaml
        search_paths = [Path.cwd(), Path("/Users/grey/work")]
        for root_dir in search_paths:
            for pkg_dir in root_dir.glob("cloudmesh-ai-*/src/cloudmesh/ai/app/*.yaml"):
                try:
                    with open(pkg_dir, "r") as yaml_file:
                        data = yaml.safe_load(yaml_file)
                        app_list = data.get("cloudmesh", {}).get("ai", {}).get("app", [])
                        if app_list and isinstance(app_list, list):
                            app_info = app_list[0]
                            plugin_path = app_info.get("plugin")
                            if plugin_path:
                                # Split 'module.path.ClassName' into 'module.path' and 'ClassName'
                                module_path, class_name = plugin_path.rsplit(".", 1)
                                module = importlib.import_module(module_path)
                                plugin_class = getattr(module, class_name)
                                plugin_instance = plugin_class()
                                PLUGIN_REGISTRY[plugin_instance.plugin_id] = plugin_instance
                                print(f"[INFO] Dynamically loaded plugin via YAML: {plugin_instance.plugin_id}")
                except Exception as e:
                    print(f"[ERROR] Failed to load plugin from {pkg_dir}: {e}")
    except Exception as e:
        print(f"[ERROR] YAML discovery failed: {e}")


# Initial discovery
discover_plugins()


class PanelViewHandler(http.server.SimpleHTTPRequestHandler):
    """
    HTTP Handler to serve the AI Panel dashboard and its APIs.
    """

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/":
            html_content = getattr(
                self.server, "html_content", "<h1>No content found</h1>"
            )
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))

        elif url.path == "/api/apps":
            apps = self.server.manager.load_apps()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(apps).encode("utf-8"))

        elif url.path.startswith("/api/plugin/"):
            # Extract plugin_id from path: /api/plugin/{plugin_id}/...
            path_parts = url.path.split("/")
            if len(path_parts) < 4:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid plugin path")
                return

            plugin_id = path_parts[3]
            plugin = PLUGIN_REGISTRY.get(plugin_id)

            # Handle plugin actions (e.g., /api/plugin/git/download)
            if len(path_parts) >= 5 and path_parts[4] == "download":
                if plugin and hasattr(plugin, "download_repo"):
                    query = urllib.parse.parse_qs(url.query)
                    repo = query.get("repo", [None])[0]
                    if repo:
                        result = plugin.download_repo(repo)
                        self.send_response(200)
                        self.send_header("Content-type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(result).encode("utf-8"))
                        return
                    else:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b"Missing repo parameter")
                        return
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(
                        f"Download not supported for plugin {plugin_id}".encode("utf-8")
                    )
                    return

            # Handle specific plugin actions
            if plugin_id == "monitor":
                query = urllib.parse.parse_qs(url.query)

                if "update_interval" in url.path:
                    interval_str = query.get("interval", [None])[0]
                    if interval_str:
                        try:
                            interval = int(interval_str)
                            if plugin and hasattr(plugin, "update_interval"):
                                result = plugin.update_interval(interval)
                                self.send_response(200)
                                self.send_header("Content-type", "application/json")
                                self.end_headers()
                                self.wfile.write(json.dumps(result).encode("utf-8"))
                                return
                        except ValueError:
                            self.send_response(400)
                            self.end_headers()
                            self.wfile.write(b"Invalid interval value")
                            return
                    else:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b"Missing interval parameter")
                        return

                elif "update_host_interval" in url.path:
                    label = query.get("label", [None])[0]
                    interval_str = query.get("interval", [None])[0]
                    if label and interval_str:
                        try:
                            interval = int(interval_str)
                            if plugin and hasattr(plugin, "update_host_interval"):
                                result = plugin.update_host_interval(label, interval)
                                self.send_response(200)
                                self.send_header("Content-type", "application/json")
                                self.end_headers()
                                self.wfile.write(json.dumps(result).encode("utf-8"))
                                return
                        except ValueError:
                            self.send_response(400)
                            self.end_headers()
                            self.wfile.write(b"Invalid interval value")
                            return
                    else:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b"Missing label or interval parameter")
                        return

                elif "refresh_host" in url.path:
                    label = query.get("label", [None])[0]
                    if label:
                        if plugin and hasattr(plugin, "refresh_host"):
                            # Run the refresh in a background thread to avoid blocking the HTTP response
                            # and preventing "Network error" timeouts in the browser.
                            threading.Thread(
                                target=plugin.refresh_host, args=(label,), daemon=True
                            ).start()
                            self.send_response(200)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(
                                json.dumps(
                                    {"success": True, "message": "Refresh triggered"}
                                ).encode("utf-8")
                            )
                            return
                    else:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b"Missing label parameter")
                        return

                elif "get_terminal_cmd" in url.path:
                    label = query.get("label", [None])[0]
                    if label:
                        if plugin and hasattr(plugin, "get_terminal_cmd"):
                            result = plugin.get_terminal_cmd(label)
                            self.send_response(200)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps(result).encode("utf-8"))
                            return
                    else:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b"Missing label parameter")
                        return

                elif "open_terminal" in url.path:
                    label = query.get("label", [None])[0]
                    if label:
                        if plugin and hasattr(plugin, "open_terminal"):
                            result = plugin.open_terminal(label)
                            self.send_response(200)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps(result).encode("utf-8"))
                            return
                    else:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b"Missing label parameter")
                        return

                elif "update_host_active" in url.path:
                    label = query.get("label", [None])[0]
                    active_str = query.get("active", [None])[0]
                    if label and active_str:
                        try:
                            # Convert "true"/"false" string to boolean
                            active_bool = active_str.lower() == "true"
                            if plugin and hasattr(plugin, "update_host_active"):
                                result = plugin.update_host_active(label, active_bool)
                                self.send_response(200)
                                self.send_header("Content-type", "application/json")
                                self.end_headers()
                                self.wfile.write(json.dumps(result).encode("utf-8"))
                                return
                        except Exception as e:
                            self.send_response(500)
                            self.end_headers()
                            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                            return
                    else:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b"Missing label or active parameter")
                        return

                elif "edit_hosts" in url.path:
                    print(f"[DEBUG] Received request to edit hosts: {url.path}")
                    try:
                        # Path to hosts.yaml
                        hosts_file = Path.home() / ".config" / "cloudmesh" / "ai" / "hosts.yaml"
                        print(f"[DEBUG] Target hosts file: {hosts_file}")
                        if hosts_file.exists():
                            print(f"[DEBUG] File exists, calling Editor().edit() in background")
                            threading.Thread(
                                target=Editor().edit, args=(str(hosts_file),), daemon=True
                            ).start()
                            self.send_response(200)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps({"success": True, "message": f"Opened {hosts_file}"}).encode("utf-8"))
                            return
                        else:
                            self.send_response(404)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps({"success": False, "error": "hosts.yaml not found"}).encode("utf-8"))
                            return
                    except Exception as e:
                        self.send_response(500)
                        self.send_header("Content-type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                        return

                elif "detail" in url.path:
                    label = query.get("label", [None])[0]
                    if label:
                        # We use HostManager to get the merged config and status for the host
                        from cloudmesh.ai.monitor.core import HostManager
                        hm = HostManager.get_instance()
                        info = hm.get_host_info(label)
                        if info:
                            self.send_response(200)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps({"success": True, "data": info}).encode("utf-8"))
                            return
                        else:
                            self.send_response(404)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps({"success": False, "error": "Host not found"}).encode("utf-8"))
                            return
                    else:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b"Missing label parameter")
                        return

                elif "update_host" in url.path:
                    query = urllib.parse.parse_qs(url.query)
                    label = query.get("label", [None])[0]
                    hostname = query.get("hostname", [None])[0]
                    active = query.get("active", ["true"])[0].lower() == "true"
                    interval = query.get("interval", ["10"])[0]
                    probe_cmd = query.get("probe_cmd", [None])[0]

                    if label and hostname:
                        try:
                            from cloudmesh.ai.monitor.core import HostManager
                            hm = HostManager.get_instance()
                            hm.add_host(
                                label=label,
                                hostname=hostname,
                                active=active,
                                refresh_interval=int(interval),
                                probe_cmd=probe_cmd
                            )
                            self.send_response(200)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps({"success": True, "message": f"Host {label} updated"}).encode("utf-8"))
                            return
                        except Exception as e:
                            self.send_response(500)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                            return
                    else:
                        self.send_response(400)
                        self.send_header("Content-type", "application/json")
                        self.end_headers()
                        self.wfile.write(b"Missing label or hostname parameter")
                        return

                elif "add_host" in url.path:
                    # For adding a host, we expect a POST-like request via GET for simplicity in this panel
                    # In a real app, this should be a POST request with a JSON body
                    query = urllib.parse.parse_qs(url.query)
                    label = query.get("label", [None])[0]
                    hostname = query.get("hostname", [None])[0]
                    active = query.get("active", ["true"])[0].lower() == "true"
                    interval = query.get("interval", ["10"])[0]
                    probe_cmd = query.get("probe_cmd", [None])[0]

                    if label and hostname:
                        try:
                            from cloudmesh.ai.monitor.core import HostManager
                            hm = HostManager.get_instance()
                            hm.add_host(
                                label=label,
                                hostname=hostname,
                                active=active,
                                refresh_interval=int(interval),
                                probe_cmd=probe_cmd
                            )
                            self.send_response(200)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps({"success": True, "message": f"Host {label} added"}).encode("utf-8"))
                            return
                        except Exception as e:
                            self.send_response(500)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                            return
                    else:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b"Missing label or hostname parameter")
                        return

                elif "probe_commands" in url.path:
                    # Return a list of common probe commands
                    commands = [
                        {"name": "Default (GPU/CPU/Mem)", "cmd": ""},
                        {"name": "NVIDIA DGX", "cmd": "cm_dgx_smi"},
                        {"name": "NVIDIA spark", "cmd": "cm_spark_smi"},
                        {"name": "Mac OS", "cmd": "cm_mac_smi"},
                        {"name": "GPU Only", "cmd": "nvidia-smi --query-gpu=utilization.gpu,temperature.gpu --format=csv,noheader,nounits"},
                        {"name": "CPU Load", "cmd": "top -bn1 | grep 'Cpu(s)'"},
                        {"name": "Memory Free", "cmd": "free -m"},
                        {"name": "Uptime", "cmd": "uptime -p"}
                    ]
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(commands).encode("utf-8"))
                    return

                elif "logs" in url.path:
                    # Simple log streaming endpoint. 
                    # In a real scenario, we'd read from a log file or a shared queue.
                    # For now, we'll return a mock set of logs or read the last few lines of a log file if it exists.
                    log_file = Path.home() / ".config" / "cloudmesh" / "ai" / "panel.log"
                    logs = []
                    if log_file.exists():
                        with open(log_file, "r") as f:
                            logs = f.readlines()[-50:] # Last 50 lines
                    
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"logs": [l.strip() for l in logs]}).encode("utf-8"))
                    return

            # Dynamic method call for plugins
            if plugin:
                # If there's a specific action requested (e.g., /api/plugin/multipass/launch_gui)
                if len(path_parts) >= 5:
                    action = path_parts[4]
                    method = getattr(plugin, action, None)
                    if callable(method):
                        try:
                            # Extract query parameters to pass as keyword arguments
                            query_params = urllib.parse.parse_qs(url.query)
                            # parse_qs returns lists for values, we take the first element
                            kwargs = {k: v[0] for k, v in query_params.items()}
                            
                            result = method(**kwargs)
                            self.send_response(200)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps(result).encode("utf-8"))
                            return
                        except Exception as e:
                            self.send_response(500)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                            return

                # Default fallback: fetch data
                data = plugin.get_data()
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))
            else:
                self.send_response(404)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Plugin {plugin_id} not found"}).encode("utf-8"))
                return

        elif url.path.startswith("/api/configs/"):
            filename = url.path.replace("/api/configs/", "")
            root_dir = Path(__file__).parent.parent.parent.parent.parent.parent

            # Search for the asset in all registered plugins
            asset_path = None
            for plugin in PLUGIN_REGISTRY.values():
                assets = plugin.get_assets()
                if filename in assets:
                    asset_path = root_dir / assets[filename]
                    break

            if asset_path and asset_path.exists():
                self.send_response(200)
                content_type = (
                    "text/css"
                    if filename.endswith(".css")
                    else "application/javascript"
                )
                self.send_header("Content-type", content_type)
                self.end_headers()
                with open(asset_path, "rb") as f:
                    self.wfile.write(f.read())
                return

            self.send_response(404)
            self.end_headers()
            self.wfile.write(f"Config file {filename} not found".encode("utf-8"))
            return

        elif url.path.rstrip('/') == "/api/available-components":
            components = []
            print("\n--- Discovering Available Components via CMC Convention ---")
            try:
                import yaml

                # We leverage the fact that all AI components are registered as CMC commands.
                # We scan for packages that provide 'cloudmesh.ai' entry points.
                print("Scanning for packages providing cloudmesh.ai commands...")

                # Get all entry points for cloudmesh.ai commands
                # This mimics how CMC discovers commands
                ai_eps = importlib.metadata.entry_points(group="cloudmesh.ai")

                # Track which distributions we've already scanned to avoid duplicates
                scanned_dists = set()

                for ep in ai_eps:
                    try:
                        # Find the distribution that provides this entry point
                        dist = importlib.metadata.distribution(ep.dist)
                        dist_name = dist.metadata["Name"]

                        if dist_name in scanned_dists:
                            continue
                        scanned_dists.add(dist_name)

                        # Now check if this distribution has an 'app' directory with YAML files
                        files = dist.files
                        if files is None:
                            continue

                        app_files = [
                            f
                            for f in files
                            if f.name.startswith("cloudmesh/ai/app/")
                            and f.name.endswith(".yaml")
                        ]
                        for f in app_files:
                            try:
                                file_path = f.locate()
                                print(
                                    f"Found app metadata in CMC-registered package {dist_name}: {file_path}"
                                )
                                with open(file_path, "r") as yaml_file:
                                    data = yaml.safe_load(yaml_file)
                                    app_list = (
                                        data.get("cloudmesh", {})
                                        .get("ai", {})
                                        .get("app", [])
                                    )
                                    if app_list and isinstance(app_list, list):
                                        app_info = app_list[0]
                                        app_id = Path(f.name).stem

                                        # Use plugin metadata if available
                                        plugin = PLUGIN_REGISTRY.get(app_id)
                                        components.append(
                                            {
                                                "id": app_id,
                                                "name": (
                                                    plugin.plugin_name
                                                    if plugin
                                                    else app_info.get("name", app_id)
                                                ),
                                                "icon": (
                                                    plugin.plugin_icon
                                                    if plugin
                                                    else app_info.get(
                                                        "image", "fa-solid fa-plug"
                                                    )
                                                ),
                                                "description": (
                                                    plugin.plugin_description
                                                    if plugin
                                                    else "No description available."
                                                ),
                                            }
                                        )
                            except Exception as e:
                                print(
                                    f"Error reading metadata file {f.name} in {dist_name}: {e}"
                                )
                    except Exception as e:
                        print(f"Error processing entry point {ep.name}: {e}")

                # Fallback for development: if no components found via entry points,
                # scan the workspace for the same convention.
                if not components:
                    print(
                        "No components found via CMC entry points. Trying workspace fallback..."
                    )
                    search_paths = [Path.cwd(), Path("/Users/grey/work")]
                    for root_dir in search_paths:
                        for pkg_dir in root_dir.glob(
                            "cloudmesh-ai-*/src/cloudmesh/ai/app/*.yaml"
                        ):
                            try:
                                with open(pkg_dir, "r") as yaml_file:
                                    data = yaml.safe_load(yaml_file)
                                    app_list = (
                                        data.get("cloudmesh", {})
                                        .get("ai", {})
                                        .get("app", [])
                                    )
                                    if app_list and isinstance(app_list, list):
                                        app_info = app_list[0]
                                        app_id = pkg_dir.stem

                                        # Use plugin metadata if available
                                        plugin = PLUGIN_REGISTRY.get(app_id)
                                        components.append(
                                            {
                                                "id": app_id,
                                                "name": (
                                                    plugin.plugin_name
                                                    if plugin
                                                    else app_info.get("name", app_id)
                                                ),
                                                "icon": (
                                                    plugin.plugin_icon
                                                    if plugin
                                                    else app_info.get(
                                                        "image", "fa-solid fa-plug"
                                                    )
                                                ),
                                                "description": (
                                                    plugin.plugin_description
                                                    if plugin
                                                    else "No description available."
                                                ),
                                            }
                                        )
                            except Exception:
                                pass

            except Exception as e:
                print(f"Error in CMC-based discovery: {e}")

            print(
                f"Discovery complete. Found {len(components)} components: {[c['id'] for c in components]}"
            )
            print("---------------------------------------\n")
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(components).encode("utf-8"))

        elif url.path == "/api/activate":
            query = urllib.parse.parse_qs(url.query)
            app_id = query.get("id", [None])[0]
            name = query.get("name", [None])[0]
            icon = query.get("icon", ["mdi-application-marker"])[0]

            if app_id and name:
                self.server.manager.activate_app(name, app_id, icon)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Activated successfully")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing parameters")

        elif url.path == "/api/deactivate":
            query = urllib.parse.parse_qs(url.query)
            app_id = query.get("id", [None])[0]

            if app_id:
                self.server.manager.deactivate_app(app_id)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Deactivated successfully")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing parameters")

        else:
            super().do_GET()


class PanelManager:
    """
    Manages the registration of applications in the AI Panel.
    """

    def __init__(self):
        self.config_file = Path.home() / ".config" / "cloudmesh" / "panel" / "apps.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

    def load_apps(self):
        if not self.config_file.exists():
            return []
        try:
            with open(self.config_file, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def activate_app(self, name, app_id, icon="mdi-application-marker"):
        apps = self.load_apps()
        if any(app["id"] == app_id for app in apps):
            console.warning(f"App with id {app_id} is already active.")
            return

        apps.append({"id": app_id, "name": name, "icon": icon})
        with open(self.config_file, "w") as f:
            json.dump(apps, f, indent=4)
        console.ok(f"Activated application '{name}' ({app_id}) in the panel.")

    def deactivate_app(self, app_id):
        apps = self.load_apps()
        new_apps = [app for app in apps if app["id"] != app_id]
        if len(new_apps) == len(apps):
            console.warning(f"App with id {app_id} is not active.")
            return

        with open(self.config_file, "w") as f:
            json.dump(new_apps, f, indent=4)
        console.ok(f"Deactivated application ({app_id}) from the panel.")


@click.group(name="panel")
def panel_group():
    """
    Cloudmesh AI Panel for managing AI extensions.
    """
    pass


@panel_group.command(name="view")
@click.argument("plugin", required=False)
def view_cmd(plugin):
    """
    View the AI Panel dashboard.

    This command starts a local HTTP server and opens the AI Panel
    dashboard in the default web browser.

    Example:
        cmc panel view
    """
    template_path = Path(__file__).parent / "panel_view.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    except Exception as e:
        console.error(f"Could not load template: {e}")
        return

    manager = PanelManager()

    class Handler(PanelViewHandler):
        def __init__(self, *args, **kwargs):
            self.server.html_content = html_content
            self.server.manager = manager
            super().__init__(*args, **kwargs)

        def get_apps(self):
            return self.server.manager.load_apps()

    # To avoid the __init__ issue from before, we attach to the server object
    # Use ThreadingTCPServer to prevent long-running probes from blocking the UI
    class Server(socketserver.ThreadingTCPServer):
        def __init__(self, server_address, RequestHandlerClass):
            self.html_content = html_content
            self.manager = manager
            self.stop_background_probes = threading.Event()
            super().__init__(server_address, RequestHandlerClass)

        def start_background_probes(self):
            """Starts a background thread to periodically refresh monitor data."""

            def probe_loop():
                print("[INFO] Background probing thread started.")
                # Use a ThreadPoolExecutor to probe hosts in parallel
                with ThreadPoolExecutor(max_workers=10) as executor:
                    while not self.stop_background_probes.is_set():
                        try:
                            monitor_plugin = PLUGIN_REGISTRY.get("monitor")
                            if monitor_plugin:
                                hm = HostManager.get_instance()
                                active_hosts = [label for label, info in hm.get_hosts_ordered() if info.get("active", True)]
                                
                                # Submit all active hosts to the thread pool
                                futures = [executor.submit(monitor_plugin.refresh_host, label) for label in active_hosts]
                                
                                # We don't necessarily need to wait for all to finish before starting the sleep,
                                # but it's cleaner to ensure one cycle completes before the next.
                                # However, to avoid blocking the loop too long, we can just let them run.
                        except Exception as e:
                            print(f"[ERROR] Background probe loop error: {e}")

                        # Sleep for a default interval (e.g., 30s) or check config
                        self.stop_background_probes.wait(timeout=30)
                print("[INFO] Background probing thread stopped.")

            thread = threading.Thread(target=probe_loop, daemon=True)
            thread.start()

    try:
        with Server(("", 0), PanelViewHandler) as httpd:
            port = httpd.server_address[1]
            
            # Start the background probing thread to keep monitor data fresh
            httpd.start_background_probes()
            
            server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            server_thread.start()
            
            url = f"http://localhost:{port}"
            if plugin:
                url += f"?plugin={urllib.parse.quote(plugin)}"

            webbrowser.open(url)
            console.ok(f"AI Panel running at {url}")

            click.echo("\nPanel is open. Press Enter to close the server...")
            input()
            httpd.shutdown()
    except Exception as e:
        console.error(f"Error starting panel server: {e}")


@panel_group.command(name="activate")
@click.option("--name", required=True, help="Name of the application")
@click.option("--id", "app_id", required=True, help="Unique ID for the application")
@click.option("--icon", default="fa-solid fa-plug", help="FontAwesome icon name")
def activate_cmd(name, app_id, icon):
    """
    Activate an application in the panel side navigation.

    This command manually adds an application to the AI Panel's
    active applications list.

    Example:
        cmc panel activate --name "My AI App" --id "my-ai-app" --icon "fa-robot"
    """
    manager = PanelManager()
    manager.activate_app(name, app_id, icon)


@panel_group.command(name="deactivate")
@click.option("--id", "app_id", required=True, help="Unique ID for the application")
def deactivate_cmd(app_id):
    """
    Deactivate an application from the panel side navigation.

    This command removes an application from the AI Panel's
    active applications list using its unique ID.

    Example:
        cmc panel deactivate --id "my-ai-app"
    """
    manager = PanelManager()
    manager.deactivate_app(app_id)


@panel_group.command(name="reset")
def reset_cmd():
    """
    Reset the AI Panel registration.

    This command clears all registered applications from the
    AI Panel configuration file.

    Example:
        cmc panel reset
    """
    manager = PanelManager()
    if manager.config_file.exists():
        manager.config_file.unlink()
        console.ok("Cleared all registered applications from the panel.")
    else:
        console.ok("No registered applications to clear.")


def register(cli):
    """
    Registers the panel commands with the main CLI.
    """
    cli.add_command(panel_group)
