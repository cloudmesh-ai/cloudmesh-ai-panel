import json
import webbrowser
from pathlib import Path
import http.server
import socketserver
import threading
import urllib.parse
import click
import importlib.metadata
from cloudmesh.ai.common.io import console
from cloudmesh.ai.command.adapters import StoragePlugin, GitPlugin

# Plugin Registry
PLUGIN_REGISTRY = {
    "storage": StoragePlugin(),
    "git": GitPlugin(),
}

class PanelViewHandler(http.server.SimpleHTTPRequestHandler):
    """
    HTTP Handler to serve the AI Panel dashboard and its APIs.
    """
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/":
            html_content = getattr(self.server, "html_content", "<h1>No content found</h1>")
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
            plugin_id = url.path.replace("/api/plugin/", "")
            plugin = PLUGIN_REGISTRY.get(plugin_id)
            if plugin:
                data = plugin.get_data()
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(f"Plugin {plugin_id} not found".encode("utf-8"))
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
                content_type = "text/css" if filename.endswith(".css") else "application/javascript"
                self.send_header("Content-type", content_type)
                self.end_headers()
                with open(asset_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            
            self.send_response(404)
            self.end_headers()
            self.wfile.write(f"Config file {filename} not found".encode("utf-8"))
            return

        elif url.path == "/api/available-components":
            components = []
            print("\n--- Discovering Available Components via CMC Convention ---")
            try:
                import yaml
                # We leverage the fact that all AI components are registered as CMC commands.
                # We scan for packages that provide 'cloudmesh.ai' entry points.
                print("Scanning for packages providing cloudmesh.ai commands...")
                
                # Get all entry points for cloudmesh.ai commands
                # This mimics how CMC discovers commands
                ai_eps = importlib.metadata.entry_points(group='cloudmesh.ai')
                
                # Track which distributions we've already scanned to avoid duplicates
                scanned_dists = set()
                
                for ep in ai_eps:
                    try:
                        # Find the distribution that provides this entry point
                        dist = importlib.metadata.distribution(ep.dist)
                        dist_name = dist.metadata['Name']
                        
                        if dist_name in scanned_dists:
                            continue
                        scanned_dists.add(dist_name)
                        
                        # Now check if this distribution has an 'app' directory with YAML files
                        files = dist.files
                        if files is None: continue
                        
                        app_files = [f for f in files if f.name.startswith("cloudmesh/ai/app/") and f.name.endswith(".yaml")]
                        for f in app_files:
                            try:
                                file_path = f.locate()
                                print(f"Found app metadata in CMC-registered package {dist_name}: {file_path}")
                                with open(file_path, "r") as yaml_file:
                                    data = yaml.safe_load(yaml_file)
                                    app_list = data.get("cloudmesh", {}).get("ai", {}).get("app", [])
                                    if app_list and isinstance(app_list, list):
                                     app_info = app_list[0]
                                     app_id = Path(f.name).stem
                                     
                                     # Use plugin metadata if available
                                     plugin = PLUGIN_REGISTRY.get(app_id)
                                     components.append({
                                         "id": app_id,
                                         "name": plugin.plugin_name if plugin else app_info.get("name", app_id),
                                         "icon": plugin.plugin_icon if plugin else app_info.get("image", "fa-solid fa-plug"),
                                         "description": plugin.plugin_description if plugin else "No description available."
                                     })
                            except Exception as e:
                                print(f"Error reading metadata file {f.name} in {dist_name}: {e}")
                    except Exception as e:
                        print(f"Error processing entry point {ep.name}: {e}")

                # Fallback for development: if no components found via entry points, 
                # scan the workspace for the same convention.
                if not components:
                    print("No components found via CMC entry points. Trying workspace fallback...")
                    search_paths = [Path.cwd(), Path("/Users/grey/work")]
                    for root_dir in search_paths:
                        for pkg_dir in root_dir.glob("cloudmesh-ai-*/src/cloudmesh/ai/app/*.yaml"):
                            try:
                                with open(pkg_dir, "r") as yaml_file:
                                    data = yaml.safe_load(yaml_file)
                                    app_list = data.get("cloudmesh", {}).get("ai", {}).get("app", [])
                                    if app_list and isinstance(app_list, list):
                                     app_info = app_list[0]
                                     app_id = pkg_dir.stem
                                     
                                     # Use plugin metadata if available
                                     plugin = PLUGIN_REGISTRY.get(app_id)
                                     components.append({
                                         "id": app_id,
                                         "name": plugin.plugin_name if plugin else app_info.get("name", app_id),
                                         "icon": plugin.plugin_icon if plugin else app_info.get("image", "fa-solid fa-plug"),
                                         "description": plugin.plugin_description if plugin else "No description available."
                                     })
                            except Exception: pass

            except Exception as e:
                print(f"Error in CMC-based discovery: {e}")
            
            print(f"Discovery complete. Found {len(components)} components: {[c['id'] for c in components]}")
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
def view_cmd():
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
    class Server(socketserver.TCPServer):
        def __init__(self, server_address, RequestHandlerClass):
            self.html_content = html_content
            self.manager = manager
            super().__init__(server_address, RequestHandlerClass)

    try:
        with Server(("", 0), PanelViewHandler) as httpd:
            port = httpd.server_address[1]
            server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            server_thread.start()
            
            url = f"http://localhost:{port}"
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