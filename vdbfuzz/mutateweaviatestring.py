"""
String mutation strategies tailored for the Weaviate vector database.

This module provides mutation methods for Weaviate-specific field types,
using enum values extracted from the Weaviate client as valid mutation sets.
It offers specialized strategies for fields such as index types, distance
metrics, vectorizers, data types, and more.
"""
import json
import os
import random
from typing import List, Dict, Optional, Union, Any, Set, Tuple

# Load keywords extracted from the Weaviate client
def load_weaviate_keywords():
    """Load Weaviate keywords from JSON file"""
    keywords_file = os.path.join(os.path.dirname(__file__), 'weaviate_keywords.json')
    try:
        with open(keywords_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # If the file is missing or invalid, return safe defaults
        return {
            'keyword_mapping': {},
            'field_path_mapping': {},
            'field_relationships': {}
        }

# Keyword mappings
WEAVIATE_KEYWORDS = load_weaviate_keywords()
KEYWORD_MAPPING = WEAVIATE_KEYWORDS.get('keyword_mapping', {})
FIELD_PATH_MAPPING = WEAVIATE_KEYWORDS.get('field_path_mapping', {})
FIELD_RELATIONSHIPS = WEAVIATE_KEYWORDS.get('field_relationships', {})

# Field-path keywords mapped to field types (fallback if JSON load fails)
FIELD_TYPE_KEYWORDS = {
    "distance_metrics": ["distance", "metric", "similarity"],
    "vectorizers": ["vectorizer", "module", "vectorization"],
    "model": ["model", "embedding", "embedder"],
    "collection_name": ["collection", "class", "name"],
    "data_types": ["dataType", "type", "property"],
    "vector_index_types": ["vectorIndexType", "indexType", "index"],
}
VECTORIZERS = {
    "text2vec-openai": ["text2vec-cohere", "text2vec-huggingface", "text2vec-transformers", "text2vec-contextionary"],
    "text2vec-cohere": ["text2vec-openai", "text2vec-huggingface", "text2vec-transformers", "text2vec-contextionary"],
    "text2vec-huggingface": ["text2vec-openai", "text2vec-cohere", "text2vec-transformers", "text2vec-contextionary"],
    "text2vec-transformers": ["text2vec-openai", "text2vec-cohere", "text2vec-huggingface", "text2vec-contextionary"],
    "text2vec-contextionary": ["text2vec-openai", "text2vec-cohere", "text2vec-huggingface", "text2vec-transformers"],
    "img2vec-neural": ["multi2vec-clip", "multi2vec-bind"],
    "multi2vec-clip": ["img2vec-neural", "multi2vec-bind"],
    "multi2vec-bind": ["img2vec-neural", "multi2vec-clip"],
    "none": ["text2vec-openai", "text2vec-cohere", "img2vec-neural"]
}

# OpenAI models and their variants
OPENAI_MODELS = {
    "text-embedding-3-small": ["text-embedding-3-large", "text-embedding-ada-002"],
    "text-embedding-3-large": ["text-embedding-3-small", "text-embedding-ada-002"],
    "text-embedding-ada-002": ["text-embedding-3-small", "text-embedding-3-large"]
}

# Cohere models and their variants
COHERE_MODELS = {
    "embed-multilingual-v2.0": ["embed-english-v2.0", "embed-multilingual-v3.0", "embed-english-v3.0"],
    "embed-english-v2.0": ["embed-multilingual-v2.0", "embed-multilingual-v3.0", "embed-english-v3.0"],
    "embed-multilingual-v3.0": ["embed-english-v3.0", "embed-multilingual-v2.0", "embed-english-v2.0"],
    "embed-english-v3.0": ["embed-multilingual-v3.0", "embed-multilingual-v2.0", "embed-english-v2.0"]
}

# Voyage models and their variants
VOYAGE_MODELS = {
    "voyage-3": ["voyage-3-lite", "voyage-large-2", "voyage-2"],
    "voyage-3-lite": ["voyage-3", "voyage-large-2", "voyage-2"],
    "voyage-large-2": ["voyage-3", "voyage-3-lite", "voyage-2"],
    "voyage-2": ["voyage-3", "voyage-3-lite", "voyage-large-2"]
}

# Field-path keywords mapped to field types
FIELD_TYPE_KEYWORDS = {
    "distance_metrics": ["distance", "metric", "similarity"],
    "vectorizer": ["vectorizer", "module", "vectorization"],
    "model": ["model", "embedding", "embedder"],
    "collection_name": ["collection", "class", "name"],
    "field_name": ["field", "property", "attribute"],
    "limit": ["limit", "top", "size", "count", "threshold"],
    "vector": ["vector", "embedding", "point", "coordinates"]
}


# --------- Field type inference ---------

def string_similarity(s1: str, s2: str) -> float:
    """Compute similarity between two strings using a simplified Jaccard metric"""
    # Lowercase for comparison
    s1, s2 = s1.lower(), s2.lower()
    
    # If identical, return 1.0
    if s1 == s2:
        return 1.0
    
    # Build character sets
    set1 = set(s1)
    set2 = set(s2)
    
    # Jaccard similarity
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    
    # Boost if substring relation
    if s1 in s2 or s2 in s1:
        return 0.8
    
    # Return Jaccard similarity
    return intersection / union if union > 0 else 0.0

def substring_match(s1: str, s2: str) -> bool:
    """Check if s1 contains s2 or vice versa"""
    s1, s2 = s1.lower(), s2.lower()
    return s1 in s2 or s2 in s1

def find_most_similar_key(target: str, keys: List[str], threshold: float = 0.7) -> Optional[str]:
    """Find the most similar keyword to target within a list"""
    best_match = None
    best_similarity = 0.0
    
    for key in keys:
        # Prefer substring match
        if substring_match(target, key):
            similarity = 0.9  # High score for substring match
        else:
            similarity = string_similarity(target, key)
        
        if similarity > best_similarity:
            best_similarity = similarity
            best_match = key
    
    # Return only if above threshold
    return best_match if best_similarity >= threshold else None

def infer_field_type(path_str: str, value: str) -> str:
    """
    Infer field type from JSON path and value using string similarity
    
    Args:
        path_str: field path in JSON
        value: field value
        
    Returns:
        str: inferred field type
    """
    # Direct keyword field patterns
    key_field_patterns = {
        "vector_index_types": ["vectorindextype", "indextype", "vector_index"],
        "distance_metrics": ["distance", "metric", "similarity"],
        "vectorizers": ["vectorizer", "vector_model", "embedding_model"],
        "data_types": ["datatype", "type", "field_type"],
        "collection_name": ["class", "collection", "table_name"]
    }
    
    # Normalize path and value
    path_lower = path_str.lower()
    path_parts = path_lower.split('.')
    last_part = path_parts[-1] if path_parts else ""
    value_lower = value.lower() if value else ""
    
    # 1. Fuzzy match on special fields across path parts
    for field_type, patterns in key_field_patterns.items():
        for pattern in patterns:
            # Direct substring match
            if pattern in path_lower:
                # Skip distance metric if threshold appears
                if field_type == "distance_metrics" and "threshold" in path_lower:
                    continue
                return field_type
    
    # 2. Fuzzy match based on last path segment
    for field_type, patterns in key_field_patterns.items():
        most_similar = find_most_similar_key(last_part, patterns)
        if most_similar:
            return field_type
    
    # 3. Field-path mapping match
    for field_key, field_type in FIELD_PATH_MAPPING.items():
        if string_similarity(field_key.lower(), last_part) > 0.7:  # similarity threshold
            return field_type
    
    # 4. Fuzzy match based on value content
    for field_type, values in KEYWORD_MAPPING.items():
        # Exact match first
        if value_lower in [v.lower() for v in values]:
            return field_type
        
        # Similarity match
        for v in values:
            if string_similarity(value_lower, v.lower()) > 0.8:  # higher threshold
                return field_type
    
    # 5. Infer based on format hints
    if value_lower in ["true", "false"]:
        return "boolean"
    
    if value_lower.isdigit() or (value_lower.startswith("-") and value_lower[1:].isdigit()):
        return "int"
    
    # Default to generic string
    return "generic_string"


# --------- Mutation methods for specific field types ---------

def mutate_vector_index_type(value: str) -> List[str]:
    """
    Specialized mutation for vector index types
    
    Args:
        value: original index type value
        
    Returns:
        list: mutated index type list
    """
    value_lower = value.lower()
    mutations = []
    
    # Use values extracted from the Weaviate client
    valid_types = KEYWORD_MAPPING.get('vector_index_types', ["hnsw", "flat", "dynamic"])
    
    # Only add other valid index types; skip generic mutations
    for index_type in valid_types:
        if index_type != value_lower:
            mutations.append(index_type)
    
    # Add only a specific invalid value
    mutations.append("invalid-index")  # Keep one specific invalid value
    
    return mutations

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
    
    # Use values extracted from the Weaviate client
    valid_metrics = KEYWORD_MAPPING.get('distance_metrics', 
                                     ["cosine", "dot", "l2-squared", "hamming", "manhattan"])
    
    # Only add other valid metrics
    for metric in valid_metrics:
        if metric != value_lower:
            mutations.append(metric)
    
    # Add a single invalid value
    mutations.append("invalid-metric")  # Keep one specific invalid value
    
    return mutations


def mutate_vectorizer(value: str) -> List[str]:
    """
    Specialized mutation for vectorizer modules
    
    Args:
        value: original vectorizer value
        
    Returns:
        list: mutated vectorizer list
    """
    value_lower = value.lower()
    mutations = []
    
    # Use values extracted from the Weaviate client
    valid_vectorizers = KEYWORD_MAPPING.get('vectorizers', list(VECTORIZERS.keys()))
    
    # Add other valid vectorizers
    for vectorizer in valid_vectorizers:
        if vectorizer.lower() != value_lower:
            mutations.append(vectorizer)
    
    # Limit mutation count; sample 10 if too many
    if len(mutations) > 10:
        mutations = random.sample(mutations, 10)
    
    # Add invalid values
    mutations.extend(["none", "custom", "invalid-vectorizer"])
    
    # Add variants
    if value:
        mutations.append(f"invalid-{value}")
        mutations.append(f"{value}-custom")
    
    return mutations

def mutate_data_type(value: str) -> List[str]:
    """
    Specialized mutation for data types
    
    Args:
        value: original data type value
        
    Returns:
        list: mutated data type list
    """
    value_lower = value.lower()
    mutations = []
    
    # Use values extracted from the Weaviate client
    valid_types = KEYWORD_MAPPING.get('data_types', 
                                     ["text", "int", "boolean", "number", "date", "uuid", 
                                      "geoCoordinates", "blob", "phoneNumber", "object"])
    
    # Only use valid data types
    # Check if array type
    is_array = value_lower.endswith("[]")
    base_type = value_lower[:-2] if is_array else value_lower
    
    # Add only valid types from Weaviate
    valid_arrays = [t for t in valid_types if t.lower().endswith("[]")]
    valid_scalars = [t for t in valid_types if not t.lower().endswith("[]")]
    
    if is_array:
        # Add other array types
        for dt in valid_arrays:
            if dt.lower() != value_lower:
                mutations.append(dt)
        # Add scalar version
        if base_type.lower() in [t.lower() for t in valid_scalars]:
            mutations.append(base_type)
    else:
        # Add other scalar types
        for dt in valid_scalars:
            if dt.lower() != value_lower:
                mutations.append(dt)
        # Add array version
        array_type = value_lower + "[]"
        if array_type.lower() in [t.lower() for t in valid_arrays]:
            mutations.append(array_type)
    
    # Add a single invalid value
    mutations.append("invalid-type")
    
    return mutations


def mutate_model_name(value: str, vectorizer_type: Optional[str] = None) -> List[str]:
    """
    Specialized mutation for model names, with context-aware options based on vectorizer type
    
    Args:
        value: original model name
        vectorizer_type: vectorizer type for context-aware mutation
        
    Returns:
        list: mutated model name list
    """
    value_lower = value.lower()
    mutations = []
    
    # Use relationships between fields
    if vectorizer_type:
        vectorizer_lower = vectorizer_type.lower()
        # Check for associated model list
        for vec_type, models in FIELD_RELATIONSHIPS.get('vectorizers', {}).items():
            if vec_type.lower() in vectorizer_lower:
                # Add all other models for this vectorizer
                for model in models:
                    if model.lower() != value_lower:
                        mutations.append(model)
                break
    
    # If no matching vectorizer relationship found
    if not mutations:
        # Check if OpenAI model
        if "text-embedding" in value_lower or "ada" in value_lower:
            # OpenAI model mutations
            openai_models = ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"]
            for model in openai_models:
                if model.lower() != value_lower:
                    mutations.append(model)
        
        # Check if Cohere model
        elif "embed-" in value_lower:
            # Cohere model mutations
            cohere_models = ["embed-multilingual-v2.0", "embed-english-v2.0", 
                            "embed-multilingual-v3.0", "embed-english-v3.0"]
            for model in cohere_models:
                if model.lower() != value_lower:
                    mutations.append(model)
        
        # Check if Voyage model
        elif "voyage-" in value_lower:
            # Voyage model mutations
            voyage_models = ["voyage-3", "voyage-3-lite", "voyage-large-2", "voyage-2"]
            for model in voyage_models:
                if model.lower() != value_lower:
                    mutations.append(model)
    
    # Add version mutations
    if "-v" in value_lower:
        base, version = value_lower.split("-v", 1)
        try:
            version_num = float(version)
            mutations.append(f"{base}-v{version_num + 1}")
            if version_num > 1:
                mutations.append(f"{base}-v{version_num - 1}")
        except ValueError:
            pass
    
    # Add invalid values
    mutations.extend(["invalid-model", "nonexistent-model", ""])
    
    return mutations


def get_context_aware_mutations(value: str, field_type: str, field_path: List[str], 
                              json_content: Optional[Dict] = None) -> List[str]:
    """
    Context-aware mutation considering relationships between fields
    
    Args:
        value: original value
        field_type: field type
        field_path: field path
        json_content: full JSON content for context
        
    Returns:
        list: context-aware mutations
    """
    mutations = []
    
    # If JSON content and field path are available
    if json_content and field_path:
        # Extract relevant context
        # For example, when mutating a model field, try to find the associated vectorizer
        path_str = '.'.join(map(str, field_path))
        
        # Find vectorizer type (for model fields)
        if "model" in field_type.lower():
            # Look for a vectorizer in the same object
            try:
                # Build path to the parent object of current field
                parent_obj = json_content
                for i in range(len(field_path) - 1):
                    key = field_path[i]
                    if isinstance(parent_obj, dict) and key in parent_obj:
                        parent_obj = parent_obj[key]
                    else:
                        parent_obj = None
                        break
                
                # If parent object found, search for vectorizer field
                if parent_obj and isinstance(parent_obj, dict):
                    vectorizer = None
                    for key, val in parent_obj.items():
                        if "vectorizer" in key.lower():
                            vectorizer = val
                            break
                    
                    if vectorizer:
                        return mutate_model_name(value, vectorizer)
            except (KeyError, TypeError, IndexError):
                pass  # On error, fall back to non-context mutations
    
    # Default to empty list; caller will use non-context mutations
    return mutations


def mutate_collection_name(value: str) -> List[str]:
    """
    Specialized mutation for collection names
    
    Args:
        value: original collection name
        
    Returns:
        list: mutated collection name list
    """
    mutations = []
    
    # Weaviate class names follow specific naming rules; generate compliant mutations only
    
    # 1. Case variation (Weaviate commonly uses capitalized class names)
    if value:
        if value[0].isupper():  # Already capitalized
            mutations.append(value.lower())  # Try all lowercase
        else:
            mutations.append(value.capitalize())  # Try capitalizing
    
    # 2. Variations related to current value
    if value:
        # Add prefix/suffix
        mutations.append(f"Test{value}")
        mutations.append(f"{value}Class")
        
        # Pluralization variation (e.g., Product -> Products)
        if not value.endswith('s'):
            mutations.append(f"{value}s")
    
    # 3. Add a single invalid value to test non-existent class name
    mutations.append("NonExistentClass")
    
    return mutations


def generic_string_mutations(value: str) -> List[str]:
    """
    Generic string mutation strategy
    
    Args:
        value: original string value
        
    Returns:
        list: mutated string list
    """
    mutations = [
        "",  # Empty string
        "null",  # Null value
        "undefined",  # Undefined
        "true",  # Boolean
        "false",  # Boolean
        "0",  # Number
        "-1",  # Negative number
        "999999"  # Large number
    ]
    
    # For non-empty strings
    if value and len(value) > 0:
        # Add overly long string
        mutations.append("A" * 1000)
        
        # Add JSON injection
        mutations.append('{"key": "value"}')
    
    return mutations


# --------- Main mutation function ---------

def mutate_weaviate_string(value: str, keyword_type: str = None, field_path: List[str] = None,
                         json_content: Dict = None) -> List[str]:
    """
    Smart string mutation for Weaviate
    
    Args:
        value: original string value
        keyword_type: keyword type
        field_path: JSON path of the field
        json_content: full JSON content for context-aware mutations
        
    Returns:
        list: mutated string list
    """
    # Determine if path corresponds to a keyword field
    def is_key_field(path: str) -> Optional[str]:
        path_lower = path.lower()
        
        # Fuzzy detection
        # 1. vectorIndexType detection
        if any(kw in path_lower for kw in ["vectorindextype", "indextype", "vector_index", "vectorindex"]):
            return "vector_index_types"
        
        # 2. distance metrics detection
        if any(kw in path_lower for kw in ["distance", "metric", "similarity"]) and not any(kw in path_lower for kw in ["threshold", "config"]):
            return "distance_metrics"
        
        # 3. vectorizer detection
        if any(kw in path_lower for kw in ["vectorizer", "embedding_model", "embedding", "vector_model"]):
            return "vectorizers"
        
        # 4. dataType detection
        if any(kw in path_lower for kw in ["datatype", "data_type", "fieldtype", "type"]):
            return "data_types"
        
        # 5. class/collection detection
        if any(kw == path_lower or kw in path_lower.split('.') for kw in ["class", "collection", "table"]):
            return "collection_name"
        
        return None
    
    # First, enforce keyword-field detection
    field_type = None
    if field_path:
        path_str = '.'.join(map(str, field_path))
        field_type = is_key_field(path_str)
        
        # Direct handling for keyword fields
        if field_type == "vector_index_types":
            return mutate_vector_index_type(value)
        
        elif field_type == "distance_metrics":
            return mutate_distance_metric(value)
        
        elif field_type == "vectorizers":
            return mutate_vectorizer(value)
        
        elif field_type == "data_types":
            return mutate_data_type(value)
        
        elif field_type == "collection_name":
            return mutate_collection_name(value)
    
    # Empty input returns empty string
    if not value:
        return [""]
    
    mutations = []
    path_str = '.'.join(map(str, field_path)) if field_path else ""
    value_lower = value.lower()
    
    # Infer type from path when not forced
    inferred_type = field_type or keyword_type or "generic_string"
    if not field_type and field_path:
        inferred_type = infer_field_type(path_str, value)
    
    # Try context-aware mutations
    context_mutations = get_context_aware_mutations(value, inferred_type, field_path, json_content)
    if context_mutations:
        mutations.extend(context_mutations)
        return mutations  # Return immediately if context mutations succeed
    
    # Field-type-based mutations
    if inferred_type == "vector_index_types":
        mutations = mutate_vector_index_type(value)
    
    elif inferred_type == "distance_metrics":
        mutations = mutate_distance_metric(value)
    
    elif inferred_type == "vectorizers":
        mutations = mutate_vectorizer(value)
    
    elif inferred_type == "model":
        mutations = mutate_model_name(value)
    
    elif inferred_type == "data_types":
        mutations = mutate_data_type(value)
    
    elif inferred_type == "collection_name":
        mutations = mutate_collection_name(value)
    
    # Non-keyword fields use generic mutations
    else:
        mutations = generic_string_mutations(value)
    
    # If nothing generated, try enum values
    if not mutations and inferred_type in KEYWORD_MAPPING:
        for enum_value in KEYWORD_MAPPING[inferred_type]:
            if enum_value.lower() != value_lower:
                mutations.append(enum_value)
    
    # Still none: use generic mutations unless keyword field
    if not mutations and not field_type and not inferred_type in ["vector_index_types", "distance_metrics", "vectorizers", "data_types", "collection_name"]:
        mutations = generic_string_mutations(value)
    
    # Strict filtering for keyword fields
    if field_type or inferred_type in ["vector_index_types", "distance_metrics", "vectorizers", "data_types"]:
        # Filter meaningless mutations
        invalid_values = ["undefined", "null", "true", "false", "", "0", "-1", "999999"]
        mutations = [m for m in mutations if m not in invalid_values]
        
        # Ensure at least one valid mutation
        if not mutations and inferred_type in KEYWORD_MAPPING:
            # Force enum values
            for enum_value in KEYWORD_MAPPING[inferred_type]:
                if enum_value.lower() != value_lower:
                    mutations.append(enum_value)
                    break
    
    # Remove originals and deduplicate
    mutations = list(set([m for m in mutations if m != value]))
    
    # Limit mutation count
    if len(mutations) > 5:
        # Keep meaningful mutations
        if field_type and field_type in KEYWORD_MAPPING and KEYWORD_MAPPING[field_type]:
            # Prefer enum values for keyword fields
            enum_mutations = [m for m in mutations if m in KEYWORD_MAPPING[field_type]]
            if enum_mutations:
                # Take up to three enum values
                mutations = enum_mutations[:min(3, len(enum_mutations))]
                # Add one special mutation
                special_mutations = [m for m in mutations if m.startswith("invalid-")]
                if special_mutations:
                    mutations.append(special_mutations[0])
            else:
                # Random selection fallback
                mutations = random.sample(mutations, 5)
        else:
            # Random selection for non-keyword fields
            mutations = random.sample(mutations, 5)
    
    return mutations
