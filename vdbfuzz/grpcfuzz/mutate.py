"""
Mutation module for the gRPC fuzzer.

This module contains various mutation strategies for different data types encountered
in gRPC requests to Milvus. It provides specialized mutation functions for:
- Integers (with boundary value testing)
- Integer arrays
- Strings (with Milvus-specific keyword injection)
- Handling of floating-point arrays

The mutation strategies are designed to maximize test coverage while avoiding
unnecessary mutations that might not yield useful test cases.
"""

import random
import sys
import json
import numpy as np
from typing import Any, Dict, List, Tuple, Union, Optional

# Integer boundary values for different bit sizes
INT8_MIN, INT8_MAX = -128, 127
INT16_MIN, INT16_MAX = -32768, 32767
INT32_MIN, INT32_MAX = -2147483648, 2147483647
INT64_MIN, INT64_MAX = -9223372036854775808, 9223372036854775807

# Special integers for mutation
SPECIAL_INTEGERS = [
    0, 1, -1, 2, -2,  # Small values
    127, 128, 255, 256,  # Byte boundaries
    32767, 32768, 65535, 65536,  # 16-bit boundaries
    2147483647, 2147483648, 4294967295, 4294967296,  # 32-bit boundaries
    # The following may be problematic in some languages/systems
    9223372036854775807, -9223372036854775808  # 64-bit boundaries
]

# Milvus-specific keywords for string mutation
MILVUS_KEYWORDS = [
    # Collection and schema-related keywords
    "collection", "schema", "field", "index", "partition", "segment", 
    "vector", "scalar", "primary_key", "auto_id", "dimension",
    
    # Operation keywords
    "insert", "delete", "search", "query", "flush", "load", "release", "drop",
    
    # Data types
    "BOOL", "INT8", "INT16", "INT32", "INT64", "FLOAT", "DOUBLE", 
    "VARCHAR", "STRING", "ARRAY", "JSON", "BINARY_VECTOR", "FLOAT_VECTOR",
    "FLOAT16_VECTOR", "BFLOAT16_VECTOR", "SPARSE_FLOAT_VECTOR",
    
    # Index types
    "FLAT", "IVFLAT", "IVF_SQ8", "RNSG", "IVF_SQ8H", "IVF_PQ", "HNSW", "ANNOY",
    
    # Metric types
    "L2", "IP", "HAMMING", "JACCARD", "TANIMOTO", "SUBSTRUCTURE", "SUPERSTRUCTURE",
    
    # Special values and operators
    "null", "None", "$in", "$nin", "$gt", "$gte", "$lt", "$lte", "$eq", "$neq",
    
    # SQL-injection like patterns (to test input validation)
    "'; DROP TABLE", "1=1", "--", "/**/", "OR 1=1"
]

# Mutation probability settings
DEFAULT_MUTATION_PROBABILITY = 0.3
STRING_MUTATION_PROBABILITY = 0.3
ARRAY_MUTATION_PROBABILITY = 0.4

# Timestamp-related fields that should not be mutated
TIMESTAMP_FIELDS = [
    "timestamp", "create_time", "created_at", "updated_at", "update_time", 
    "start_time", "end_time", "expire_time", "time", "date", "datetime",
    "createTs", "updateTs", "last_modified", "timetravel", "lsn", "ts"
]


class Mutator:
    """Main mutation class that provides various mutation strategies."""
    
    def __init__(self, mutation_probability: float = DEFAULT_MUTATION_PROBABILITY, 
                 seed: Optional[int] = None):
        """
        Initialize the Mutator.
        
        Args:
            mutation_probability: Probability of mutating a value when encountered.
            seed: Random seed for reproducibility.
        """
        self.mutation_probability = mutation_probability
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
    
    def should_mutate(self, probability: Optional[float] = None) -> bool:
        """
        Determine if a mutation should occur based on probability.
        
        Args:
            probability: Optional override for the default mutation probability.
            
        Returns:
            True if mutation should be performed, False otherwise.
        """
        prob = probability if probability is not None else self.mutation_probability
        return random.random() < prob
    
    def mutate_value(self, value: Any, field_path: str = "") -> Any:
        """
        Mutate a value based on its type.
        
        Args:
            value: The value to mutate.
            field_path: Path to the field in the request structure (for context-specific mutations).
            
        Returns:
            Mutated value or original value if not mutated.
        """
        # Check if this is a timestamp-related field by examining the field path
        field_name = field_path.split('.')[-1].lower() if field_path else ""
        
        # Skip mutation for timestamp-related fields
        if any(ts_field in field_name for ts_field in TIMESTAMP_FIELDS):
            return value
            
        # Skip mutation if probability check fails
        if not self.should_mutate():
            return value
        
        # Determine type and select appropriate mutation strategy
        if isinstance(value, bool):
            return not value
        elif isinstance(value, int):
            return self.mutate_integer(value)
        elif isinstance(value, float):
            return self.mutate_float(value)
        elif isinstance(value, str):
            return self.mutate_string(value)
        elif isinstance(value, list) or isinstance(value, tuple):
            return self.mutate_array(value, field_path)
        elif isinstance(value, dict):
            return self.mutate_dict(value, field_path)
        else:
            # For unsupported types, return as is
            return value
    
    def mutate_integer(self, value: int) -> int:
        """
        Mutate an integer value, focusing on boundary values.
        
        Args:
            value: Original integer value.
            
        Returns:
            Mutated integer value.
        """
        strategy = random.randint(1, 5)
        
        if strategy == 1:
            # Use a special boundary value
            return random.choice(SPECIAL_INTEGERS)
        elif strategy == 2:
            # Bit flip (flip a random bit)
            bit_position = random.randint(0, 63)  # Up to 64 bits
            return value ^ (1 << bit_position)
        elif strategy == 3:
            # Off-by-one error simulation
            return value + random.choice([-1, 1])
        elif strategy == 4:
            # Scale up or down by a power of 10
            scale_factor = 10 ** random.randint(1, 6)
            return value * scale_factor
        else:
            # Negate the value
            return -value
    
    def mutate_float(self, value: float) -> float:
        """
        Mutate a floating-point value.
        
        Args:
            value: Original float value.
            
        Returns:
            Mutated float value.
        """
        strategy = random.randint(1, 6)
        
        if strategy == 1:
            # Special floating point values
            return random.choice([0.0, -0.0, float('inf'), float('-inf'), float('nan')])
        elif strategy == 2:
            # Small deviation
            return value * (1.0 + random.uniform(-0.1, 0.1))
        elif strategy == 3:
            # Larger deviation
            return value * random.uniform(0.5, 2.0)
        elif strategy == 4:
            # Negate
            return -value
        elif strategy == 5:
            # Cast to integer and back (precision loss)
            return float(int(value))
        else:
            # Extreme values
            return random.uniform(-1e12, 1e12)
    
    def mutate_string(self, value: str) -> str:
        """
        Mutate a string value, potentially injecting Milvus-specific keywords.
        
        Args:
            value: Original string value.
            
        Returns:
            Mutated string value.
        """
        strategy = random.randint(1, 7)
        
        if strategy == 1:
            # Empty string
            return ""
        elif strategy == 2:
            # Very long string
            return value * random.randint(10, 100)
        elif strategy == 3:
            # Inject a Milvus keyword
            keyword = random.choice(MILVUS_KEYWORDS)
            insert_pos = random.randint(0, len(value)) if value else 0
            return value[:insert_pos] + keyword + value[insert_pos:]
        elif strategy == 4:
            # Replace with a Milvus keyword
            return random.choice(MILVUS_KEYWORDS)
        elif strategy == 5:
            # Add special characters
            special_chars = "!@#$%^&*(){}[]<>?/\\|~`'\""
            insert_pos = random.randint(0, len(value)) if value else 0
            char = random.choice(special_chars)
            return value[:insert_pos] + char + value[insert_pos:]
        elif strategy == 6:
            # Unicode characters
            unicode_chars = [chr(random.randint(0x4E00, 0x9FFF)), chr(random.randint(0x0400, 0x04FF))]
            insert_pos = random.randint(0, len(value)) if value else 0
            char = random.choice(unicode_chars)
            return value[:insert_pos] + char + value[insert_pos:]
        else:
            # Reverse the string
            return value[::-1]
    
    def mutate_array(self, value: Union[List, Tuple], field_path: str = "") -> List:
        """
        Mutate an array, with special handling for numeric arrays.
        
        Args:
            value: Original array value.
            field_path: Path to the field (used to identify vector fields).
            
        Returns:
            Mutated array.
        """
        if not value:
            # For empty arrays, either return empty or add some elements
            if self.should_mutate(0.5):
                return []
            else:
                element_type = random.choice([int, float, str, bool])
                if element_type == int:
                    return [random.choice(SPECIAL_INTEGERS) for _ in range(random.randint(1, 5))]
                elif element_type == float:
                    return [random.uniform(-100, 100) for _ in range(random.randint(1, 5))]
                elif element_type == str:
                    return [random.choice(MILVUS_KEYWORDS) for _ in range(random.randint(1, 3))]
                else:  # bool
                    return [random.choice([True, False]) for _ in range(random.randint(1, 5))]
        
        # Convert to list to ensure mutability
        result = list(value)
        
        # Determine if this is likely a vector field
        is_vector = "vector" in field_path.lower() or (
            len(value) > 0 and all(isinstance(x, (int, float)) for x in value)
        )
        
        # Special handling for vectors (mostly dimension changes)
        if is_vector:
            strategy = random.randint(1, 4)
            
            if strategy == 1 and len(result) > 1:
                # Remove a random element
                result.pop(random.randint(0, len(result) - 1))
            elif strategy == 2:
                # Add a random element
                if all(isinstance(x, int) for x in result):
                    result.append(random.choice(SPECIAL_INTEGERS))
                else:  # float vectors
                    result.append(random.uniform(-1.0, 1.0))
            elif strategy == 3:
                # Completely change dimension
                new_dim = random.choice([2, 4, 8, 16, 32, 64, 128, 256, 512, 1024])
                if all(isinstance(x, int) for x in result):
                    result = [random.choice(SPECIAL_INTEGERS) for _ in range(new_dim)]
                else:  # float vectors
                    result = [random.uniform(-1.0, 1.0) for _ in range(new_dim)]
            else:
                # Scale all values in the vector
                scalar = random.uniform(0.1, 10.0)
                result = [x * scalar for x in result]
                
            return result
        
        # For non-vector arrays, apply different strategies
        strategy = random.randint(1, 5)
        
        if strategy == 1 and len(result) > 0:
            # Mutate a random element
            index = random.randint(0, len(result) - 1)
            result[index] = self.mutate_value(result[index], field_path + f"[{index}]")
        elif strategy == 2 and len(result) > 1:
            # Remove a random element
            result.pop(random.randint(0, len(result) - 1))
        elif strategy == 3:
            # Add a new element based on existing element types
            if len(result) > 0:
                new_val = self.mutate_value(result[0], field_path + "[0]")
                result.append(new_val)
            else:
                result.append(random.choice([0, 1.0, "new_element", True]))
        elif strategy == 4:
            # Reorder elements
            random.shuffle(result)
        else:
            # Duplicate a random element
            if len(result) > 0:
                index = random.randint(0, len(result) - 1)
                result.append(result[index])
        
        return result
    
    def mutate_dict(self, value: Dict, field_path: str = "") -> Dict:
        """
        Mutate a dictionary by modifying its key-value pairs.
        
        Args:
            value: Original dictionary.
            field_path: Path to the field.
            
        Returns:
            Mutated dictionary.
        """
        # Create a copy to avoid modifying the original
        result = value.copy()
        
        if not result:
            # For empty dictionaries, add some key-value pairs
            if self.should_mutate(0.5):
                num_pairs = random.randint(1, 3)
                for _ in range(num_pairs):
                    key = random.choice(MILVUS_KEYWORDS)
                    val_type = random.choice([int, float, str, bool])
                    if val_type == int:
                        result[key] = random.choice(SPECIAL_INTEGERS)
                    elif val_type == float:
                        result[key] = random.uniform(-100, 100)
                    elif val_type == str:
                        result[key] = random.choice(MILVUS_KEYWORDS)
                    else:  # bool
                        result[key] = random.choice([True, False])
            return result
        
        strategy = random.randint(1, 5)
        
        if strategy == 1:
            # Mutate a random value
            if result:
                key = random.choice(list(result.keys()))
                result[key] = self.mutate_value(result[key], field_path + "." + str(key))
        elif strategy == 2:
            # Add a new key-value pair
            new_key = random.choice(MILVUS_KEYWORDS)
            while new_key in result:
                new_key += "_" + str(random.randint(1, 100))
                
            val_type = random.choice([int, float, str, bool])
            if val_type == int:
                result[new_key] = random.choice(SPECIAL_INTEGERS)
            elif val_type == float:
                result[new_key] = random.uniform(-100, 100)
            elif val_type == str:
                result[new_key] = random.choice(MILVUS_KEYWORDS)
            else:  # bool
                result[new_key] = random.choice([True, False])
        elif strategy == 3 and len(result) > 1:
            # Remove a random key-value pair
            key = random.choice(list(result.keys()))
            del result[key]
        elif strategy == 4:
            # Modify a key name
            if result:
                old_key = random.choice(list(result.keys()))
                new_key = old_key + "_mutated"
                result[new_key] = result[old_key]
                del result[old_key]
        else:
            # No mutation for this strategy
            pass
        
        return result
    
    def mutate_field_values(self, request_dict: Dict, path: str = "") -> Dict:
        """
        Recursively mutate field values in a request dictionary.
        
        Args:
            request_dict: Dictionary representing a gRPC request.
            path: Current path in the dictionary (for nested structures).
            
        Returns:
            Mutated request dictionary.
        """
        result = {}
        
        for key, value in request_dict.items():
            current_path = f"{path}.{key}" if path else key
            
            if isinstance(value, dict):
                # Recursively mutate nested dictionaries
                result[key] = self.mutate_field_values(value, current_path)
            else:
                # Mutate the value directly
                result[key] = self.mutate_value(value, current_path)
        
        return result
    
    def mutate_request(self, request_obj) -> Dict:
        """
        Top-level function to mutate a gRPC request.
        
        Args:
            request_obj: Dictionary or protobuf message object representing a gRPC request.
            
        Returns:
            Mutated request dictionary.
        """
        # Check if we're dealing with a protobuf message object
        if hasattr(request_obj, 'DESCRIPTOR') and not isinstance(request_obj, dict):
            # Attempt to convert it to a dictionary if it's a protobuf message
            try:
                from google.protobuf import json_format
                request_dict = json_format.MessageToDict(
                    request_obj,
                    preserving_proto_field_name=True
                )
            except Exception as e:
                # Fallback to a simpler conversion if json_format fails
                request_dict = {}
                for field in request_obj.DESCRIPTOR.fields:
                    field_name = field.name
                    if hasattr(request_obj, field_name):
                        field_value = getattr(request_obj, field_name)
                        request_dict[field_name] = field_value
        else:
            # It's already a dictionary
            request_dict = request_obj
            
        # Handle case where request_dict might still not be a dictionary
        if not isinstance(request_dict, dict):
            # Create an empty dictionary as fallback
            request_dict = {}
            
        return self.mutate_field_values(request_dict)


# Utility functions for special cases

def generate_random_vector(dim: int, dtype: str = "float") -> List:
    """
    Generate a random vector of specified dimension and type.
    
    Args:
        dim: Dimension of the vector.
        dtype: Data type of the vector ("float" or "int").
        
    Returns:
        Random vector as a list.
    """
    if dtype == "float":
        return list(np.random.uniform(-1.0, 1.0, dim))
    else:  # int
        return list(np.random.randint(-100, 100, dim))


def mutate_protobuf_field(field_value: Any, field_name: str, field_type: str) -> Any:
    """
    Mutation function specifically designed for protobuf fields.
    
    Args:
        field_value: Original field value.
        field_name: Name of the field.
        field_type: Type of the field from protobuf definition.
        
    Returns:
        Mutated field value.
    """
    mutator = Mutator()
    
    # Handle different protobuf types
    if field_type == "int32" or field_type == "int64":
        return mutator.mutate_integer(field_value if field_value else 0)
    elif field_type == "float" or field_type == "double":
        return mutator.mutate_float(field_value if field_value else 0.0)
    elif field_type == "bool":
        return not field_value
    elif field_type == "string":
        return mutator.mutate_string(field_value if field_value else "")
    elif field_type == "bytes":
        # For bytes, convert to string, mutate, and convert back
        str_value = field_value.decode('utf-8', errors='replace') if field_value else ""
        mutated_str = mutator.mutate_string(str_value)
        return mutated_str.encode('utf-8')
    elif "repeated" in field_type:
        # Handle repeated fields (arrays)
        return mutator.mutate_array(field_value, field_name)
    else:
        # For complex/message types, just return as is
        return field_value
