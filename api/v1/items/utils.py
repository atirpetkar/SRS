import hashlib
from typing import Any


def canonical_text(item_type: str, payload: dict[str, Any]) -> str:
    """
    Extract canonical text from an item payload for content hashing and search indexing.
    
    Args:
        item_type: The type of item (flashcard, mcq, cloze, short_answer)
        payload: The item payload
        
    Returns:
        Canonical text representation of the item content
    """
    if item_type == "flashcard":
        parts = [payload.get("front", ""), payload.get("back", "")]
        
        # Add examples and hints if present
        if payload.get("examples"):
            parts.extend(payload["examples"])
        if payload.get("hints"):
            parts.extend(payload["hints"])
        if payload.get("pronunciation"):
            parts.append(payload["pronunciation"])
            
        return " ".join(parts).strip()
    
    elif item_type == "mcq":
        parts = [payload.get("stem", "")]
        
        # Add all option text
        if payload.get("options"):
            for option in payload["options"]:
                parts.append(option.get("text", ""))
                if option.get("rationale"):
                    parts.append(option["rationale"])
        
        return " ".join(parts).strip()
    
    elif item_type == "cloze":
        parts = [payload.get("text", "")]
        
        # Add all blank answers
        if payload.get("blanks"):
            for blank in payload["blanks"]:
                if blank.get("answers"):
                    parts.extend(blank["answers"])
                if blank.get("alt_answers"):
                    parts.extend(blank["alt_answers"])
        
        if payload.get("context_note"):
            parts.append(payload["context_note"])
            
        return " ".join(parts).strip()
    
    elif item_type == "short_answer":
        parts = [payload.get("prompt", "")]
        
        expected = payload.get("expected", {})
        if expected.get("value"):
            parts.append(expected["value"])
        if expected.get("unit"):
            parts.append(expected["unit"])
            
        if payload.get("acceptable_patterns"):
            parts.extend(payload["acceptable_patterns"])
            
        return " ".join(parts).strip()
    
    else:
        # Fallback: join all string values in the payload
        def extract_strings(obj):
            strings = []
            if isinstance(obj, str):
                strings.append(obj)
            elif isinstance(obj, dict):
                for value in obj.values():
                    strings.extend(extract_strings(value))
            elif isinstance(obj, list):
                for item in obj:
                    strings.extend(extract_strings(item))
            return strings
        
        return " ".join(extract_strings(payload)).strip()


def content_hash(item_type: str, payload: dict[str, Any]) -> str:
    """
    Generate a content hash for an item based on its canonical text.
    
    Args:
        item_type: The type of item
        payload: The item payload
        
    Returns:
        SHA-256 hash of the canonical text (lowercase, 64 characters)
    """
    canonical = canonical_text(item_type, payload)
    
    # Normalize the canonical text for consistent hashing
    normalized = canonical.lower().strip()
    
    # Create SHA-256 hash
    hasher = hashlib.sha256()
    hasher.update(normalized.encode('utf-8'))
    
    return hasher.hexdigest()


def normalize_tags(tags: list[str] | None) -> list[str]:
    """
    Normalize tags for consistent storage.
    
    Args:
        tags: List of tag strings
        
    Returns:
        Normalized list of unique, non-empty tags
    """
    if not tags:
        return []
    
    normalized = []
    seen = set()
    
    for tag in tags:
        if isinstance(tag, str):
            # Strip whitespace, lowercase, and remove empty tags
            clean_tag = tag.strip().lower()
            if clean_tag and clean_tag not in seen:
                normalized.append(clean_tag)
                seen.add(clean_tag)
    
    return sorted(normalized)  # Sort for consistency


def validate_difficulty(difficulty: str | None) -> str | None:
    """
    Validate difficulty level.
    
    Args:
        difficulty: Difficulty string
        
    Returns:
        Validated difficulty or None
        
    Raises:
        ValueError: If difficulty is invalid
    """
    if difficulty is None:
        return None
    
    valid_levels = {"intro", "core", "stretch"}
    
    if isinstance(difficulty, str):
        clean_difficulty = difficulty.strip().lower()
        if clean_difficulty in valid_levels:
            return clean_difficulty
    
    raise ValueError(f"Invalid difficulty level: {difficulty}. Must be one of {valid_levels}")