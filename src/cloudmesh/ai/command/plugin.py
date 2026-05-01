from abc import ABC, abstractmethod
from typing import Any, Dict, List

class PanelPlugin(ABC):
    """
    Base class for all AI Panel plugins.
    Components that want to be integrated into the AI Panel must implement this interface.
    """

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """The unique identifier for the plugin (e.g., 'git', 'storage')."""
        pass

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """The human-readable name of the plugin."""
        pass

    @property
    @abstractmethod
    def plugin_icon(self) -> str:
        """The FontAwesome icon class for the plugin (e.g., 'fa-solid fa-database')."""
        pass

    @property
    @abstractmethod
    def plugin_description(self) -> str:
        """A short description of what the plugin does."""
        pass

    @abstractmethod
    def get_data(self) -> Any:
        """
        Returns the data to be displayed in the panel.
        Should return a JSON-serializable object (dict or list).
        """
        pass

    def get_assets(self) -> Dict[str, str]:
        """
        Returns a mapping of asset filenames to their relative paths.
        Default implementation returns an empty dict.
        """
        return {}