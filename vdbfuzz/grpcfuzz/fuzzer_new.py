"""
Milvus gRPC Fuzzer

This module implements a fuzzer for Milvus gRPC API, using captured request logs
to generate mutated requests and test for unexpected behavior.
"""

import json
import random
import time
import os
import grpc
from datetime import datetime
from pathlib import Path
import logging
from google.protobuf import text_format, json_format
from pymilvus.grpc_gen import milvus_pb2, milvus_pb2_grpc
from .mutate import Mutator

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GrpcFuzzer")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_BASE = PROJECT_ROOT / "output" / "milvus_grpc"

class MilvusFuzzer:
    """Fuzzing utility for MilvusService gRPC requests."""
    
    def __init__(self, server_addr="localhost:19530", log_file=None, output_dir=None, mutation_probability=0.3, seed=None):
        """
        Initialize the fuzzer
        
        Args:
            server_addr: Milvus server address
            log_file: Path to the log file containing recorded gRPC requests
            output_dir: Output directory used to save test results
            mutation_probability: Mutation probability (0.0-1.0)
            seed: Random seed used for reproducible testing
        """
        self.server_addr = server_addr
        self.channel = grpc.insecure_channel(server_addr)
        self.stub = milvus_pb2_grpc.MilvusServiceStub(self.channel)
        self.log_file = log_file
        self.requests_data = self._load_requests() if log_file else []
        self.crash_logs = []
        
        # Set the output directory
        timestamp = int(time.time())
        default_output_dir = DEFAULT_OUTPUT_BASE / f"fuzzing_results_{timestamp}"
        self.output_dir = str(output_dir or default_output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Initialize the mutator
        self.mutator = Mutator(mutation_probability=mutation_probability, seed=seed)
        
        # Record session information
        self.session_info = {
            "start_time": timestamp,
            "server_addr": server_addr,
            "log_file": log_file,
            "requests_count": len(self.requests_data) if self.requests_data else 0,
            "mutation_probability": mutation_probability,
            "seed": seed
        }
        
        logger.info(f"Initialize the fuzzer, target server: {server_addr}")
        if log_file:
            logger.info(f"Loaded {len(self.requests_data)} requests")
    
    def _load_requests(self):
        """Load request data from the aggregated log."""
        try:
            with open(self.log_file, 'r') as f:
                log_data = json.load(f)
            requests = log_data.get("requests", [])
            logger.info(f"Successfully loaded {self.log_file} from {len(requests)} requests")
            return requests
        except Exception as e:
            logger.error(f"Failed to load request data: {e}")
            return []
    
    def _fix_binary_data(self, request_str):
        """
        Fix binary-data formatting issues in text-format payloads
        
        Args:
            request_str: Request payload in text-format string form
            
        Returns:
            Fixed text-format string
        """
        import re
        
        # Match binary-data fields such as contents and data
        binary_pattern = re.compile(r'(contents|data):\s*"([^"\\]*(?:\\.[^"\\]*)*?)"', re.DOTALL)
        
        # Replace all matches in a single pass
        def safe_replace(match):
            field_name = match.group(1)
            content = match.group(2)
            
            # Check for non-printable or control characters
            has_binary = False
            for char in content:
                if ord(char) < 32 or ord(char) > 126:
                    has_binary = True
                    break
            
            if has_binary:
                # For binary data, replace the original content with a base64 marker
                encoded = f'{field_name}: "BASE64:"'
                return encoded
            else:
                # Leave regular strings unchanged
                return match.group(0)
                
        fixed_str = binary_pattern.sub(safe_replace, request_str)
        return fixed_str
    
    def _fix_json_text_format(self, request_str):
        """
        Fix JSON string formatting issues in text-format payloads
        
        Args:
            request_str: Request payload in text-format string form
            
        Returns:
            Fixed text-format string
        """
        import re
        
        # Match JSON fields
        json_field_pattern = re.compile(r'json_data\s*{([^}]*)}', re.DOTALL)
        data_line_pattern = re.compile(r'\s*data:\s*"({.*?})"')
        
        # Find all JSON field blocks
        for json_match in json_field_pattern.finditer(request_str):
            json_block = json_match.group(1)
            original_block = json_block
            
            # Fix the JSON string in each data line
            fixed_lines = []
            for line in json_block.splitlines():
                data_match = data_line_pattern.match(line)
                if data_match:
                    # Extract the JSON string content
                    json_str = data_match.group(1)
                    try:
                        # Try to parse the JSON
                        json_obj = json.loads(json_str.replace('\\"', '"'))
                        # Reformat it into valid protobuf text format
                        valid_json = json.dumps(json_obj).replace('"', '\\"')
                        fixed_line = line.replace(json_str, valid_json)
                        fixed_lines.append(fixed_line)
                    except json.JSONDecodeError:
                        # If the JSON cannot be parsed, replace it with a valid empty object
                        fixed_line = line.replace(json_str, '{}')
                        fixed_lines.append(fixed_line)
                else:
                    fixed_lines.append(line)
                    
            # Replace the original block with the fixed JSON block
            fixed_block = '\n'.join(fixed_lines)
            request_str = request_str.replace(original_block, fixed_block)
            
        return request_str

    def _parse_proto_message(self, method_name, request_str):
        """Parse a text-format request string into a proto message object."""
        try:
            # Get the corresponding request message type
            request_type = self._get_request_type(method_name)
            if not request_type:
                logger.warning(f"Could not find a request type for method {method_name} corresponding request type")
                return None
            
            # Fix JSON-formatting issues
            request_str = self._fix_json_text_format(request_str)
            
            # Fix binary-data formatting issues
            request_str = self._fix_binary_data(request_str)
            
            # Parse the text-format request
            request = request_type()
            text_format.Parse(request_str, request)
            return request
        except Exception as e:
            logger.error(f"Failed to parse request: {e}")
            logger.debug(f"Problematic request string: {request_str}")
            return None
    
    def _get_request_type(self, method_name):
        """Return the request message type for a given method name."""
        operation = method_name.split('/')[-1] if '/' in method_name else method_name
        
        # Map method names to the corresponding request message types
        method_mapping = {
            "Connect": milvus_pb2.ConnectRequest,
            "CreateCollection": milvus_pb2.CreateCollectionRequest,
            "DropCollection": milvus_pb2.DropCollectionRequest,
            "HasCollection": milvus_pb2.HasCollectionRequest,
            "LoadCollection": milvus_pb2.LoadCollectionRequest,
            "ReleaseCollection": milvus_pb2.ReleaseCollectionRequest,
            "DescribeCollection": milvus_pb2.DescribeCollectionRequest,
            "GetCollectionStatistics": milvus_pb2.GetCollectionStatisticsRequest,
            "ShowCollections": milvus_pb2.ShowCollectionsRequest,
            "CreatePartition": milvus_pb2.CreatePartitionRequest,
            "DropPartition": milvus_pb2.DropPartitionRequest,
            "HasPartition": milvus_pb2.HasPartitionRequest,
            "LoadPartitions": milvus_pb2.LoadPartitionsRequest,
            "ReleasePartitions": milvus_pb2.ReleasePartitionsRequest,
            "GetPartitionStatistics": milvus_pb2.GetPartitionStatisticsRequest,
            "ShowPartitions": milvus_pb2.ShowPartitionsRequest,
            "CreateIndex": milvus_pb2.CreateIndexRequest,
            "DescribeIndex": milvus_pb2.DescribeIndexRequest,
            "GetIndexState": milvus_pb2.GetIndexStateRequest,
            "DropIndex": milvus_pb2.DropIndexRequest,
            "Insert": milvus_pb2.InsertRequest,
            "Search": milvus_pb2.SearchRequest,
            "Flush": milvus_pb2.FlushRequest,
            "Query": milvus_pb2.QueryRequest,
            "Delete": milvus_pb2.DeleteRequest,
            "CreateAlias": milvus_pb2.CreateAliasRequest,
            "DropAlias": milvus_pb2.DropAliasRequest,
            "AlterAlias": milvus_pb2.AlterAliasRequest,
            "GetIndexBuildProgress": milvus_pb2.GetIndexBuildProgressRequest,
            "GetCollectionStatistics": milvus_pb2.GetCollectionStatisticsRequest,
            "GetPartitionStatistics": milvus_pb2.GetPartitionStatisticsRequest,
            "GetLoadingProgress": milvus_pb2.GetLoadingProgressRequest,
            "GetLoadState": milvus_pb2.GetLoadStateRequest,
            "GetFlushState": milvus_pb2.GetFlushStateRequest,
            "GetFlushAllState": milvus_pb2.GetFlushAllStateRequest,
            "FlushAll": milvus_pb2.FlushAllRequest,
            "GetPersistentSegmentInfo": milvus_pb2.GetPersistentSegmentInfoRequest,
            "GetQuerySegmentInfo": milvus_pb2.GetQuerySegmentInfoRequest,
            "HybridSearch": milvus_pb2.HybridSearchRequest,
            "CalcDistance": milvus_pb2.CalcDistanceRequest,
            "DescribeAlias": milvus_pb2.DescribeAliasRequest,
            "ListAliases": milvus_pb2.ListAliasesRequest,
            "Upsert": milvus_pb2.UpsertRequest,
            "ManualCompaction": milvus_pb2.ManualCompactionRequest,
            "GetCompactionState": milvus_pb2.GetCompactionStateRequest,
            # User management and privilege requests
            "CreateCredential": milvus_pb2.CreateCredentialRequest,
            "DeleteCredential": milvus_pb2.DeleteCredentialRequest,
            "ListCredUsers": milvus_pb2.ListCredUsersRequest,
            "CreateRole": milvus_pb2.CreateRoleRequest,
            "DropRole": milvus_pb2.DropRoleRequest,
            "OperateUserRole": milvus_pb2.OperateUserRoleRequest,
            "SelectRole": milvus_pb2.SelectRoleRequest,
            "SelectUser": milvus_pb2.SelectUserRequest,
            "OperatePrivilege": milvus_pb2.OperatePrivilegeRequest,
            "OperatePrivilegeV2": milvus_pb2.OperatePrivilegeV2Request,
            "SelectGrant": milvus_pb2.SelectGrantRequest,
            "CreatePrivilegeGroup": milvus_pb2.CreatePrivilegeGroupRequest,
            "DropPrivilegeGroup": milvus_pb2.DropPrivilegeGroupRequest,
            "OperatePrivilegeGroup": milvus_pb2.OperatePrivilegeGroupRequest,
            "ListPrivilegeGroups": milvus_pb2.ListPrivilegeGroupsRequest,
        }
        
        return method_mapping.get(operation)
    
    def mutate_request(self, request, mutation_level=1):
        """
        Mutate a request
        
        Args:
            request: Original request object
            mutation_level: Mutation level (1=light, 2=medium, 3=high)
        
        Returns:
            Mutated request object
        """
        # First convert the request to a dictionary
        request_dict = json_format.MessageToDict(
            request, 
            preserving_proto_field_name=True
        )

        # Get the method name
        method_name = request.__class__.__name__.replace("Request", "")
        
        # Log the request content before mutation
        logger.debug(f"[BEFORE MUTATION] {method_name} Request: {json.dumps(request_dict, indent=2, ensure_ascii=False)}")
        
        # Use a specialized mutator when available
        mutator = MutatorFactory.create_mutator(method_name, self.mutator)
        
        # Call mutate_request while keeping compatibility with the older mutate method
        if hasattr(mutator, 'mutate_request'):
            mutated_dict = mutator.mutate_request(request_dict)
        elif hasattr(mutator, 'mutate'):
            mutated_dict = mutator.mutate(request_dict)
        else:
            # Fall back to the base mutator if neither method exists
            mutated_dict = self.mutator.mutate_request(request_dict)
        
        # Validate and repair types
        mutated_dict = self._validate_and_fix_types(mutated_dict, method_name)
        
        # Log the request content after mutation
        logger.debug(f"[AFTER MUTATION] {method_name} Request: {json.dumps(mutated_dict, indent=2, ensure_ascii=False)}")
        
        try:
            # Convert the mutated dictionary back into a request object
            mutated_request = type(request)()
            json_format.ParseDict(mutated_dict, mutated_request)
            return mutated_request
        except Exception as e:
            logger.error(f"Error while converting the mutated dictionary back to a request object: {e}")
            
            # Log detailed error information and the dictionary content
            logger.error(f"Error details: {str(e)}")
            
            # Log the field that caused the error and its value type
            error_str = str(e)
            if 'field:' in error_str:
                field_name = error_str.split('field:')[1].split(' ')[0].strip()
                if field_name in mutated_dict:
                    value = mutated_dict[field_name]
                    logger.error(f"\u2192 Field {field_name} value: '{value}', type: {type(value).__name__}")
                    
                    # Try to repair the type issue one more time
                    if 'int' in error_str.lower() and isinstance(value, str):
                        try:
                            # Try converting the value to an integer
                            if value.strip() == '':
                                mutated_dict[field_name] = 0
                            else:
                                # If the value contains non-numeric characters, fall back to a default
                                mutated_dict[field_name] = 0
                            
                            # Retry the conversion
                            logger.info(f"Trying to repair field {field_name} as an integer: {mutated_dict[field_name]}")
                            mutated_request = type(request)()
                            json_format.ParseDict(mutated_dict, mutated_request)
                            return mutated_request
                        except Exception as e2:
                            logger.error(f"Error while trying to repair the type error: {e2}")
            
            return request  # Return the original request on error
    
    def send_request(self, method_name, request):
        """
        Send a gRPC request and handle the response
        
        Args:
            method_name: Method name
            request: Request object
            
        Returns:
            Response object or None on error
        """
        operation = method_name.split('/')[-1] if '/' in method_name else method_name
        logger.debug(f"Sending request: {operation}")
        
        try:
            # Dispatch to the corresponding gRPC method by name
            method = getattr(self.stub, operation, None)
            if not method:
                logger.warning(f"Method not found: {operation}")
                return None
                
            # Set the timeout
            response = method(request, timeout=10)
            return response
        except grpc.RpcError as e:
            self._log_crash({
                "timestamp": time.time(),
                "method": method_name,
                "error": f"gRPC error: {e.code()}, {e.details()}",
                "request": str(request)
            })
            logger.warning(f"gRPC error: {e.code()}, {e.details()}")
            return None
        except Exception as e:
            self._log_crash({
                "timestamp": time.time(),
                "method": method_name,
                "error": str(e),
                "request": str(request)
            })
            logger.warning(f"Request exception: {e}")
            return None
    
    def _validate_and_fix_types(self, data_dict, method_name=""):
        """
        Validate and repair type issues in the mutated dictionary
        
        Args:
            data_dict: Dictionary to validate and repair
            method_name: Request type name used for logging
            
        Returns:
            Repaired dictionary
        """
        if not isinstance(data_dict, dict):
            logger.warning(f"{method_name} is not a dictionary and cannot be validated or repaired")
            return data_dict
            
        # Timestamp-related fields should not be mutated
        timestamp_fields = [
            "timestamp", "create_time", "created_at", "updated_at", "update_time", 
            "start_time", "end_time", "expire_time", "time", "date", "datetime",
            "createTs", "updateTs", "last_modified", "timetravel", "lsn", "ts"
        ]
        
        # Integer fields that require validation
        integer_fields = [
            'guarantee_timestamp', 'nq', 'topk', 'round_decimal', 'radius', 'range', 
            'offset', 'limit', 'timeout_timestamp', 'search_timestamp'
        ]
        
        result = {}
        
        # Validate and repair field types
        for key, value in data_dict.items():
            # Skip mutation for timestamp-related fields and preserve the original value
            lower_key = key.lower()
            if any(ts_field in lower_key for ts_field in timestamp_fields):
                result[key] = value
                continue
                
            # Handle integer fields
            if key in integer_fields and isinstance(value, str):
                try:
                    # Try converting the value to an integer
                    result[key] = int(value)
                except ValueError:
                    # If conversion fails, assign a reasonable default value
                    logger.warning(f"Field {key} value '{value}' is not a valid integer; using a default value")
                    if key in ['nq', 'topk', 'limit']:
                        result[key] = 10
                    elif key == 'offset':
                        result[key] = 0
                    else:
                        result[key] = 0
                continue
                
            # Recursively handle nested dictionaries
            if isinstance(value, dict):
                result[key] = self._validate_and_fix_types(value, f"{method_name}.{key}")
                continue
                
            # Recursively handle dictionaries inside lists
            if isinstance(value, list):
                new_list = []
                for item in value:
                    if isinstance(item, dict):
                        new_list.append(self._validate_and_fix_types(item, f"{method_name}.{key}[]"))
                    else:
                        new_list.append(item)
                result[key] = new_list
                continue
                
            # Handle all other fields
            result[key] = value
            
        # Special handling for expr_template_values in Search requests
        if 'expr_template_values' in result and isinstance(result['expr_template_values'], list):
            for item in result['expr_template_values']:
                if isinstance(item, dict) and 'int64_val' in item:
                    if isinstance(item['int64_val'], str):
                        try:
                            item['int64_val'] = int(item['int64_val'])
                        except ValueError:
                            logger.warning(f"int64_val value in expr_template_values '{item['int64_val']}' is not a valid integer; using a default value 0")
                            item['int64_val'] = 0
        
        return result
    
    def _log_crash(self, crash_info):
        """Record crash information."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_id = f"crash_{timestamp}_{random.randint(1000, 9999)}"
        crash_info['id'] = crash_id
        
        # Append crash information to the in-memory list
        self.crash_logs.append(crash_info)
        
        # Write a dedicated crash log file
        crash_file = os.path.join(self.output_dir, f"{crash_id}.json")
        with open(crash_file, 'w') as f:
            json.dump(crash_info, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Recorded crash #{crash_id}: {crash_info['method']}")
    
    def run_fuzzing(self, iterations=100, mutation_levels=[1, 2, 3]):
        """
        Run fuzzing tests
        
        Args:
            iterations: Number of iterations
            mutation_levels: List of mutation levels
        """
        if not self.requests_data:
            logger.error("No request data is available for fuzzing")
            return
        
        logger.info(f"Starting fuzzing; planned iterations:{iterations} iterations...")
        start_time = time.time()
        
        from tqdm import tqdm
        for i in tqdm(range(iterations)):
            # Randomly select a request
            request_data = random.choice(self.requests_data)
            method_name = request_data["method"]
            request_str = request_data["request"].get("request_str", "")
            
            # Parse the request
            original_request = self._parse_proto_message(method_name, request_str)
            if not original_request:
                continue
            
            # Randomly choose a mutation level
            mutation_level = random.choice(mutation_levels)
            
            # Use specialized mutation for specific request types
            operation = method_name.split('/')[-1] if '/' in method_name else method_name
            
            # Use the factory to get a mutator suitable for this request type
            specialized_mutator = MutatorFactory.create_mutator(operation, self.mutator)
            
            # Use the specialized mutation strategy when available
            if hasattr(specialized_mutator, 'mutate') and specialized_mutator != self.mutator:
                mutated_dict = specialized_mutator.mutate(original_request)
            else:
                # Fall back to generic mutation
                mutated_dict = self.mutate_request(original_request, mutation_level)
            
            # Convert the mutated dictionary back into a protobuf message
            if isinstance(mutated_dict, dict):
                try:
                    mutated_request = type(original_request)()
                    from google.protobuf import json_format
                    json_format.ParseDict(mutated_dict, mutated_request)
                except Exception as e:
                    logger.warning(f"Failed to convert the dictionary back into a protobuf message: {e}")
                    # Use the original request if conversion fails
                    mutated_request = original_request
            else:
                # If the result is not a dictionary, ensure that it is a valid protobuf message object
                if hasattr(mutated_dict, 'DESCRIPTOR'):
                    mutated_request = mutated_dict
                else:
                    # If it is not a valid protobuf message object, use the original request
                    logger.warning(f"The mutator returned an invalid type: {type(mutated_dict)}")
                    mutated_request = original_request
            
            # Send the mutated request
            self.send_request(method_name, mutated_request)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        # Save the test report
        report = {
            "start_time": start_time,
            "end_time": end_time,
            "elapsed_time": elapsed_time,
            "iterations": iterations,
            "server_addr": self.server_addr,
            "log_file": self.log_file,
            "crash_count": len(self.crash_logs),
            "mutation_levels": mutation_levels
        }
        
        with open(os.path.join(self.output_dir, "fuzzing_report.json"), 'w') as f:
            json.dump(report, f, indent=2)
        
        # Save the aggregated crash log
        if self.crash_logs:
            with open(os.path.join(self.output_dir, "crash_logs.json"), 'w') as f:
                json.dump(self.crash_logs, f, indent=2)
            logger.info(f"Fuzzing completed; found {len(self.crash_logs)} potential issues, elapsed time: {elapsed_time:.2f}s")
        else:
            logger.info(f"Fuzzing completed; no issues found, elapsed time: {elapsed_time:.2f}s")
        
        return report


# Mutation factory for specific request types
class MutatorFactory:
    """
    Factory used to create an appropriate mutator based on request type
    """
    @staticmethod
    def create_mutator(request_type, base_mutator):
        """
        Create an appropriate mutator for a given request type
        
        Args:
            request_type: Request type or operation name
            base_mutator: Base mutator instance
            
        Returns:
            Mutator suitable for the given request type
        """
        if request_type == "CreateCollection":
            return CreateCollectionMutator(base_mutator)
        elif request_type == "Insert":
            return InsertMutator(base_mutator)
        elif request_type == "Search":
            return SearchMutator(base_mutator)
        elif request_type == "CreateIndex":
            return CreateIndexMutator(base_mutator)
        elif request_type == "GetLoadingProgress":
            return GetLoadingProgressMutator(base_mutator)
        elif request_type == "GetLoadState":
            return GetLoadStateMutator(base_mutator)
        elif request_type == "GetFlushState":
            return GetFlushStateMutator(base_mutator)
        elif request_type == "GetFlushAllState":
            return GetFlushAllStateMutator(base_mutator)
        elif request_type == "FlushAll":
            return FlushAllMutator(base_mutator)
        elif request_type == "GetPersistentSegmentInfo":
            return GetPersistentSegmentInfoMutator(base_mutator)
        elif request_type == "GetQuerySegmentInfo":
            return GetQuerySegmentInfoMutator(base_mutator)
        elif request_type == "HybridSearch":
            return HybridSearchMutator(base_mutator)
        elif request_type == "CalcDistance":
            return CalcDistanceMutator(base_mutator)
        elif request_type == "DescribeAlias":
            return DescribeAliasMutator(base_mutator)
        elif request_type == "ListAliases":
            return ListAliasesMutator(base_mutator)
        elif request_type == "Upsert":
            return UpsertMutator(base_mutator)
        elif request_type == "ManualCompaction":
            return ManualCompactionMutator(base_mutator)
        elif request_type == "GetCompactionState":
            return GetCompactionStateMutator(base_mutator)
        # User management and privilege-related requests
        elif request_type == "CreateCredential":
            return CreateCredentialMutator(base_mutator)
        elif request_type == "DeleteCredential":
            return DeleteCredentialMutator(base_mutator)
        elif request_type == "ListCredUsers":
            return ListCredUsersMutator(base_mutator)
        elif request_type == "CreateRole":
            return CreateRoleMutator(base_mutator)
        elif request_type == "DropRole":
            return DropRoleMutator(base_mutator)
        elif request_type == "OperateUserRole":
            return OperateUserRoleMutator(base_mutator)
        elif request_type == "SelectRole":
            return SelectRoleMutator(base_mutator)
        elif request_type == "SelectUser":
            return SelectUserMutator(base_mutator)
        elif request_type == "OperatePrivilege":
            return OperatePrivilegeMutator(base_mutator)
        elif request_type == "OperatePrivilegeV2":
            return OperatePrivilegeV2Mutator(base_mutator)
        elif request_type == "SelectGrant":
            return SelectGrantMutator(base_mutator)
        elif request_type == "CreatePrivilegeGroup":
            return CreatePrivilegeGroupMutator(base_mutator)
        elif request_type == "DropPrivilegeGroup":
            return DropPrivilegeGroupMutator(base_mutator)
        elif request_type == "OperatePrivilegeGroup":
            return OperatePrivilegeGroupMutator(base_mutator)
        elif request_type == "ListPrivilegeGroups":
            return ListPrivilegeGroupsMutator(base_mutator)
        else:
            # For request types without special handling, return the base mutator
            return base_mutator


# Specialized mutator for CreateCollection requests
class CreateCollectionMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate CreateCollection requests with special handling"""
        # Specialized mutation logic can be added here if needed
        # The base mutator is used here for now
        return self.base_mutator.mutate_request(request)


# Specialized mutator for Insert requests
class InsertMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate Insert requests with special handling"""
        # Specialized mutation logic can be added here if needed
        # The base mutator is used here for now
        return self.base_mutator.mutate_request(request)


# Specialized mutator for Search requests
class SearchMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate Search requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            # Handle the collection_name field
            if 'collection_name' not in mutated_request or not mutated_request['collection_name']:
                mutated_request['collection_name'] = "default_collection"
            
            # Validate the dsl_type enum field and ensure it has a valid value
            if 'dsl_type' in mutated_request:
                # Check whether the enum value is valid; if not, replace it with a valid value
                # Based on the test corpus, valid values should include entries such as BoolExprV1
                valid_dsl_types = ["Invalid", "BoolExprV1", "Expression"]
                
                if mutated_request['dsl_type'] not in valid_dsl_types:
                    # If the value is invalid, use a random valid enum value
                    mutated_request['dsl_type'] = random.choice(valid_dsl_types)
            
            # Validate numeric fields and ensure they contain valid integers
            numeric_fields = ['nq', 'topk', 'guarantee_timestamp']
            for field in numeric_fields:
                if field in mutated_request and isinstance(mutated_request[field], str):
                    try:
                        # Try converting the value to an integer
                        if mutated_request[field].strip() == '':
                            mutated_request[field] = 0
                        else:
                            # If the string is not a valid integer, use a default value
                            try:
                                int(mutated_request[field])
                            except ValueError:
                                if field == 'nq':
                                    mutated_request[field] = 1
                                elif field == 'topk':
                                    mutated_request[field] = 10
                                elif field == 'guarantee_timestamp':
                                    mutated_request[field] = 0
                    except Exception as e:
                        # Conversion failed; using a default value
                        if field == 'nq':
                            mutated_request[field] = 1
                        elif field == 'topk':
                            mutated_request[field] = 10
                        elif field == 'guarantee_timestamp':
                            mutated_request[field] = 0
            
            # Validate integer values in the expr_template_values field
            if 'expr_template_values' in mutated_request:
                for i, val in enumerate(mutated_request['expr_template_values']):
                    if 'int64_val' in val and isinstance(val['int64_val'], str):
                        if val['int64_val'].strip() == '':
                            val['int64_val'] = '0'  # Use the string '0' as a safe fallback value
                        elif not val['int64_val'].isdigit():
                            val['int64_val'] = '0'  # Use the string '0' as a safe fallback value
        
        return mutated_request


# Specialized mutator for CreateIndex requests
class CreateIndexMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate CreateIndex requests with special handling"""
        # Specialized mutation logic can be added here if needed
        # The base mutator is used here for now
        return self.base_mutator.mutate_request(request)


# Specialized mutator for GetLoadingProgress requests
class GetLoadingProgressMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate GetLoadingProgress requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure that the collection_name field exists and is non-empty
        if isinstance(mutated_request, dict) and ('collection_name' not in mutated_request or not mutated_request['collection_name']):
            mutated_request['collection_name'] = "default_collection"
            
        return mutated_request


# Specialized mutator for GetLoadState requests
class GetLoadStateMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate GetLoadState requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure that the collection_name field exists and is non-empty
        if isinstance(mutated_request, dict) and ('collection_name' not in mutated_request or not mutated_request['collection_name']):
            mutated_request['collection_name'] = "default_collection"
            
        return mutated_request


# Specialized mutator for GetFlushState requests
class GetFlushStateMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate GetFlushState requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict) and ('collection_name' not in mutated_request or not mutated_request['collection_name']):
            mutated_request['collection_name'] = "default_collection"
        
        if isinstance(mutated_request, dict) and ('flush_id' not in mutated_request or not mutated_request['flush_id']):
            mutated_request['flush_id'] = "flush_" + str(random.randint(1, 1000))
            
        return mutated_request


# Specialized mutator for GetFlushAllState requests
class GetFlushAllStateMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate GetFlushAllState requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict) and ('flush_all_id' not in mutated_request or not mutated_request['flush_all_id']):
            mutated_request['flush_all_id'] = "flush_all_" + str(random.randint(1, 1000))
            
        return mutated_request


# Specialized mutator for FlushAll requests
class FlushAllMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate FlushAll requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
            
        return mutated_request


# Specialized mutator for GetPersistentSegmentInfo requests
class GetPersistentSegmentInfoMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate GetPersistentSegmentInfo requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict) and ('collection_name' not in mutated_request or not mutated_request['collection_name']):
            mutated_request['collection_name'] = "default_collection"
            
        return mutated_request


# Specialized mutator for GetQuerySegmentInfo requests
class GetQuerySegmentInfoMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate GetQuerySegmentInfo requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict) and ('collection_name' not in mutated_request or not mutated_request['collection_name']):
            mutated_request['collection_name'] = "default_collection"
            
        return mutated_request


# Specialized mutator for HybridSearch requests
class HybridSearchMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate HybridSearch requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict) and ('collection_name' not in mutated_request or not mutated_request['collection_name']):
            mutated_request['collection_name'] = "default_collection"
        
        # Ensure that either vector data or a keyword query is present
        if isinstance(mutated_request, dict) and 'data' in mutated_request:
            if 'vectors' not in mutated_request['data'] and 'keyword' not in mutated_request['data']:
                mutated_request['data']['keyword'] = {}
                mutated_request['data']['keyword']['keyword_query'] = "test"
            
        return mutated_request


# Specialized mutator for CalcDistance requests
class CalcDistanceMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate CalcDistance requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            # Ensure that vector data for distance calculation is present
            if 'op_left' not in mutated_request or not mutated_request['op_left']:
                mutated_request['op_left'] = {
                    "float_vectors": [[random.random() for _ in range(4)] for _ in range(2)]
                }
                
            if 'op_right' not in mutated_request or not mutated_request['op_right']:
                mutated_request['op_right'] = {
                    "float_vectors": [[random.random() for _ in range(4)] for _ in range(2)]
                }
            
        return mutated_request


# Specialized mutator for DescribeAlias requests
class DescribeAliasMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate DescribeAlias requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict) and ('alias' not in mutated_request or not mutated_request['alias']):
            mutated_request['alias'] = "alias_" + str(random.randint(1, 1000))
            
        return mutated_request


# Specialized mutator for ListAliases requests
class ListAliasesMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate(self, request):
        """Mutate ListAliases requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict) and ('collection_name' not in mutated_request or not mutated_request['collection_name']):
            mutated_request['collection_name'] = "default_collection"
            
        return mutated_request


# Specialized mutator for Upsert requests
class UpsertMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate Upsert requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            # Handle the collection_name field
            if 'collection_name' not in mutated_request or not mutated_request['collection_name']:
                mutated_request['collection_name'] = "default_collection"
            
            # Handle data fields
            if 'data' not in mutated_request or not mutated_request['data']:
                # Create a minimal valid data structure
                mutated_request['data'] = {
                    'ids': {
                        'int_id': {'data': [random.randint(1, 1000) for _ in range(3)]}
                    },
                    'fields_data': [
                        {
                            'field_name': 'test_field',
                            'field': {
                                'scalars': {
                                    'data': ["test_value"]
                                }
                            }
                        }
                    ]
                }
                
        return mutated_request


# Specialized mutator for ManualCompaction requests
class ManualCompactionMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate ManualCompaction requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            # Handle the collection_name field
            if 'collection_name' not in mutated_request or not mutated_request['collection_name']:
                mutated_request['collection_name'] = "default_collection"
            
            # Normalize timestamp fields to valid integers
            if 'timetravel' in mutated_request:
                if not isinstance(mutated_request['timetravel'], int):
                    try:
                        mutated_request['timetravel'] = int(mutated_request['timetravel'])
                    except (ValueError, TypeError):
                        mutated_request['timetravel'] = 0
                        
        return mutated_request


# Specialized mutator for GetCompactionState requests
class GetCompactionStateMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate GetCompactionState requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            # Handle the compaction_id field
            if 'compaction_id' not in mutated_request or not mutated_request['compaction_id']:
                mutated_request['compaction_id'] = "compaction_" + str(random.randint(1, 1000))
                
        return mutated_request


# Specialized mutator for user-management and privilege-related requests

# Mutator for CreateCredential requests
class CreateCredentialMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate CreateCredential requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'username' not in mutated_request or not mutated_request['username']:
                mutated_request['username'] = f"user_{random.randint(1, 1000)}"
            
            if 'password' not in mutated_request or not mutated_request['password']:
                mutated_request['password'] = f"password_{random.randint(1, 1000)}"
                
        return mutated_request


# Mutator for DeleteCredential requests
class DeleteCredentialMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate DeleteCredential requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'username' not in mutated_request or not mutated_request['username']:
                mutated_request['username'] = f"user_{random.randint(1, 1000)}"
                
        return mutated_request


# Mutator for ListCredUsers requests
class ListCredUsersMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate ListCredUsers requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # This request usually does not need special handling because it has no required fields
        # Optional filtering flags can still be added
        if isinstance(mutated_request, dict):
            if 'include_user_info' not in mutated_request:
                mutated_request['include_user_info'] = random.choice([True, False])
                
        return mutated_request


# Mutator for CreateRole requests
class CreateRoleMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate CreateRole requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'role_name' not in mutated_request or not mutated_request['role_name']:
                mutated_request['role_name'] = f"role_{random.randint(1, 1000)}"
                
        return mutated_request


# Mutator for DropRole requests
class DropRoleMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate DropRole requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'role_name' not in mutated_request or not mutated_request['role_name']:
                mutated_request['role_name'] = f"role_{random.randint(1, 1000)}"
                
        return mutated_request


# Mutator for OperateUserRole requests
class OperateUserRoleMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate OperateUserRole requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'username' not in mutated_request or not mutated_request['username']:
                mutated_request['username'] = f"user_{random.randint(1, 1000)}"
                
            if 'role_name' not in mutated_request or not mutated_request['role_name']:
                mutated_request['role_name'] = f"role_{random.randint(1, 1000)}"
                
            # Ensure that the type field exists and is valid
            if 'type' not in mutated_request or not isinstance(mutated_request['type'], int):
                # Typically, type=1 grants a role and type=2 revokes a role
                mutated_request['type'] = random.choice([1, 2])
                
        return mutated_request


# Mutator for SelectRole requests
class SelectRoleMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate SelectRole requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'role_names' not in mutated_request or not mutated_request['role_names']:
                mutated_request['role_names'] = [f"role_{random.randint(1, 100)}" for _ in range(random.randint(1, 3))]
                
        return mutated_request


# Mutator for SelectUser requests
class SelectUserMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate SelectUser requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'usernames' not in mutated_request or not mutated_request['usernames']:
                mutated_request['usernames'] = [f"user_{random.randint(1, 100)}" for _ in range(random.randint(1, 3))]
                
        return mutated_request


# Mutator for OperatePrivilege requests
class OperatePrivilegeMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate OperatePrivilege requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'role_name' not in mutated_request or not mutated_request['role_name']:
                mutated_request['role_name'] = f"role_{random.randint(1, 1000)}"
                
            if 'object' not in mutated_request or not mutated_request['object'] or 'name' not in mutated_request['object']:
                mutated_request['object'] = {
                    'name': f"collection_{random.randint(1, 1000)}",
                    'object_type': random.randint(1, 5)  # Object type; 1 typically represents Collection
                }
                
            if 'object_name' not in mutated_request or not mutated_request['object_name']:
                mutated_request['object_name'] = f"object_{random.randint(1, 1000)}"
                
            if 'object_type' not in mutated_request or not isinstance(mutated_request['object_type'], int):
                mutated_request['object_type'] = random.randint(1, 5)
                
            if 'privilege_type' not in mutated_request or not isinstance(mutated_request['privilege_type'], int):
                mutated_request['privilege_type'] = random.randint(1, 10)  # Privilege type
                
            if 'grant_option' not in mutated_request:
                mutated_request['grant_option'] = random.choice([True, False])
                
        return mutated_request


# Mutator for OperatePrivilegeV2 requests
class OperatePrivilegeV2Mutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate OperatePrivilegeV2 requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'entities' not in mutated_request or not mutated_request['entities']:
                mutated_request['entities'] = [
                    {
                        'entity': {
                            'name': f"role_{random.randint(1, 1000)}",
                            'type': 1  # Typically, 1 means role
                        }
                    }
                ]
                
            if 'object' not in mutated_request or not mutated_request['object']:
                mutated_request['object'] = {
                    'name': f"collection_{random.randint(1, 1000)}",
                    'type': random.randint(1, 5)  # Object type
                }
                
            if 'action_type' not in mutated_request or not isinstance(mutated_request['action_type'], int):
                mutated_request['action_type'] = random.randint(1, 3)  # 1=grant, 2=revoke, 3=revoke all
                
            if 'privileges' not in mutated_request or not mutated_request['privileges']:
                mutated_request['privileges'] = [random.randint(1, 10) for _ in range(random.randint(1, 3))]  # List of privilege types
                
        return mutated_request


# Mutator for SelectGrant requests
class SelectGrantMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate SelectGrant requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'entity' not in mutated_request or not mutated_request['entity']:
                mutated_request['entity'] = {
                    'name': f"user_{random.randint(1, 1000)}",
                    'type': random.choice([1, 2])  # 1=role, 2=user
                }
                
        return mutated_request


# Mutator for CreatePrivilegeGroup requests
class CreatePrivilegeGroupMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate CreatePrivilegeGroup requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'group_name' not in mutated_request or not mutated_request['group_name']:
                mutated_request['group_name'] = f"group_{random.randint(1, 1000)}"
                
            if 'privileges' not in mutated_request or not mutated_request['privileges']:
                mutated_request['privileges'] = [random.randint(1, 10) for _ in range(random.randint(1, 3))]  # List of privilege types
                
        return mutated_request


# Mutator for DropPrivilegeGroup requests
class DropPrivilegeGroupMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate DropPrivilegeGroup requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'group_name' not in mutated_request or not mutated_request['group_name']:
                mutated_request['group_name'] = f"group_{random.randint(1, 1000)}"
                
        return mutated_request


# Mutator for OperatePrivilegeGroup requests
class OperatePrivilegeGroupMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate OperatePrivilegeGroup requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # Ensure required fields exist and are non-empty
        if isinstance(mutated_request, dict):
            if 'entities' not in mutated_request or not mutated_request['entities']:
                mutated_request['entities'] = [
                    {
                        'entity': {
                            'name': f"role_{random.randint(1, 1000)}",
                            'type': random.choice([1, 2])  # 1=role, 2=user
                        }
                    }
                ]
                
            if 'group_name' not in mutated_request or not mutated_request['group_name']:
                mutated_request['group_name'] = f"group_{random.randint(1, 1000)}"
                
            if 'action_type' not in mutated_request or not isinstance(mutated_request['action_type'], int):
                mutated_request['action_type'] = random.randint(1, 3)  # 1=grant, 2=revoke, 3=revoke all
                
            if 'object' not in mutated_request or not mutated_request['object']:
                mutated_request['object'] = {
                    'name': f"collection_{random.randint(1, 1000)}",
                    'type': random.randint(1, 5)  # Object type
                }
                
        return mutated_request


# Mutator for ListPrivilegeGroups requests
class ListPrivilegeGroupsMutator:
    def __init__(self, base_mutator):
        self.base_mutator = base_mutator
        
    def mutate_request(self, request):
        """Mutate ListPrivilegeGroups requests with special handling"""
        # Use the base mutator for the initial mutation
        mutated_request = self.base_mutator.mutate_request(request)
        
        # This request usually does not need special handling because it has no required fields
        # Optional filtering flags can still be added
        if isinstance(mutated_request, dict):
            if random.choice([True, False]):
                mutated_request['include_group_info'] = random.choice([True, False])
                
        return mutated_request
