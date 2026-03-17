#!/usr/bin/env python3
"""
Portal Agent Daemon - Production Service

Runs all portal workflows simultaneously in separate threads for autonomous server deployment.

This daemon imports command functions from entry.py and orchestrates them to run continuously
with configurable intervals. It's designed for 24/7 operation on a server.

Architecture:
    - entry.py: CLI tool for manual/development use
    - daemon.py: Production service for autonomous operation

Usage:
    python daemon.py [options]

    Options:
        --config CONFIG_FILE    Path to config file (default: daemon_config.json)
        --headless              Run all browsers in headless mode (default: True)

System Requirements:
    - Sufficient memory for 6 concurrent browser sessions
    - Stable network connection
    - Valid .env configuration

Monitoring:
    - All workflows log to the same logger
    - Each workflow has a thread name for identification
    - Errors are logged but don't crash the daemon
    - Health status available via logs
"""

import sys
import os
import time
import logging
import threading
import signal
import argparse
import json
import gc
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Import command functions from entry.py
# These are the actual workflow implementations
from entry import (
    validate_environment,
    cmd_queue_submit,
    cmd_queue_analyze,
    cmd_monitor,
    cmd_gmail_monitor,  # Email monitoring
    cmd_messages_draft,
    cmd_messages_send,
    cmd_documents_download
)

# Import enhanced daemon logger
from daemon_logger import setup_daemon_logging, DaemonLogger

load_dotenv()

# Setup enhanced logging with timestamped files
logger, daemon_logger_manager = setup_daemon_logging(logs_dir="../logs", level=logging.INFO)


# ============================================================================
# WORKFLOW CONFIGURATION
# ============================================================================

@dataclass
class WorkflowConfig:
    """Configuration for a single workflow"""
    name: str
    enabled: bool
    interval_minutes: int
    command_func: callable
    args: Dict[str, Any]
    description: str


class DaemonConfig:
    """Daemon configuration manager"""

    DEFAULT_CONFIG = {
        "headless": True,
        "user_id": None,  
        "workflows": {
            "queue_submit": {
                "enabled": True,
                "interval_minutes": 30,
                "mode": "parallel",
                "max_requests": None,
                "workers": 1,
                "description": "Process request submission queue"
            },
            "queue_analyze": {
                "enabled": True,
                "interval_minutes": 5,
                "mode": "parallel",
                "max_jobs": None,
                "workers": 1,
                "description": "Process bulk analysis queue"
            },
            "monitor": {
                "enabled": True,
                "interval_minutes": 1440,
                "mode": "parallel",
                "target_users": "all",
                "workers": 10,
                "description": "Monitor portal requests for changes"
            },
            "gmail_monitor": {
                "enabled": True,
                "interval_minutes": 5,  # Check email more frequently
                "mode": "single",
                "target_users": "all",
                "portal_type": "email",
                "workers": 5,
                "description": "Monitor Gmail for agency email responses"
            },
            "messages_draft": {
                "enabled": True,
                "interval_minutes": 1440,
                "mode": "parallel",
                "target_users": "all",
                "workers": 1,
                "description": "Draft messages for flagged requests"
            },
            "messages_send": {
                "enabled": True,
                "interval_minutes": 5,
                "mode": "parallel",
                "target_users": "all",
                "max_batch_size": 5,
                "workers": 1,
                "description": "Send approved message drafts"
            },
            "documents_download": {
                "enabled": True,
                "interval_minutes": 360,  # 6 hours
                "mode": "single",
                "target_users": "all",
                "description": "Download documents from requests"
            }
        }
    }

    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration from file or defaults"""
        if config_file and os.path.exists(config_file):
            logger.info(f"📋 Loading configuration from {config_file}")
            with open(config_file, 'r') as f:
                self.config = json.load(f)
        else:
            logger.info("📋 Using default configuration")
            self.config = self.DEFAULT_CONFIG.copy()

        # Override with environment variables
        self._apply_env_overrides()

    def _apply_env_overrides(self):
        """Apply environment variable overrides"""
        # Global settings
        if os.environ.get('HEADLESS_MODE'):
            self.config['headless'] = os.environ.get('HEADLESS_MODE', 'true').lower() == 'true'

        if os.environ.get('TEST_USER_ID'):
            self.config['user_id'] = os.environ.get('TEST_USER_ID')

        # Workflow-specific overrides
        for workflow_name in self.config['workflows']:
            env_prefix = workflow_name.upper().replace('_', '_')

            # Check if workflow is disabled via env
            env_enabled = os.environ.get(f'{env_prefix}_ENABLED')
            if env_enabled is not None:
                self.config['workflows'][workflow_name]['enabled'] = env_enabled.lower() == 'true'

            # Check interval override
            env_interval = os.environ.get(f'{env_prefix}_INTERVAL_MINUTES')
            if env_interval:
                try:
                    self.config['workflows'][workflow_name]['interval_minutes'] = int(env_interval)
                except ValueError:
                    logger.warning(f"Invalid interval for {workflow_name}: {env_interval}")

    def get_workflow_configs(self) -> Dict[str, WorkflowConfig]:
        """Get workflow configurations"""
        workflows = {}

        # Build argument objects for each workflow based on entry.py's expectations
        # These mimic the argparse namespace objects that entry.py commands expect

        class Args:
            """Mock argparse.Namespace for passing to entry.py commands"""
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        # Queue Submit
        if self.config['workflows']['queue_submit']['enabled']:
            workflows['queue_submit'] = WorkflowConfig(
                name='QueueSubmit',
                enabled=True,
                interval_minutes=self.config['workflows']['queue_submit']['interval_minutes'],
                command_func=cmd_queue_submit,
                args=Args(
                    headless=self.config['headless'],
                    mode=self.config['workflows']['queue_submit'].get('mode', 'parallel'),
                    continuous=False,  # Daemon handles looping
                    user_id=self.config.get('user_id'),
                    interval=self.config['workflows']['queue_submit']['interval_minutes'],
                    max_requests=self.config['workflows']['queue_submit']['max_requests'],
                    workers=self.config['workflows']['queue_submit'].get('workers', 5)
                ),
                description=self.config['workflows']['queue_submit']['description']
            )

        # Queue Analyze
        if self.config['workflows']['queue_analyze']['enabled']:
            workflows['queue_analyze'] = WorkflowConfig(
                name='QueueAnalyze',
                enabled=True,
                interval_minutes=self.config['workflows']['queue_analyze']['interval_minutes'],
                command_func=cmd_queue_analyze,
                args=Args(
                    headless=self.config['headless'],
                    mode=self.config['workflows']['queue_analyze'].get('mode', 'parallel'),
                    continuous=False,
                    user_id=self.config.get('user_id'),
                    interval=self.config['workflows']['queue_analyze']['interval_minutes'],
                    max_jobs=self.config['workflows']['queue_analyze']['max_jobs'],
                    workers=self.config['workflows']['queue_analyze'].get('workers', 5)
                ),
                description=self.config['workflows']['queue_analyze']['description']
            )

        # Monitor
        if self.config['workflows']['monitor']['enabled']:
            workflows['monitor'] = WorkflowConfig(
                name='Monitor',
                enabled=True,
                interval_minutes=self.config['workflows']['monitor']['interval_minutes'],
                command_func=cmd_monitor,
                args=Args(
                    headless=self.config['headless'],
                    mode=self.config['workflows']['monitor'].get('mode', 'parallel'),
                    interval=self.config['workflows']['monitor']['interval_minutes'],
                    target_users=self.config['workflows']['monitor']['target_users'],
                    workers=self.config['workflows']['monitor'].get('workers', 5)
                ),
                description=self.config['workflows']['monitor']['description']
            )

        # Gmail Monitor
        if self.config['workflows']['gmail_monitor']['enabled']:
            workflows['gmail_monitor'] = WorkflowConfig(
                name='GmailMonitor',
                enabled=True,
                interval_minutes=self.config['workflows']['gmail_monitor']['interval_minutes'],
                command_func=cmd_gmail_monitor,
                args=Args(
                    mode=self.config['workflows']['gmail_monitor'].get('mode', 'single'),
                    target_users=self.config['workflows']['gmail_monitor']['target_users'],
                    portal_type=self.config['workflows']['gmail_monitor'].get('portal_type', 'email'),
                    workers=self.config['workflows']['gmail_monitor'].get('workers', 5)
                ),
                description=self.config['workflows']['gmail_monitor']['description']
            )

        # Messages Draft
        if self.config['workflows']['messages_draft']['enabled']:
            workflows['messages_draft'] = WorkflowConfig(
                name='MessagesDraft',
                enabled=True,
                interval_minutes=self.config['workflows']['messages_draft']['interval_minutes'],
                command_func=cmd_messages_draft,
                args=Args(
                    headless=self.config['headless'],
                    mode=self.config['workflows']['messages_draft'].get('mode', 'parallel'),
                    target_users=self.config['workflows']['messages_draft']['target_users'],
                    workers=self.config['workflows']['messages_draft'].get('workers', 5)
                ),
                description=self.config['workflows']['messages_draft']['description']
            )

        # Messages Send
        if self.config['workflows']['messages_send']['enabled']:
            workflows['messages_send'] = WorkflowConfig(
                name='MessagesSend',
                enabled=True,
                interval_minutes=self.config['workflows']['messages_send']['interval_minutes'],
                command_func=cmd_messages_send,
                args=Args(
                    headless=self.config['headless'],
                    mode=self.config['workflows']['messages_send'].get('mode', 'parallel'),
                    target_users=self.config['workflows']['messages_send']['target_users'],
                    max_batch_size=self.config['workflows']['messages_send']['max_batch_size'],
                    workers=self.config['workflows']['messages_send'].get('workers', 5)
                ),
                description=self.config['workflows']['messages_send']['description']
            )

        # Documents Download
        if self.config['workflows']['documents_download']['enabled']:
            workflows['documents_download'] = WorkflowConfig(
                name='DocumentsDownload',
                enabled=True,
                interval_minutes=self.config['workflows']['documents_download']['interval_minutes'],
                command_func=cmd_documents_download,
                args=Args(
                    headless=self.config['headless'],
                    mode='single',
                    interval=self.config['workflows']['documents_download']['interval_minutes'],
                    target_users=self.config['workflows']['documents_download']['target_users']
                ),
                description=self.config['workflows']['documents_download']['description']
            )

        return workflows

    def save(self, filepath: str):
        """Save current configuration to file"""
        with open(filepath, 'w') as f:
            json.dump(self.config, f, indent=2)
        logger.info(f"💾 Configuration saved to {filepath}")


# ============================================================================
# DAEMON IMPLEMENTATION
# ============================================================================

class PortalDaemon:
    """Main daemon that orchestrates all workflows"""

    def __init__(self, config: DaemonConfig, logger_manager: DaemonLogger):
        self.config = config
        self.workflows = config.get_workflow_configs()
        self.threads = []
        self.shutdown_event = threading.Event()
        self.workflow_stats = {workflow.name.lower(): {'cycles': 0, 'errors': 0, 'last_run': None}
                              for workflow in self.workflows.values()}
        self.logger_manager = logger_manager

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"🛑 Received signal {signum}, initiating graceful shutdown...")
        self.shutdown()

    def _run_workflow_loop(self, workflow: WorkflowConfig):
        """Run a single workflow in a loop with its configured interval"""
        # Import context setter
        from daemon_logger import set_workflow_context

        # Set workflow context for this thread (enables parallel worker logging)
        set_workflow_context(workflow.name)

        # Setup dedicated logger for this workflow
        workflow_logger = self.logger_manager.setup_workflow_logger(workflow.name)

        # Log thread start with separator
        self.logger_manager.log_thread_start(
            workflow.name,
            workflow.description,
            workflow.interval_minutes
        )

        while not self.shutdown_event.is_set():
            cycle_start = time.time()
            cycle_num = self.workflow_stats[workflow.name.lower()]['cycles'] + 1

            # Log cycle start with separator
            self.logger_manager.log_cycle_start(workflow.name, cycle_num)

            try:
                # Call the command function from entry.py
                result = workflow.command_func(workflow.args)

                # Update statistics
                self.workflow_stats[workflow.name.lower()]['cycles'] += 1
                self.workflow_stats[workflow.name.lower()]['last_run'] = datetime.now().isoformat()

                # Extract stats and exit code from result
                workflow_stats = None
                if isinstance(result, dict) and 'exit_code' in result:
                    # Result is a dict with exit_code and optional stats
                    exit_code = result['exit_code']
                    workflow_stats = result.get('stats')
                    success = (exit_code == 0)
                else:
                    # Legacy format: result is just an exit code
                    success = (result == 0 or result is None)
                    exit_code = result

                if not success:
                    workflow_logger.warning(f"⚠️ Cycle completed with status code {exit_code}")
                    self.workflow_stats[workflow.name.lower()]['errors'] += 1

            except Exception as e:
                workflow_logger.error(f"❌ Error during cycle: {str(e)}", exc_info=True)
                self.workflow_stats[workflow.name.lower()]['errors'] += 1
                success = False
                workflow_stats = None

            # Calculate cycle duration and log cycle end with separator (including stats if available)
            cycle_duration = time.time() - cycle_start
            self.logger_manager.log_cycle_end(workflow.name, cycle_num, success, cycle_duration, workflow_stats)

            # Force garbage collection to free memory after each cycle
            gc.collect()

            # Calculate wait time until next cycle
            wait_time = max(0, (workflow.interval_minutes * 60) - cycle_duration)

            if wait_time > 0:
                next_run = datetime.fromtimestamp(time.time() + wait_time)
                workflow_logger.info(f"💤 Sleeping for {wait_time/60:.1f} minutes (next run at {next_run.strftime('%H:%M:%S')})")

                # Wait with shutdown check
                if self.shutdown_event.wait(timeout=wait_time):
                    break  # Shutdown signal received
            else:
                workflow_logger.warning(f"⚠️ Cycle took longer than interval ({cycle_duration/60:.1f} min > {workflow.interval_minutes} min)")

        # Log thread stop with final statistics
        self.logger_manager.log_thread_stop(
            workflow.name,
            self.workflow_stats[workflow.name.lower()]['cycles'],
            self.workflow_stats[workflow.name.lower()]['errors']
        )

    def start(self):
        """Start all enabled workflows"""
        # Log daemon start with configuration
        self.logger_manager.log_daemon_start(
            num_workflows=len(self.workflows),
            headless=self.config.config['headless'],
            user_id=self.config.config.get('user_id')
        )

        # Validate environment
        logger.info("🔍 Validating environment...")
        if not validate_environment():
            logger.error("❌ Environment validation failed")
            return 1

        logger.info("✅ Environment validated")
        logger.info("")

        # Display workflow configuration
        logger.info("📋 Enabled Workflows:")
        for name, workflow in self.workflows.items():
            logger.info(f"   • {workflow.name}: Every {workflow.interval_minutes} min - {workflow.description}")

        logger.info("")

        # Start each workflow in its own thread
        logger.info("🚀 Starting workflow threads...")
        for workflow_id, workflow in self.workflows.items():
            thread = threading.Thread(
                target=self._run_workflow_loop,
                args=(workflow,),
                name=workflow.name,
                daemon=True
            )
            thread.start()
            self.threads.append(thread)
            logger.info(f"   ✅ {workflow.name}: Thread started")

        logger.info("")
        logger.info("="*80)
        logger.info(f"🎯 All workflows running! Daemon operational.")
        logger.info(f"💡 Press Ctrl+C to stop gracefully")
        logger.info(f"📂 Logs directory: {self.logger_manager.get_run_dir()}")
        logger.info(f"📄 Main log: {self.logger_manager.get_log_file_path().name}")
        for workflow_name in self.workflows.keys():
            log_path = self.logger_manager.get_workflow_log_path(self.workflows[workflow_name].name)
            if log_path:
                logger.info(f"📄 {self.workflows[workflow_name].name} log: {log_path.name}")
        logger.info("="*80)
        logger.info("")

        # Main thread: Monitor and log status periodically
        try:
            while not self.shutdown_event.is_set():
                # Log status every 5 minutes
                self.shutdown_event.wait(timeout=300)

                if not self.shutdown_event.is_set():
                    self._log_status()

        except KeyboardInterrupt:
            logger.info("🛑 Keyboard interrupt received")
            self.shutdown()

    def _log_status(self):
        """Log daemon status and statistics"""
        logger.info("")
        logger.info("📊 DAEMON STATUS REPORT")
        logger.info("-" * 60)

        for workflow_name, stats in self.workflow_stats.items():
            last_run = stats['last_run'] or 'Never'
            logger.info(f"  {workflow_name.replace('_', ' ').title()}:")
            logger.info(f"    Cycles: {stats['cycles']}, Errors: {stats['errors']}, Last Run: {last_run}")

        logger.info("-" * 60)
        logger.info("")

    def shutdown(self):
        """Gracefully shutdown all workflows"""
        logger.info("")
        logger.info("="*80)
        logger.info("🛑 INITIATING GRACEFUL SHUTDOWN")
        logger.info("="*80)

        # Signal all threads to stop
        self.shutdown_event.set()

        # Wait for threads to finish (with timeout)
        logger.info("⏳ Waiting for workflows to complete their current cycles...")

        for thread in self.threads:
            thread.join(timeout=30)  # Wait up to 30 seconds per thread
            if thread.is_alive():
                logger.warning(f"⚠️ {thread.name}: Thread did not stop within timeout")
            else:
                logger.info(f"✅ {thread.name}: Thread stopped")

        # Calculate final statistics
        total_cycles = sum(stats['cycles'] for stats in self.workflow_stats.values())
        total_errors = sum(stats['errors'] for stats in self.workflow_stats.values())

        # Log daemon shutdown with statistics
        self.logger_manager.log_daemon_shutdown(total_cycles, total_errors)

        sys.exit(0)


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def main():
    """Main entry point for daemon"""
    parser = argparse.ArgumentParser(
        description='Portal Agent Daemon - Production Service',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Run with default config
  %(prog)s --config my_config.json           # Run with custom config
  %(prog)s --headless                        # Force headless mode
  %(prog)s --generate-config daemon.json     # Generate default config file

Configuration:
  Configuration can be provided via:
    1. Config file (--config daemon_config.json)
    2. Environment variables (see .env.example)
    3. Command line arguments (override both)

Environment Variables:
  HEADLESS_MODE=true              # Run browsers in headless mode
  TEST_USER_ID=abc123             # User ID for testing
  QUEUE_SUBMIT_INTERVAL_MINUTES=30     # Custom interval for queue submit
  MONITOR_ENABLED=false           # Disable monitor workflow

Deployment:
  For production deployment, use systemd or supervisord to manage the daemon:

  # systemd example
  sudo systemctl start portal-daemon
  sudo systemctl enable portal-daemon  # Start on boot

  # supervisord example
  supervisorctl start portal-daemon
        """
    )

    parser.add_argument('--config', type=str,
                       help='Path to configuration file (JSON)')
    parser.add_argument('--headless', action='store_true',
                       help='Force headless mode (overrides config)')
    parser.add_argument('--generate-config', type=str, metavar='FILE',
                       help='Generate default configuration file and exit')

    args = parser.parse_args()

    # Generate config file if requested
    if args.generate_config:
        config = DaemonConfig()
        config.save(args.generate_config)
        print(f"✅ Default configuration saved to {args.generate_config}")
        print(f"💡 Edit the file and run: python daemon.py --config {args.generate_config}")
        return 0

    # Load configuration
    config = DaemonConfig(config_file=args.config)

    # Apply CLI overrides
    if args.headless:
        config.config['headless'] = True
        logger.info("🖥️  Headless mode forced via CLI argument")

    # Create and start daemon
    daemon = PortalDaemon(config, daemon_logger_manager)
    daemon.start()


if __name__ == "__main__":
    sys.exit(main())
