"""
Daemon Logger - Enhanced logging for portal daemon

Provides organized log files with run-specific subdirectories and per-process separation.
Each daemon run creates a new subdirectory with separate log files for each workflow.

Features:
- Run-specific subdirectories (logs/run_YYYY-MM-DD_HH-MM-SS/)
- Separate log file for each workflow process
- Main daemon log for coordination/status
- Both file and console output
- Easy to navigate and debug individual processes
- Workflow context system for parallel workers (logs from all workers go to correct file)

Usage in parallel workers:
    from daemon_logger import set_workflow_context

    def worker_function(data):
        set_workflow_context('QueueAnalyze')  # All logs now go to QueueAnalyze.log
        # ... do work ...
"""

import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


# Thread-local storage for workflow context
# This allows parallel workers to set their workflow context
_workflow_context = threading.local()


def set_workflow_context(workflow_name: str):
    """Set the current workflow context for logging (thread-safe)"""
    _workflow_context.name = workflow_name


def get_workflow_context() -> Optional[str]:
    """Get the current workflow context"""
    return getattr(_workflow_context, 'name', None)


class ThreadFilter(logging.Filter):
    """Filter that only allows log records from specific threads"""

    def __init__(self, thread_name: str):
        super().__init__()
        self.thread_name = thread_name

    def filter(self, record):
        """Only allow records from the specified thread"""
        return threading.current_thread().name == self.thread_name


class WorkflowContextFilter(logging.Filter):
    """Filter that captures logs based on workflow context (works with parallel workers)"""

    def __init__(self, workflow_name: str):
        super().__init__()
        self.workflow_name = workflow_name

    def filter(self, record):
        """Only allow records from the specified workflow context"""
        context = get_workflow_context()
        # Also allow logs from the main workflow thread (for backwards compatibility)
        return context == self.workflow_name or threading.current_thread().name == self.workflow_name


class MainThreadFilter(logging.Filter):
    """Filter that only allows log records from the main thread (excludes workflow threads)"""

    def __init__(self):
        super().__init__()
        self.workflow_threads = set()

    def add_workflow_thread(self, thread_name: str):
        """Register a workflow thread to be excluded"""
        self.workflow_threads.add(thread_name)

    def filter(self, record):
        """Only allow records from threads that are NOT workflow threads"""
        current_thread = threading.current_thread().name
        return current_thread not in self.workflow_threads


class DaemonLogger:
    """Enhanced logging setup for daemon with per-process log files in run-specific subdirectories"""

    def __init__(self, logs_dir: str = "../logs"):
        """
        Initialize daemon logger

        Args:
            logs_dir: Directory for log files (default: ../logs)
        """
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Generate timestamped subdirectory for this daemon run
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.run_dir = self.logs_dir / f"run_{timestamp}"
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # Main daemon log file
        self.log_file = self.run_dir / "daemon.log"

        # Track workflow-specific log files
        self.workflow_log_files: Dict[str, Path] = {}
        self.workflow_handlers: Dict[str, logging.FileHandler] = {}

        # Create main thread filter to exclude workflow threads
        self.main_thread_filter = MainThreadFilter()

        # Keep reference to logger
        self.logger = None

    def setup_logging(self, level: int = logging.INFO) -> logging.Logger:
        """
        Configure logging with file and console handlers

        Args:
            level: Logging level (default: INFO)

        Returns:
            Configured logger
        """
        # Custom formatter with thread information
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)-8s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # File handler - writes to main daemon log file (excludes workflow threads)
        file_handler = logging.FileHandler(self.log_file, mode='a', encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        file_handler.addFilter(self.main_thread_filter)  # Only log from non-workflow threads

        # Console handler - writes to stdout (excludes workflow threads)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        console_handler.addFilter(self.main_thread_filter)  # Only log from non-workflow threads

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        # Remove any existing handlers to avoid duplicates
        root_logger.handlers.clear()

        # Add our handlers
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

        # Create daemon logger
        self.logger = logging.getLogger('daemon')

        # Log initialization
        self._log_separator("=", 80)
        self.logger.info(f"📝 Daemon logger initialized")
        self.logger.info(f"📂 Run directory: {self.run_dir}")
        self.logger.info(f"📂 Main log file: {self.log_file}")
        self._log_separator("=", 80)

        return self.logger

    def setup_workflow_logger(self, workflow_name: str, level: int = logging.INFO) -> logging.Logger:
        """
        Create a separate log file and logger for a specific workflow

        Args:
            workflow_name: Name of the workflow (e.g., "QueueSubmit")
            level: Logging level (default: INFO)

        Returns:
            Configured workflow logger
        """
        # Register this workflow thread with the main thread filter
        # This prevents workflow logs from appearing in daemon.log
        self.main_thread_filter.add_workflow_thread(workflow_name)

        # Create workflow-specific log file
        workflow_log_file = self.run_dir / f"{workflow_name}.log"
        self.workflow_log_files[workflow_name] = workflow_log_file

        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)-8s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Create file handler for this workflow with context filter
        workflow_file_handler = logging.FileHandler(workflow_log_file, mode='a', encoding='utf-8')
        workflow_file_handler.setFormatter(formatter)
        workflow_file_handler.setLevel(level)

        # Add workflow context filter to capture logs from main thread and parallel workers
        context_filter = WorkflowContextFilter(workflow_name)
        workflow_file_handler.addFilter(context_filter)

        self.workflow_handlers[workflow_name] = workflow_file_handler

        # Add workflow file handler to ROOT logger so ALL module loggers write to it
        # The thread filter ensures only logs from this workflow's thread are captured
        root_logger = logging.getLogger()
        root_logger.addHandler(workflow_file_handler)

        # Create logger for this workflow
        workflow_logger = logging.getLogger(workflow_name)
        workflow_logger.setLevel(level)
        workflow_logger.propagate = True  # Propagate to root logger so messages reach workflow file handler

        # Add console handler with context filter (only show logs from this workflow context)
        # The root logger's console handler will ignore these (MainThreadFilter excludes workflow threads)
        # so there's no duplicate console output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        console_handler.addFilter(context_filter)
        workflow_logger.addHandler(console_handler)

        return workflow_logger

    def _log_separator(self, char: str = "-", length: int = 80, newline_before: bool = False, newline_after: bool = False):
        """Internal helper to log separator lines"""
        if newline_before:
            self.logger.info("")
        self.logger.info(char * length)
        if newline_after:
            self.logger.info("")

    def log_thread_start(self, thread_name: str, description: str, interval_minutes: int):
        """
        Log thread start with separator

        Args:
            thread_name: Name of the thread/workflow
            description: Description of what the thread does
            interval_minutes: How often the thread runs
        """
        logger = logging.getLogger(thread_name)

        logger.info("")
        self._log_separator("=", 80)
        logger.info(f"🚀 THREAD STARTED: {thread_name}")
        logger.info(f"📋 Description: {description}")
        logger.info(f"⏱️  Interval: Every {interval_minutes} minutes")
        logger.info(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._log_separator("=", 80)
        logger.info("")

    def log_cycle_start(self, thread_name: str, cycle_num: int):
        """
        Log cycle start with separator

        Args:
            thread_name: Name of the thread/workflow
            cycle_num: Cycle number
        """
        logger = logging.getLogger(thread_name)

        logger.info("")
        self._log_separator("-", 60)
        logger.info(f"🔄 CYCLE #{cycle_num} STARTED")
        logger.info(f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._log_separator("-", 60)

    def log_cycle_end(self, thread_name: str, cycle_num: int, success: bool, duration_seconds: float, stats: Optional[Dict[str, Any]] = None):
        """
        Log cycle end with separator

        Args:
            thread_name: Name of the thread/workflow
            cycle_num: Cycle number
            success: Whether the cycle succeeded
            duration_seconds: How long the cycle took
            stats: Optional workflow-specific statistics (e.g., requests processed, successes, failures)
        """
        logger = logging.getLogger(thread_name)

        status_emoji = "✅" if success else "❌"
        status_text = "COMPLETED SUCCESSFULLY" if success else "FAILED"

        self._log_separator("-", 60)
        logger.info(f"{status_emoji} CYCLE #{cycle_num} {status_text}")
        logger.info(f"⏱️  Duration: {duration_seconds:.1f} seconds ({duration_seconds/60:.1f} minutes)")
        logger.info(f"🕐 Ended at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Log workflow-specific statistics if provided
        if stats:
            # Check if this is a monitoring workflow (has monitoring-specific stats)
            if 'successful_checks' in stats and 'sessions_processed' in stats:
                self._log_monitoring_stats(logger, stats)
            else:
                # Generic stats display for other workflows
                logger.info(f"📊 Cycle Statistics:")
                for key, value in stats.items():
                    # Format the key to be more readable (e.g., requests_checked -> Requests Checked)
                    formatted_key = key.replace('_', ' ').title()
                    logger.info(f"   • {formatted_key}: {value}")

        self._log_separator("-", 60)
        logger.info("")

    def _log_monitoring_stats(self, logger, stats: Dict[str, Any]):
        """
        Format and log monitoring-specific statistics in a clear, hierarchical way

        Args:
            logger: Logger to use
            stats: Statistics dict containing monitoring metrics
        """
        successful_checks = stats.get('successful_checks', 0)
        failed_checks = stats.get('failed_checks', 0)
        changes_detected = stats.get('changes_detected', 0)
        attention_flags = stats.get('attention_flags_set', 0)
        sessions_processed = stats.get('sessions_processed', 0)
        successful_sessions = stats.get('successful_sessions', 0)

        total_requests = successful_checks + failed_checks
        failed_sessions = sessions_processed - successful_sessions

        # Calculate percentages
        success_rate = (successful_checks / total_requests * 100) if total_requests > 0 else 0
        session_success_rate = (successful_sessions / sessions_processed * 100) if sessions_processed > 0 else 0
        change_rate = (changes_detected / successful_checks * 100) if successful_checks > 0 else 0
        flagged_rate = (attention_flags / changes_detected * 100) if changes_detected > 0 else 0

        logger.info(f"📊 Monitoring Cycle Complete:")
        logger.info(f"")
        logger.info(f"Portal Sessions:")
        logger.info(f"   • Completed: {successful_sessions}/{sessions_processed} ({session_success_rate:.0f}% success rate)")
        if failed_sessions > 0:
            logger.info(f"   • Failed: {failed_sessions} sessions encountered errors")

        logger.info(f"")
        logger.info(f"Request Monitoring:")
        logger.info(f"   • Successfully monitored: {successful_checks}/{total_requests} requests ({success_rate:.0f}% success)")
        if failed_checks > 0:
            logger.info(f"   • Failed to check: {failed_checks} requests")

        logger.info(f"")
        logger.info(f"Change Detection:")
        logger.info(f"   • Requests with changes: {changes_detected}/{successful_checks} ({change_rate:.0f}%)")
        logger.info(f"   • Flagged for user attention: {attention_flags}/{changes_detected if changes_detected > 0 else 1} ({flagged_rate:.0f}%)")
        logger.info(f"   • No changes: {successful_checks - changes_detected}/{successful_checks} ({100-change_rate:.0f}%)")

    def log_thread_stop(self, thread_name: str, total_cycles: int, total_errors: int):
        """
        Log thread stop with final statistics

        Args:
            thread_name: Name of the thread/workflow
            total_cycles: Total number of cycles completed
            total_errors: Total number of errors encountered
        """
        logger = logging.getLogger(thread_name)

        logger.info("")
        self._log_separator("=", 80)
        logger.info(f"🛑 THREAD STOPPED: {thread_name}")
        logger.info(f"📊 Total Cycles: {total_cycles}")
        logger.info(f"❌ Total Errors: {total_errors}")
        logger.info(f"✅ Success Rate: {((total_cycles - total_errors) / total_cycles * 100) if total_cycles > 0 else 0:.1f}%")
        logger.info(f"🕐 Stopped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._log_separator("=", 80)
        logger.info("")

        # IMPORTANT: Remove workflow file handler from root logger to prevent accumulation
        if thread_name in self.workflow_handlers:
            workflow_file_handler = self.workflow_handlers[thread_name]
            root_logger = logging.getLogger()
            root_logger.removeHandler(workflow_file_handler)
            workflow_file_handler.close()
            del self.workflow_handlers[thread_name]

    def log_daemon_start(self, num_workflows: int, headless: bool, user_id: Optional[str]):
        """
        Log daemon startup

        Args:
            num_workflows: Number of enabled workflows
            headless: Whether running in headless mode
            user_id: User ID (if specified)
        """
        if not self.logger:
            self.logger = logging.getLogger('daemon')

        self.logger.info("")
        self._log_separator("=", 80)
        self.logger.info("🚀 PORTAL AGENT DAEMON STARTING")
        self._log_separator("=", 80)
        self.logger.info(f"📋 Configuration:")
        self.logger.info(f"   🖥️  Headless Mode: {headless}")
        self.logger.info(f"   👤 User ID: {user_id or 'Not specified'}")
        self.logger.info(f"   🔧 Enabled Workflows: {num_workflows}")
        self._log_separator("=", 80)
        self.logger.info("")

    def log_daemon_shutdown(self, total_cycles: int, total_errors: int):
        """
        Log daemon shutdown

        Args:
            total_cycles: Total cycles across all workflows
            total_errors: Total errors across all workflows
        """
        if not self.logger:
            self.logger = logging.getLogger('daemon')

        self.logger.info("")
        self._log_separator("=", 80)
        self.logger.info("🛑 DAEMON SHUTDOWN")
        self._log_separator("=", 80)
        self.logger.info(f"📊 Final Statistics:")
        self.logger.info(f"   Total Cycles: {total_cycles}")
        self.logger.info(f"   Total Errors: {total_errors}")
        self.logger.info(f"   Success Rate: {((total_cycles - total_errors) / total_cycles * 100) if total_cycles > 0 else 0:.1f}%")
        self._log_separator("=", 80)
        self.logger.info("✅ SHUTDOWN COMPLETE")
        self._log_separator("=", 80)
        self.logger.info("")

    def get_log_file_path(self) -> Path:
        """Get the path to the current main daemon log file"""
        return self.log_file

    def get_run_dir(self) -> Path:
        """Get the path to the current run directory"""
        return self.run_dir

    def get_workflow_log_path(self, workflow_name: str) -> Optional[Path]:
        """Get the path to a specific workflow's log file"""
        return self.workflow_log_files.get(workflow_name)


# Convenience function for easy import
def setup_daemon_logging(logs_dir: str = "../logs", level: int = logging.INFO) -> tuple[logging.Logger, DaemonLogger]:
    """
    Setup daemon logging and return logger and manager

    Args:
        logs_dir: Directory for log files
        level: Logging level

    Returns:
        Tuple of (logger, daemon_logger_manager)
    """
    daemon_logger = DaemonLogger(logs_dir)
    logger = daemon_logger.setup_logging(level)
    return logger, daemon_logger
