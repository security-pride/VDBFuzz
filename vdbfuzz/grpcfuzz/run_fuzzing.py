#!/usr/bin/env python3
import argparse
import logging
import os
import sys
import time

def setup_logger():
    """Set up the logger."""
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    
    return root_logger

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='Milvus gRPC Fuzzer - run fuzzing tests')
    
    parser.add_argument('--log-file', required=True, 
                       help='Path to the log file containing recorded gRPC requests')
    
    parser.add_argument('--server', default='localhost:19530', 
                       help='Milvus server address (default: localhost:19530)')
    
    parser.add_argument('--iterations', type=int, default=1000, 
                       help='Number of fuzzing iterations (default: 1000)')
    
    parser.add_argument('--output-dir', 
                       help='Output directory used to save test results (default: fuzzing_results_<timestamp>)')
    
    parser.add_argument('--mutation-levels', type=int, nargs='+', default=[1, 2, 3],
                       help='Mutation levels to use: any combination of 1 (light), 2 (medium), and 3 (high) (default: 1 2 3)')
    
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Check that the log file exists
    if not os.path.exists(args.log_file):
        parser.error(f"Log file does not exist: {args.log_file}")
    
    # Validate mutation levels
    for level in args.mutation_levels:
        if level not in [1, 2, 3]:
            parser.error(f"Invalid mutation level: {level}; it must be 1, 2, or 3")
    
    return args

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
    logger.info("Milvus gRPC Fuzzer - starting")
    logger.info(f"Target server: {args.server}")
    logger.info(f"Log file: {args.log_file}")
    logger.info(f"Planned {args.iterations} iterations")
    logger.info(f"Mutation levels: {args.mutation_levels}")
    logger.info("=" * 60)
    
    try:
        try:
            from .fuzzer_new import MilvusFuzzer
        except ModuleNotFoundError as exc:
            missing = exc.name or str(exc)
            logger.error(
                "Missing Milvus gRPC fuzz dependency: %s. Install it with `pip install -e .[milvus-grpc]`。",
                missing,
            )
            sys.exit(1)

        # Create the fuzzer instance
        fuzzer = MilvusFuzzer(
            server_addr=args.server, 
            log_file=args.log_file,
            output_dir=args.output_dir
        )
        
        # Run fuzzing
        start_time = time.time()
        report = fuzzer.run_fuzzing(
            iterations=args.iterations,
            mutation_levels=args.mutation_levels
        )
        elapsed_time = time.time() - start_time
        
        # Print summary results
        logger.info("=" * 60)
        logger.info("Fuzzing completed")
        logger.info(f"Total elapsed time: {(time.time() - start_time):.2f}s")
        
        if report is not None:
            logger.info(f"Potential issues found: {report['crash_count']}")
            logger.info(f"Test report saved in: {fuzzer.output_dir}")
        else:
            logger.error("No test report was generated. Check whether the request log file is valid")
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("\nExecution interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error while running tests: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
