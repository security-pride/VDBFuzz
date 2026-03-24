"""
String mutation strategies tailored for the Qdrant vector database.

This module provides mutation methods for Qdrant-specific field types,
such as distance metrics, quantization methods, and compression ratios.
"""
from typing import List, Dict, Optional, Union


# --------- Qdrant-specific mutation mappings ---------

# Distance metric types and their mutations
DISTANCE_METRICS = {
    "cosine": ["dot", "euclid", "manhattan"],
    "dot": ["cosine", "euclid", "manhattan"],
    "euclid": ["cosine", "dot", "manhattan"],
    "manhattan": ["cosine", "dot", "euclid"]
}

# Quantization methods and their mutations
QUANTIZATION_TYPES = {
    "scalar": ["product", "binary"],
    "product": ["scalar", "binary"],
    "binary": ["scalar", "product"]
}

# Compression ratio options
COMPRESSION_RATIOS = ["x1", "x2", "x4", "x8", "x16", "x32", "x64", "x128", "x256"]

# API operation types and their mutations
OPERATION_TYPES = {
    "search": ["recommend", "retrieve", "count"],
    "update": ["delete", "create", "upsert"],
    "upsert": ["insert", "replace", "update"]
}

# Field-path keywords mapped to field types
FIELD_TYPE_KEYWORDS = {
    "distance_metric": ["distance", "metric", "similarity"],
    "quantization": ["quantization", "quantize", "compression"],
    "operation": ["operation", "action", "method"],
    "collection_name": ["collection", "name", "namespace"],
    "limit": ["limit", "top", "size", "count", "threshold"],
    "vector": ["vector", "embedding", "point", "coordinates"]
}


# --------- Field type inference ---------

def infer_field_type(path_str: str, value: str) -> str:
    """
    Infer field type from the JSON path and value
    
    Args:
        path_str: field path in JSON
        value: field value
        
    Returns:
        str: inferred field type
    """
    path_lower = path_str.lower()
    value_lower = value.lower() if value else ""
    
    # Infer type based on path keywords
    for field_type, keywords in FIELD_TYPE_KEYWORDS.items():
        if any(kw in path_lower for kw in keywords):
            return field_type
    
    # Infer based on value format
    if value_lower in DISTANCE_METRICS:
        return "distance_metric"
    
    if value_lower in QUANTIZATION_TYPES:
        return "quantization"
    
    if value and value.startswith('x') and value[1:].isdigit():
        return "compression_ratio"
    
    # Default type
    return "generic_string"


# --------- Mutation methods for specific field types ---------

def mutate_distance_metric(value: str) -> List[str]:
    """
    Specialized mutation for distance metrics
    
    Args:
        value: original distance metric value
        
    Returns:
        list: mutated distance metric list
    """
    value_lower = value.lower()
    mutations = []
    
    # Add standard metric mutations
    if value_lower in DISTANCE_METRICS:
        mutations.extend(DISTANCE_METRICS[value_lower])
    
    # Add invalid values
    mutations.extend(["invalid_metric", "unknown", "none"])
    
    # Add case variants
    if value:
        mutations.append(value.upper())
        mutations.append(value.capitalize())
    
    return mutations


def mutate_quantization(value: str) -> List[str]:
    """
    Specialized mutation for quantization methods
    
    Args:
        value: original quantization value
        
    Returns:
        list: mutated quantization list
    """
    value_lower = value.lower()
    mutations = []
    
    # Add standard quantization mutations
    if value_lower in QUANTIZATION_TYPES:
        mutations.extend(QUANTIZATION_TYPES[value_lower])
    
    # Add invalid values
    mutations.extend(["invalid_quantization", "none", "auto"])
    
    # Add extra variants
    if value:
        mutations.append(f"{value}_quantization")
    
    return mutations


def mutate_compression_ratio(value: str) -> List[str]:
    """
    Specialized mutation for compression ratios
    
    Args:
        value: original compression ratio value
        
    Returns:
        list: mutated compression ratio list
    """
    # Recognize formats like x4, x8, etc.
    if value.startswith('x') and value[1:].isdigit():
        # Add reasonable compression ratio mutations
        mutations = [r for r in COMPRESSION_RATIOS if r != value]
        
        # Add boundary and invalid values
        edge_cases = ["x0", "x-1", "x1000000", "none"]
        
        return mutations + edge_cases
    
    return generic_string_mutations(value)


def mutate_operation(value: str) -> List[str]:
    """
    Specialized mutation for operation types
    
    Args:
        value: original operation type
        
    Returns:
        list: mutated operation type list
    """
    value_lower = value.lower()
    mutations = []
    
    # Add standard operation mutations
    if value_lower in OPERATION_TYPES:
        mutations.extend(OPERATION_TYPES[value_lower])
    
    # Add invalid values
    mutations.extend(["invalid_operation", "unknown"])
    
    # SQL injection style (only for specific operations)
    if "search" in value_lower:
        mutations.append("' OR 1=1 --")
    
    return mutations


def mutate_collection_name(value: str) -> List[str]:
    """
    Specialized mutation for collection names
    
    Args:
        value: original collection name
        
    Returns:
        list: mutated collection name list
    """
    mutations = [
        "nonexistent_collection",
        f"{value}_nonexistent",
        "",  # Empty collection name
        "SYSTEM_COLLECTION",  # Reserved system name
        "very_long_collection_name_" + "x" * 100  # Excessively long name
    ]
    
    # Add special characters
    if value:
        mutations.append(f"{value}$")
        mutations.append(f"{value}#")
        mutations.append(f"{value}/")
    
    return mutations


def generic_string_mutations(value: str) -> List[str]:
    """
    Generic string mutation strategy
    
    Args:
        value: original string value
        
    Returns:
        list: mutated string values
    """
    mutations = [
        "",  # empty string
        "null",  # null value
        "undefined",  # undefined
        "true",  # boolean
        "false",  # boolean
        "0",  # number
        "-1",  # negative number
        "999999"  # large number
    ]
    
    # For non-empty strings
    if value and len(value) > 0:
        # Add overly long string
        mutations.append("A" * 1000)
        
        # Add SQL injection tests
        mutations.append("' OR 1=1 --")
        
        # Add special characters
        mutations.append(f"{value}$")
        mutations.append(f"{value}#")
        
        # Add JSON injection
        mutations.append('{"key": "value"}')
    
    return mutations


# --------- Main mutation function ---------

def mutate_qdrant_string(value: str, keyword_type: str = None, field_path: List[str] = None) -> List[str]:
    """
    Smart string mutation strategy for Qdrant
    
    Args:
        value: original string value
        keyword_type: keyword type
        field_path: JSON path of the field
        
    Returns:
        list: mutated string values
    """
    if not value:
        return generic_string_mutations("")
    
    mutations = []
    path_str = '.'.join(map(str, field_path)) if field_path else ""
    value_lower = value.lower()
    
    # Infer a more precise field type based on the JSON path
    inferred_type = keyword_type or "generic_string"
    if field_path:
        inferred_type = infer_field_type(path_str, value)
    
    # Apply specialized mutation strategies by inferred field type
    if inferred_type == "distance_metric" or any(kw in path_str.lower() for kw in FIELD_TYPE_KEYWORDS["distance_metric"]):
        mutations = mutate_distance_metric(value)
    
    elif inferred_type == "quantization" or any(kw in path_str.lower() for kw in FIELD_TYPE_KEYWORDS["quantization"]):
        mutations = mutate_quantization(value)
    
    elif inferred_type == "compression_ratio" or (value.startswith('x') and value[1:].isdigit()):
        mutations = mutate_compression_ratio(value)
    
    elif inferred_type == "collection_name" or any(kw in path_str.lower() for kw in FIELD_TYPE_KEYWORDS["collection_name"]):
        mutations = mutate_collection_name(value)
    
    elif inferred_type == "operation" or any(kw in path_str.lower() for kw in FIELD_TYPE_KEYWORDS["operation"]):
        mutations = mutate_operation(value)
    
    # Default mutation strategy
    else:
        mutations = generic_string_mutations(value)
    
    # Remove original value and deduplicate
    mutations = list(set([m for m in mutations if m != value]))
    
    # Limit mutation count
    if len(mutations) > 10:
        return mutations[:10]
    
    return mutations
