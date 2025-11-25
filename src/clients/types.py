from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union

from telemetry import LLMUsage


@dataclass
class SchemaProperty:
    """A property in a JSON schema.

    To define nested schemas:
    1. For nested objects:
        Use `object_schema` to define a nested Schema object.
        Example:
        ```python
        nested_schema = Schema(
            "Address",
            "A user's address",
            {
                "street": SchemaProperty("string", "Street address"),
                "city": SchemaProperty("string", "City name"),
                "postal_code": SchemaProperty("string", "Postal code")
            }
        )
        
        user_schema = Schema(
            "User",
            "A user profile",
            {
                "name": SchemaProperty("string", "User name"),
                "address": SchemaProperty(
                    "object",
                    "User's address",
                    object_schema=nested_schema
                )
            }
        )
        ```

    2. For arrays of objects:
        Use `array_items_schema` to define the schema for array items.
        Example:
        ```python
        phone_schema = Schema(
            "Phone",
            "A phone number with type",
            {
                "type": SchemaProperty("string", "Phone type"),
                "number": SchemaProperty("string", "Phone number")
            }
        )
        
        user_schema = Schema(
            "User",
            "A user profile",
            {
                "name": SchemaProperty("string", "User name"),
                "phones": SchemaProperty(
                    "array",
                    "List of phone numbers",
                    array_items_schema=phone_schema
                )
            }
        )
        ```
    """
    type: str
    description: Optional[str] = None
    required: bool = True
    enum: Optional[List[Any]] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    default: Optional[Any] = None
    items: Optional[Dict[str, Any]] = None
    properties: Optional[Dict[str, "SchemaProperty"]] = None
    additional_properties: bool = False
    # For handling nested object schemas
    object_schema: Optional["Schema"] = None
    # For handling array of objects
    array_items_schema: Optional["Schema"] = None


@dataclass
class Schema:
    """
    A unified schema definition that can be converted to different LLM client formats.
    
    Usage:
    schema = Schema(
        "UserProfile",
        "A user profile object",
        {
            "name": SchemaProperty("string", "Full name of the user"),
            "age": SchemaProperty("integer", "Age in years", minimum=0, maximum=120),
            "interests": SchemaProperty("array", "List of interests", required=False,
                                       items={"type": "string"})
        }
    )
    """
    name: str
    description: str
    properties: Dict[str, SchemaProperty]
    
    def required_properties(self) -> List[str]:
        """Get list of required property names."""
        return [name for name, prop in self.properties.items() if prop.required]
    def all_properties(self) -> List[str]:
        """Get list of all property names."""
        return list(self.properties.keys())


@dataclass
class Response:
    """Container for response data."""
    response_text: str
    structured_data: Dict[str, Any]
    usage: LLMUsage
    additional_thought: Optional[str] = None
