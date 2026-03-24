"""
Extract key enum values defined in the Weaviate Python client for string mutation tests.
"""
import json
import sys
from pathlib import Path
from enum import Enum
from typing import Dict, List, Set, Any, Optional

# Import enum classes from the Weaviate client
import weaviate
from weaviate.collections.classes.config import (
    DataType, ConsistencyLevel, Tokenization, 
    GenerativeSearches, Rerankers, StopwordsPreset, 
    ReplicationDeletionStrategy, PQEncoderType, 
    PQEncoderDistribution, MultiVectorAggregation
)
from weaviate.collections.classes.config_vector_index import (
    VectorIndexType, VectorFilterStrategy
)
from weaviate.collections.classes.config_vectorizers import (
    Vectorizers, VectorDistances
)


def extract_enum_values(enum_class) -> List[str]:
    """Extract all string values from an enum class"""
    return [item.value for item in enum_class]


def create_weaviate_keywords_mapping() -> Dict[str, List[str]]:
    """Create a mapping from field type to valid values"""
    keyword_mapping = {}
    
    # Vector index types
    keyword_mapping["vector_index_types"] = extract_enum_values(VectorIndexType)
    
    # Distance metrics
    keyword_mapping["distance_metrics"] = extract_enum_values(VectorDistances)
    
    # Vectorizer modules
    keyword_mapping["vectorizers"] = extract_enum_values(Vectorizers)
    
    # Data types
    keyword_mapping["data_types"] = extract_enum_values(DataType)
    
    # Consistency levels
    keyword_mapping["consistency_levels"] = extract_enum_values(ConsistencyLevel)
    
    # Tokenization methods
    keyword_mapping["tokenization"] = extract_enum_values(Tokenization)
    
    # Generative search modules
    keyword_mapping["generative_searches"] = extract_enum_values(GenerativeSearches)
    
    # Reranker modules
    keyword_mapping["rerankers"] = extract_enum_values(Rerankers)
    
    # Stopwords presets
    keyword_mapping["stopwords_preset"] = extract_enum_values(StopwordsPreset)
    
    # Replication deletion strategies
    keyword_mapping["replication_deletion_strategy"] = extract_enum_values(ReplicationDeletionStrategy)
    
    # PQ encoder types
    keyword_mapping["pq_encoder_type"] = extract_enum_values(PQEncoderType)
    
    # PQ encoder distributions
    keyword_mapping["pq_encoder_distribution"] = extract_enum_values(PQEncoderDistribution)
    
    # Multi-vector aggregation
    keyword_mapping["multi_vector_aggregation"] = extract_enum_values(MultiVectorAggregation)
    
    # Vector filter strategies
    keyword_mapping["vector_filter_strategy"] = extract_enum_values(VectorFilterStrategy)
    
    return keyword_mapping


def create_field_path_mapping() -> Dict[str, str]:
    """Map field paths to expected enum types"""
    field_mapping = {
        "vectorIndexType": "vector_index_types",
        "distance": "distance_metrics",
        "vectorizer": "vectorizers",
        "dataType": "data_types",
        "consistency": "consistency_levels",
        "tokenization": "tokenization",
        "generative": "generative_searches",
        "reranker": "rerankers",
        "stopwordsPreset": "stopwords_preset",
        "deletionStrategy": "replication_deletion_strategy",
        "encoderType": "pq_encoder_type",
        "distribution": "pq_encoder_distribution",
        "aggregation": "multi_vector_aggregation",
        "filterStrategy": "vector_filter_strategy",
    }
    return field_mapping


def create_field_relationships() -> Dict[str, List[str]]:
    """Create dependency mappings between fields"""
    # Example: vectorizer type affects available model values
    relationships = {
        "vectorizers": {
            "text2vec-openai": ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
            "text2vec-cohere": ["embed-multilingual-v2.0", "embed-english-v2.0", "embed-multilingual-v3.0", "embed-english-v3.0"],
            "text2vec-huggingface": [],  # Too many models; handle separately
            "text2vec-jinaai": ["jina-embeddings-v2-base-en", "jina-embeddings-v2-small-en", "jina-embeddings-v3"],
            "text2vec-voyageai": ["voyage-3", "voyage-3-lite", "voyage-large-2", "voyage-2"],
        },
        "vector_index_types": {
            "hnsw": ["distance", "ef", "maxConnections", "dynamicEfMin", "dynamicEfMax", "vectorCacheMaxObjects"],
            "flat": ["distance"],
            "dynamic": ["distance", "threshold", "flat", "hnsw"],
        }
    }
    return relationships


def extract_keywords():
    """Extract all keywords and save them to a JSON file"""
    weaviate_keywords = create_weaviate_keywords_mapping()
    field_path_mapping = create_field_path_mapping()
    field_relationships = create_field_relationships()
    
    # Output to JSON file
    keywords_data = {
        "keyword_mapping": weaviate_keywords,
        "field_path_mapping": field_path_mapping,
        "field_relationships": field_relationships
    }
    
    output_path = Path(__file__).with_name("weaviate_keywords.json")
    with open(output_path, "w") as f:
        json.dump(keywords_data, f, indent=2)
    
    print(f"Extracted {sum(len(values) for values in weaviate_keywords.values())} keywords to weaviate_keywords.json")
    return keywords_data


if __name__ == "__main__":
    extract_keywords()
