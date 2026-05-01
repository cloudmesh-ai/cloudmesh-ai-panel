from cloudmesh.ai.command.plugin import PanelPlugin
from cloudmesh.ai.command.storage_view import StorageInfoView
from cloudmesh.ai.command.git_view import GitInfoView
from cloudmesh.ai.command.git import UserConfig, fetch_all_repos_for_user
from cloudmesh.ai.monitor.terminalgui.core import HostManager
from typing import Any

class StoragePlugin(PanelPlugin):
    @property
    def plugin_id(self) -> str:
        return "storage"

    @property
    def plugin_name(self) -> str:
        return "Storage Equivalencies"

    @property
    def plugin_icon(self) -> str:
        return "fa-solid fa-database"

    @property
    def plugin_description(self) -> str:
        return "Analyze and compare storage usage across different environments and targets."

    def get_data(self) -> Any:
        view = StorageInfoView()
        raw_data = view.load_data()
        
        candidates = raw_data.get("candidates", {}) if isinstance(raw_data, dict) else {}
        flattened_data = []
        metrics_map = {}
        group_counter = 1
        
        for dirname, paths_meta in candidates.items():
            if not isinstance(paths_meta, dict): continue
            for path, meta in paths_meta.items():
                if not isinstance(meta, dict): continue
                size, files, dirs = meta.get("size", 0), meta.get("files", 0), meta.get("dirs", 0)
                metrics = (size, files, dirs)
                if metrics not in metrics_map:
                    metrics_map[metrics] = f"Group {group_counter}"
                    group_counter += 1
                flattened_data.append({
                    "dirname": dirname, "path": path, "size": size, 
                    "files": files, "dirs": dirs, 
                    "group": metrics_map[metrics] if size >= 0 else "Unique"
                })
        
        return {
            "info": {
                "root": "User Home/Desktop", 
                "target": "cloudmesh-common"
            },
            "rows": flattened_data
        }

    def get_assets(self):
        return {
            "storage_table_config.js": "cloudmesh-ai-storage/src/cloudmesh/ai/command/storage_table_config.js",
            "storage_table_styles.css": "cloudmesh-ai-storage/src/cloudmesh/ai/command/storage_table_styles.css",
        }

class GitPlugin(PanelPlugin):
    @property
    def plugin_id(self) -> str:
        return "git"

    @property
    def plugin_name(self) -> str:
        return "Repository Statistics"

    @property
    def plugin_icon(self) -> str:
        return "fa-solid fa-code-branch"

    @property
    def plugin_description(self) -> str:
        return "Track and visualize statistics for your Git repositories across multiple users."

    def get_data(self) -> Any:
        print(f"[DEBUG] GitPlugin.get_data() called")
        config = UserConfig()
        users = config.get_users()
        print(f"[DEBUG] Configured users: {users}")
        
        if not users:
            print("[DEBUG] No users configured, returning error")
            return {"error": "no_users_configured"}

        all_user_data = {}
        for user in users:
            print(f"[DEBUG] Reading cached repos for user: {user}")
            # Use get_cached_repos directly to avoid any GitHub API calls (incremental enrichment)
            all_user_data[user] = config.get_cached_repos(user) or []
        
        print(f"[DEBUG] All cached data collected for users: {list(all_user_data.keys())}")
        flattened_data = []
        for user, repos in all_user_data.items():
            for repo in repos:
                repo_copy = repo.copy()
                repo_copy["user"] = user
                flattened_data.append(repo_copy)
        
        return flattened_data

    def get_assets(self):
        return {
            "git_table_config.js": "cloudmesh-ai-git/src/cloudmesh/ai/command/git_table_config.js",
            "git_table_styles.css": "cloudmesh-ai-git/src/cloudmesh/ai/command/git_table_styles.css",
        }

    def download_repo(self, repo_full_name: str):
        """Clones the specified repository using the Git plugin's UserConfig."""
        config = UserConfig()
        success, message = config.clone_repo(repo_full_name)
        return {"success": success, "message": message}

