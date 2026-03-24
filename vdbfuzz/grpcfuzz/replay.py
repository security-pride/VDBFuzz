#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sys

def setup_logger():
    """Set up the logger."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger("Replay")

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='Milvus gRPC Fuzzer - replay crash cases')
    
    parser.add_argument('--crash-file', required=True, 
                       help='Path to a crash log file, either a single crash record or an aggregated crash_logs.json')
    
    parser.add_argument('--index', type=int, default=0, 
                       help='Crash index to replay, only used when an aggregated crash log is provided (default: 0)')
    
    parser.add_argument('--server', default='localhost:19530', 
                       help='Milvus server address (default: localhost:19530)')
    
    parser.add_argument('--repeat', type=int, default=1,
                       help='Number of times to resend the request (default: 1)')
    
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Check that the crash log file exists
    if not os.path.exists(args.crash_file):
        parser.error(f"Crash log file does not exist: {args.crash_file}")
    
    return args

def load_crash_data(crash_file, index=0):
    """Load crash data."""
    logger = logging.getLogger("Replay")
    
    try:
        with open(crash_file, 'r') as f:
            data = json.load(f)
        
        # Determine the file format
        if isinstance(data, list):
            # The file contains multiple crash records
            if index >= len(data):
                logger.error(f"Index {index} is out of range; the file contains {len(data)} crash records")
                return None
            logger.info(f"Selected crash #{index+1}")
            return data[index]
        elif isinstance(data, dict):
            # The file contains a single crash record
            logger.info("Loaded a single crash record")
            return data
        else:
            logger.error("Invalid crash log format")
            return None
    except Exception as e:
        logger.error(f"Failed to load crash data: {e}")
        return None

def replay_crash(crash_data, server_addr, repeat=1):
    """Replay a recorded crash."""
    logger = logging.getLogger("Replay")
    
    if not crash_data:
        logger.error("No valid crash data available")
        return False
    
    method_name = crash_data.get('method')
    request_str = crash_data.get('request')
    
    if not method_name or not request_str:
        logger.error("Crash data is missing the method name or request payload")
        return False
    
    logger.info(f"Preparing to replay crash: {method_name}")
    logger.info(f"Error details: {crash_data.get('error_details', crash_data.get('error', 'unknown error'))}")
    
    # Create a fuzzer instance used only for parsing and sending the request
    try:
        from .fuzzer_new import MilvusFuzzer
    except ModuleNotFoundError as exc:
        missing = exc.name or str(exc)
        logger.error(
            "Missing Milvus gRPC fuzz dependency: %s. Install it with `pip install -e .[milvus-grpc]`。",
            missing,
        )
        return False

    fuzzer = MilvusFuzzer(server_addr=server_addr)
    
    # Parse the request
    request = fuzzer._parse_proto_message(method_name, request_str)
    
    if not request:
        logger.error("Failed to parse the request; replay aborted")
        return False
    
    # Replay the request the requested number of times
    success_count = 0
    for i in range(repeat):
        logger.info(f"Sending replay request ({i+1}/{repeat})...")
        try:
            response = fuzzer.send_request(method_name, request)
            if response:
                logger.info(f"Request returned successfully: {response}")
                success_count += 1
            else:
                logger.warning("Request failed or returned an empty response")
        except Exception as e:
            logger.warning(f"Request raised an exception: {e}")
    
    success_rate = (success_count / repeat) * 100 if repeat > 0 else 0
    logger.info(f"Replay finished: success rate {success_rate:.1f}% ({success_count}/{repeat})")
    
    return success_count > 0

def main():
    """Run the CLI entry point."""
    # Set up logging
    logger = setup_logger()
    
    # Parse command-line arguments
    args = parse_args()
    
    # Adjust log level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Print startup information
    logger.info("=" * 60)
    logger.info("Milvus gRPC Fuzzer - crash replay tool")
    logger.info(f"Crash log file: {args.crash_file}")
    logger.info(f"Target server: {args.server}")
    logger.info("=" * 60)
    
    try:
        # Load crash data
        crash_data = load_crash_data(args.crash_file, args.index)
        
        if crash_data:
            # Replay the crash
            replay_crash(crash_data, args.server, args.repeat)
        else:
            logger.error("Unable to load crash data; replay terminated")
            sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("\nReplay interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Replay failed with an error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
