#!/usr/bin/python3
"""
Schema conversion utilities for various LLM clients.

This module provides a unified Schema dataclass that can be
converted to the appropriate format for different LLM clients:
- OpenAI
- Anthropic
- Google Gemini
- Ollama
"""

import copy
from typing import Dict, Any

from clients.types import Schema, SchemaProperty


def to_openai_schema(schema: Schema) -> Dict[str, Any]:
    """
    Convert Schema to OpenAI's schema format.
    
    OpenAI doesn't support the "optional" concept directly in its schema.
    Instead, it uses the "required" field at the schema level listing all required properties.
    """
    result = {
        "type": "object",
        "properties": {},
        "required": schema.all_properties(),
        "additionalProperties": False,
    }
    
    for name, prop in schema.properties.items():
        property_schema = {
            "type": prop.type,
        }
        
        if prop.description:
            property_schema["description"] = prop.description
        
        if prop.enum:
            property_schema["enum"] = prop.enum
            
        # Add minimum/maximum constraints for numeric types
        if prop.type in ["integer", "number"]:
            if prop.minimum is not None:
                property_schema["minimum"] = prop.minimum
            if prop.maximum is not None:
                property_schema["maximum"] = prop.maximum
        
        # Handle nested objects
        if prop.type == "object" and prop.object_schema:
            # Convert nested schema
            nested_schema = to_openai_schema(prop.object_schema)
            # Copy properties and required fields
            property_schema["properties"] = nested_schema["properties"]
            if "required" in nested_schema and nested_schema["required"]:
                property_schema["required"] = nested_schema["required"]
            property_schema["additionalProperties"] = nested_schema.get("additionalProperties", False)
        elif prop.type == "object" and prop.properties:
            # Handle inline object definition
            property_schema["properties"] = {}
            required_props = []
            
            for sub_name, sub_prop in prop.properties.items():
                sub_schema = {"type": sub_prop.type}
                
                if sub_prop.description:
                    sub_schema["description"] = sub_prop.description
                
                if sub_prop.enum:
                    sub_schema["enum"] = sub_prop.enum
                
                if sub_prop.type in ["integer", "number"]:
                    if sub_prop.minimum is not None:
                        sub_schema["minimum"] = sub_prop.minimum
                    if sub_prop.maximum is not None:
                        sub_schema["maximum"] = sub_prop.maximum
                
                if sub_prop.type == "array" and sub_prop.items:
                    sub_schema["items"] = sub_prop.items
                
                if sub_prop.required:
                    required_props.append(sub_name)
                
                property_schema["properties"][sub_name] = sub_schema
            
            if required_props:
                property_schema["required"] = required_props
            
            property_schema["additionalProperties"] = False
                
        # Handle array items
        elif prop.type == "array" and prop.array_items_schema:
            # Handle array of objects with a full schema
            property_schema["items"] = to_openai_schema(prop.array_items_schema)
        elif prop.type == "array" and prop.items:
            # Handle simple array items or array of objects with inline schema
            if isinstance(prop.items, dict) and prop.items.get("type") == "object":
                # Ensure additionalProperties is set for object schemas
                items_copy = copy.deepcopy(prop.items)
                if "additionalProperties" not in items_copy:
                    items_copy["additionalProperties"] = False
                # OpenAI requires all properties to be in the required array
                if "properties" in items_copy and "required" not in items_copy:
                    items_copy["required"] = list(items_copy["properties"].keys())
                elif "properties" in items_copy and "required" in items_copy:
                    # Ensure all properties are in required array for OpenAI
                    items_copy["required"] = list(items_copy["properties"].keys())
                property_schema["items"] = items_copy
            else:
                property_schema["items"] = prop.items
            
        result["properties"][name] = property_schema
    
    _recursive_clean_for_openai(result)
    return result


def to_anthropic_schema(schema: Schema) -> Dict[str, Any]:
    """
    Convert Schema to Anthropic's schema format.
    
    Anthropic's schema is similar to JSON Schema with a few differences.
    """
    result = {
        "type": "object",
        "properties": {},
        "required": schema.required_properties()
    }
    
    for name, prop in schema.properties.items():
        property_schema = {
            "type": prop.type,
        }
        
        if prop.description:
            property_schema["description"] = prop.description
        
        if prop.enum:
            property_schema["enum"] = prop.enum
            
        # Add minimum/maximum constraints for numeric types
        if prop.type in ["integer", "number"]:
            if prop.minimum is not None:
                property_schema["minimum"] = prop.minimum
            if prop.maximum is not None:
                property_schema["maximum"] = prop.maximum
        
        # Handle nested objects
        if prop.type == "object" and prop.object_schema:
            # Convert nested schema
            nested_schema = to_anthropic_schema(prop.object_schema)
            # Copy properties and required fields
            property_schema["properties"] = nested_schema["properties"]
            if "required" in nested_schema and nested_schema["required"]:
                property_schema["required"] = nested_schema["required"]
            property_schema["additionalProperties"] = nested_schema.get("additionalProperties", False)
        elif prop.type == "object" and prop.properties:
            # Handle inline object definition
            property_schema["properties"] = {}
            required_props = []
            
            for sub_name, sub_prop in prop.properties.items():
                sub_schema = {"type": sub_prop.type}
                
                if sub_prop.description:
                    sub_schema["description"] = sub_prop.description
                
                if sub_prop.enum:
                    sub_schema["enum"] = sub_prop.enum
                
                if sub_prop.type in ["integer", "number"]:
                    if sub_prop.minimum is not None:
                        sub_schema["minimum"] = sub_prop.minimum
                    if sub_prop.maximum is not None:
                        sub_schema["maximum"] = sub_prop.maximum
                
                if sub_prop.type == "array" and sub_prop.items:
                    sub_schema["items"] = sub_prop.items
                
                if sub_prop.required:
                    required_props.append(sub_name)
                
                property_schema["properties"][sub_name] = sub_schema
            
            if required_props:
                property_schema["required"] = required_props
            
            property_schema["additionalProperties"] = False
                
        # Handle array items
        elif prop.type == "array" and prop.array_items_schema:
            # Handle array of objects with a full schema
            property_schema["items"] = to_anthropic_schema(prop.array_items_schema)
        elif prop.type == "array" and prop.items:
            # Handle simple array items or array of objects with inline schema
            property_schema["items"] = prop.items
            
        # Add default value if specified
        if prop.default is not None:
            property_schema["default"] = prop.default
            
        result["properties"][name] = property_schema
    
    return result


def to_gemini_schema(schema: Schema) -> Dict[str, Any]:
    """
    Convert Schema to Google Gemini's schema format.
    
    Gemini uses a slightly different approach where the schema is an items schema
    for an array with a single item, and requires propertyOrdering.
    """
    result = {
        "type": "object",
        "properties": {},
        "required": schema.required_properties(),
    }
    
    for name, prop in schema.properties.items():
        property_schema = {
            "type": prop.type,
        }
        
        if prop.description:
            property_schema["description"] = prop.description
        
        if prop.enum:
            property_schema["enum"] = prop.enum
            
        # Add minimum/maximum constraints for numeric types
        if prop.type in ["integer", "number"]:
            if prop.minimum is not None:
                property_schema["minimum"] = prop.minimum
            if prop.maximum is not None:
                property_schema["maximum"] = prop.maximum
        
        # Handle nested objects
        if prop.type == "object" and prop.object_schema:
            # Convert nested schema
            nested_schema = to_gemini_schema(prop.object_schema)
            # Copy properties and required fields
            property_schema["properties"] = nested_schema["properties"]
            if "required" in nested_schema and nested_schema["required"]:
                property_schema["required"] = nested_schema["required"]
            property_schema["additionalProperties"] = nested_schema.get("additionalProperties", False)
            if "propertyOrdering" in nested_schema:
                property_schema["propertyOrdering"] = nested_schema["propertyOrdering"]
        elif prop.type == "object" and prop.properties:
            # Handle inline object definition
            property_schema["properties"] = {}
            required_props = []
            sub_property_names = []
            
            for sub_name, sub_prop in prop.properties.items():
                sub_schema = {"type": sub_prop.type}
                sub_property_names.append(sub_name)
                
                if sub_prop.description:
                    sub_schema["description"] = sub_prop.description
                
                if sub_prop.enum:
                    sub_schema["enum"] = sub_prop.enum
                
                if sub_prop.type in ["integer", "number"]:
                    if sub_prop.minimum is not None:
                        sub_schema["minimum"] = sub_prop.minimum
                    if sub_prop.maximum is not None:
                        sub_schema["maximum"] = sub_prop.maximum
                
                if sub_prop.type == "array" and sub_prop.items:
                    sub_schema["items"] = sub_prop.items
                
                if sub_prop.required:
                    required_props.append(sub_name)
                
                property_schema["properties"][sub_name] = sub_schema
            
            if required_props:
                property_schema["required"] = required_props
            
            # Include propertyOrdering for nested objects too
            property_schema["propertyOrdering"] = sub_property_names
            property_schema["additionalProperties"] = prop.additional_properties
                
        # Handle array items
        elif prop.type == "array" and prop.array_items_schema:
            # Handle array of objects with a full schema
            property_schema["items"] = to_gemini_schema(prop.array_items_schema)
        elif prop.type == "array" and prop.items:
            # Handle simple array items or array of objects with inline schema
            property_schema["items"] = prop.items
            
        # Add default value if specified
        if prop.default is not None:
            property_schema["default"] = prop.default
            
        result["properties"][name] = property_schema
    
    # Add propertyOrdering required by Gemini
    result["propertyOrdering"] = list(schema.properties.keys())
    
    return result


def to_ollama_schema(schema: Schema) -> Dict[str, Any]:
    """
    Convert Schema to Ollama's schema format.
    
    Ollama follows standard JSON Schema conventions.
    """
    result = {
        "type": "object",
        "properties": {},
        "required": schema.required_properties(),
        "additionalProperties": False,
    }
    
    for name, prop in schema.properties.items():
        property_schema = {
            "type": prop.type,
        }
        
        if prop.description:
            property_schema["description"] = prop.description
        
        if prop.enum:
            property_schema["enum"] = prop.enum
            
        # Add minimum/maximum constraints for numeric types
        if prop.type in ["integer", "number"]:
            if prop.minimum is not None:
                property_schema["minimum"] = prop.minimum
            if prop.maximum is not None:
                property_schema["maximum"] = prop.maximum
        
        # Handle nested objects
        if prop.type == "object" and prop.object_schema:
            # Convert nested schema
            nested_schema = to_ollama_schema(prop.object_schema)
            # Copy properties and required fields
            property_schema["properties"] = nested_schema["properties"]
            if "required" in nested_schema and nested_schema["required"]:
                property_schema["required"] = nested_schema["required"]
            property_schema["additionalProperties"] = nested_schema.get("additionalProperties", False)
        elif prop.type == "object" and prop.properties:
            # Handle inline object definition
            property_schema["properties"] = {}
            required_props = []
            
            for sub_name, sub_prop in prop.properties.items():
                sub_schema = {"type": sub_prop.type}
                
                if sub_prop.description:
                    sub_schema["description"] = sub_prop.description
                
                if sub_prop.enum:
                    sub_schema["enum"] = sub_prop.enum
                
                if sub_prop.type in ["integer", "number"]:
                    if sub_prop.minimum is not None:
                        sub_schema["minimum"] = sub_prop.minimum
                    if sub_prop.maximum is not None:
                        sub_schema["maximum"] = sub_prop.maximum
                
                if sub_prop.type == "array" and sub_prop.items:
                    sub_schema["items"] = sub_prop.items
                
                if sub_prop.required:
                    required_props.append(sub_name)
                
                property_schema["properties"][sub_name] = sub_schema
            
            if required_props:
                property_schema["required"] = required_props
            
            property_schema["additionalProperties"] = prop.additional_properties
                
        # Handle array items
        elif prop.type == "array" and prop.array_items_schema:
            # Handle array of objects with a full schema
            property_schema["items"] = to_ollama_schema(prop.array_items_schema)
        elif prop.type == "array" and prop.items:
            # Handle simple array items or array of objects with inline schema
            property_schema["items"] = prop.items
            
        # Add default value if specified
        if prop.default is not None:
            property_schema["default"] = prop.default
            
        result["properties"][name] = property_schema
    
    return result


def _recursive_clean_for_openai(schema_part: Dict[str, Any]) -> None:
    """
    Recursively clean a schema dict for OpenAI, removing properties that cause issues.
    
    Args:
        schema_part: A schema or part of a schema to clean
    """
    if not isinstance(schema_part, dict):
        return
    
    # Remove minimum/maximum from the current level
    schema_part.pop("minimum", None)
    schema_part.pop("maximum", None)
    
    # Process properties if they exist
    if "properties" in schema_part and isinstance(schema_part["properties"], dict):
        for prop in schema_part["properties"].values():
            if isinstance(prop, dict):
                _recursive_clean_for_openai(prop)
    
    # Process nested items for arrays
    if "items" in schema_part and isinstance(schema_part["items"], dict):
        _recursive_clean_for_openai(schema_part["items"])
        
    # Check for nested 'items' with 'properties' (array of objects)
    if "items" in schema_part and isinstance(schema_part["items"], dict) and "properties" in schema_part["items"]:
        for prop in schema_part["items"]["properties"].values():
            if isinstance(prop, dict):
                _recursive_clean_for_openai(prop)


def schema_from_dict(schema_dict: Dict[str, Any]) -> Schema:
    """
    Convert a standard JSON schema dictionary to a Schema object.
    
    This is useful for converting existing schema dictionaries to our unified format.
    
    Args:
        schema_dict: A JSON schema dictionary
        
    Returns:
        Schema object
    """
    # Extract basic properties
    name = schema_dict.get("title", schema_dict.get("name", "Schema"))
    description = schema_dict.get("description", "")
    additional_properties = schema_dict.get("additionalProperties", False)
    
    # Extract property definitions
    properties = {}
    required_props = schema_dict.get("required", [])
    
    if "properties" in schema_dict:
        for prop_name, prop_def in schema_dict["properties"].items():
            # Is property required?
            is_required = prop_name in required_props
            
            # Basic property attributes
            prop_type = prop_def.get("type", "string")
            prop_desc = prop_def.get("description", "")
            
            # Create property object
            prop = SchemaProperty(
                type=prop_type,
                description=prop_desc,
                required=is_required
            )
            
            # Handle constraints for numeric types
            if prop_type in ["integer", "number"]:
                prop.minimum = prop_def.get("minimum")
                prop.maximum = prop_def.get("maximum")
            
            # Handle enum values
            if "enum" in prop_def:
                prop.enum = prop_def["enum"]
            
            # Handle default values
            if "default" in prop_def:
                prop.default = prop_def["default"]
            
            # Handle nested objects
            if prop_type == "object" and "properties" in prop_def:
                # Create a sub-schema for nested object
                sub_schema_dict = {
                    "title": f"{prop_name}Object",
                    "description": prop_desc,
                    "properties": prop_def["properties"],
                    "required": prop_def.get("required", []),
                    "additionalProperties": prop_def.get("additionalProperties", False)
                }
                
                prop.object_schema = schema_from_dict(sub_schema_dict)
                prop.additional_properties = prop_def.get("additionalProperties", False)
            
            # Handle array items
            if prop_type == "array" and "items" in prop_def:
                items = prop_def["items"]
                
                # If items is an object schema
                if isinstance(items, dict):
                    if items.get("type") == "object" and "properties" in items:
                        # Create a schema for array items
                        items_schema_dict = {
                            "title": f"{prop_name}Item",
                            "description": items.get("description", "Array item"),
                            "properties": items["properties"],
                            "required": items.get("required", []),
                            "additionalProperties": items.get("additionalProperties", False)
                        }
                        
                        prop.array_items_schema = schema_from_dict(items_schema_dict)
                    else:
                        # For simple items or non-object schemas
                        prop.items = items
                else:
                    # Handle non-dict items (should be rare)
                    prop.items = {"type": "string"}
            
            properties[prop_name] = prop
    
    return Schema(
        name=name,
        description=description,
        properties=properties
    )