import json
import os
from typing import List, Dict, Any, Optional

class ConversationManager:
    """
    Manages conversation history with on-disk persistence.
    Each entry is a dict: {"role": "user"|"assistant"|"system", "content": str}
    """

    def __init__(self, plugin_dir: str, max_messages: int = 20):
        self.plugin_dir = plugin_dir
        os.makedirs(self.plugin_dir, exist_ok=True)
        self.history_file = os.path.join(self.plugin_dir, "conversation_history.json")
        self.max_messages = int(max_messages) if max_messages is not None else 20
        self.messages: List[Dict[str, Any]] = []
        self.load()

    # ------------------------
    # Public API
    # ------------------------
    def append(self, role: str, content: str) -> None:
        """Append a message, trim the history to max_messages, then persist to disk."""
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
        self.save()

    def get_messages(self) -> List[Dict[str, Any]]:
        """Return the message list (by reference). Do not modify it directly."""
        return self.messages

    def clear(self) -> None:
        """Clear all messages and persist the empty state to disk."""
        self.messages = []
        self.save()

    # ------------------------
    # Persistence
    # ------------------------
    def save(self) -> None:
        """Persist the conversation history to disk as UTF-8 JSON."""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.messages, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ConversationManager] Failed to save: {e}")

    def load(self) -> None:
        """Load conversation history from disk and normalize it."""
        if not os.path.exists(self.history_file):
            self.messages = []
            return
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Normalize the loaded data — tolerate malformed entries.
            if isinstance(data, list):
                self.messages = self._normalize_messages(data)
            else:
                self.messages = []
        except Exception as e:
            print(f"[ConversationManager] Failed to load: {e}")
            self.messages = []

    # ------------------------
    # History windowing
    # ------------------------
    def get_last_turns_messages(self, n: Optional[int]) -> List[Dict[str, Any]]:
        """
        Return the messages corresponding to the last n conversation turns (user + assistant pairs).
        - A turn starts at each 'user' message and may be incomplete (user with no assistant reply).
        - n <= 0 or n is None returns [] (no history sent).
        - Only 'user' and 'assistant' roles are returned; 'system' messages are excluded.
        """
        if n is None:
            return []
        try:
            n = int(n)
        except Exception:
            n = 0
        if n <= 0:
            return []

        msgs = list(self.get_messages())  # [{role, content}, ...]
        # Walk backwards, grouping messages until a 'user' message closes a turn.
        turns: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []

        for m in reversed(msgs):
            current.append(m)
            if m.get("role") == "user":
                turns.append(list(reversed(current)))
                current = []
                if len(turns) >= n:
                    break

        # Include a dangling assistant message at the top (incomplete turn with no preceding user).
        if current:
            turns.append(list(reversed(current)))

        # Reverse back to chronological order and flatten.
        turns = list(reversed(turns))
        flat: List[Dict[str, Any]] = []
        for t in turns:
            flat.extend(t)

        # Strip 'system' messages — the API injects its own system prompt.
        flat = [m for m in flat if m.get("role") in ("user", "assistant")]
        return flat

    # ------------------------
    # Internal helpers
    # ------------------------
    def _normalize_messages(self, data: List[Any]) -> List[Dict[str, Any]]:
        """
        Sanitise the loaded message list:
        - keeps only dicts with valid 'role' and 'content' (str) fields
        - trims to max_messages if necessary
        """
        normalized: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if isinstance(role, str) and isinstance(content, str):
                normalized.append({"role": role, "content": content})
        if len(normalized) > self.max_messages:
            normalized = normalized[-self.max_messages:]
        return normalized
    
    def purge_on_disk(self):
        """Delete the on-disk history file if it exists."""
        try:
            if os.path.exists(self.history_file):
                os.remove(self.history_file)
        except Exception as e:
            print(f"[ConversationManager] Failed to purge history file: {e}")

