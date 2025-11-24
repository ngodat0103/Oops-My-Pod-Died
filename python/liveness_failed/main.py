import asyncio
import random
import time
import traceback
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from pathlib import Path
import os
import psutil
import threading
import logging
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Response, status, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn


# Configure logging
def setup_logging():
    """Setup logging configuration"""
    # Create logs directory if not exists
    log_dir = Path("./logs")
    log_dir.mkdir(exist_ok=True)

    # Create logger
    logger = logging.getLogger("healthcheck")
    logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_dir / "healthcheck.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# Initialize logger
healthcheck_logger = setup_logging()


class FailureMode(str, Enum):
    HEALTHY = "healthy"
    DATABASE_ERROR = "database_error"
    MEMORY_LEAK = "memory_leak"
    DEPENDENCY_TIMEOUT = "dependency_timeout"
    RANDOM_CRASH = "random_crash"
    SLOW_RESPONSE = "slow_response"
    OOM_ERROR = "oom_error"
    CONNECTION_POOL_EXHAUSTED = "connection_pool_exhausted"


class RealWorldErrors:
    """Simulate real-world error messages and stack traces"""

    @staticmethod
    def database_connection_error():
        errors = [
            {
                "error": "psycopg2.OperationalError",
                "message": "could not connect to server: Connection refused. Is the server running on host 'postgres-db' (10.96.0.15) and accepting TCP/IP connections on port 5432?",
                "traceback": """Traceback (most recent call last):
  File "/app/services/database.py", line 45, in get_connection
    conn = psycopg2.connect(dsn=DATABASE_URL)
  File "/usr/local/lib/python3.12/site-packages/psycopg2/__init__.py", line 122, in connect
    conn = _connect(dsn, connection_factory=connection_factory, **kwasync)
psycopg2.OperationalError: could not connect to server: Connection refused"""
            },
            {
                "error": "sqlalchemy.exc.OperationalError",
                "message": "(pymysql.err.OperationalError) (2003, \"Can't connect to MySQL server on 'mysql-service' ([Errno 111] Connection refused)\")",
                "traceback": """Traceback (most recent call last):
  File "/app/models/user.py", line 23, in get_user
    result = session.execute(query)
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/orm/session.py", line 1716, in execute
    conn = self._connection_for_bind(bind)
sqlalchemy.exc.OperationalError: (pymysql.err.OperationalError) (2003, \"Can't connect to MySQL server\")"""
            },
            {
                "error": "redis.exceptions.ConnectionError",
                "message": "Error 111 connecting to redis-cache:6379. Connection refused.",
                "traceback": """Traceback (most recent call last):
  File "/app/cache/redis_client.py", line 67, in get
    return self.client.get(key)
  File "/usr/local/lib/python3.12/site-packages/redis/client.py", line 1809, in get
    return self.execute_command('GET', name)
redis.exceptions.ConnectionError: Error 111 connecting to redis-cache:6379. Connection refused."""
            }
        ]
        return random.choice(errors)

    @staticmethod
    def memory_error():
        return {
            "error": "MemoryError",
            "message": "Unable to allocate memory for array with shape (1000000, 1000000)",
            "traceback": """Traceback (most recent call last):
  File "/app/services/data_processor.py", line 156, in process_large_dataset
    data = np.zeros((1000000, 1000000))
MemoryError: Unable to allocate 7.45 TiB for an array with shape (1000000, 1000000) and data type float64"""
        }

    @staticmethod
    def dependency_timeout():
        errors = [
            {
                "error": "httpx.ReadTimeout",
                "message": "Read timeout after 30.0 seconds",
                "traceback": """Traceback (most recent call last):
  File "/app/services/external_api.py", line 89, in fetch_user_data
    response = await client.get(f"{API_URL}/users/{user_id}")
  File "/usr/local/lib/python3.12/site-packages/httpx/_client.py", line 1757, in get
    return await self.request("GET", url, **kwargs)
httpx.ReadTimeout: Read timeout after 30.0 seconds"""
            },
            {
                "error": "requests.exceptions.Timeout",
                "message": "HTTPConnectionPool(host='api.external-service.com', port=443): Read timed out. (read timeout=30)",
                "traceback": """Traceback (most recent call last):
  File "/app/integrations/payment_gateway.py", line 234, in process_payment
    response = requests.post(PAYMENT_URL, json=payload, timeout=30)
  File "/usr/local/lib/python3.12/site-packages/requests/api.py", line 115, in post
    return request('post', url, data=data, json=json, **kwargs)
requests.exceptions.Timeout: HTTPConnectionPool: Read timed out."""
            }
        ]
        return random.choice(errors)

    @staticmethod
    def connection_pool_exhausted():
        return {
            "error": "sqlalchemy.exc.TimeoutError",
            "message": "QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00",
            "traceback": """Traceback (most recent call last):
  File "/app/api/endpoints/users.py", line 45, in get_users
    users = db.query(User).all()
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/pool/impl.py", line 449, in _do_get
    return self._create_connection()
sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached, connection timed out"""
        }

    @staticmethod
    def random_exception():
        errors = [
            {
                "error": "KeyError",
                "message": "'user_id'",
                "traceback": """Traceback (most recent call last):
  File "/app/services/auth.py", line 123, in validate_token
    user_id = payload['user_id']
KeyError: 'user_id'"""
            },
            {
                "error": "AttributeError",
                "message": "'NoneType' object has no attribute 'id'",
                "traceback": """Traceback (most recent call last):
  File "/app/api/endpoints/orders.py", line 78, in get_order
    return order.user.id
AttributeError: 'NoneType' object has no attribute 'id'"""
            },
            {
                "error": "ValueError",
                "message": "invalid literal for int() with base 10: 'abc'",
                "traceback": """Traceback (most recent call last):
  File "/app/utils/validators.py", line 34, in parse_id
    return int(value)
ValueError: invalid literal for int() with base 10: 'abc'"""
            },
            {
                "error": "JSONDecodeError",
                "message": "Expecting value: line 1 column 1 (char 0)",
                "traceback": """Traceback (most recent call last):
  File "/app/services/webhook_handler.py", line 67, in process_webhook
    data = json.loads(payload)
  File "/usr/local/lib/python3.12/json/__init__.py", line 346, in loads
    return _default_decoder.decode(s)
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)"""
            }
        ]
        return random.choice(errors)


class PodSimulator:
    def __init__(self, config_file: str = "/data/simulator_config.json"):
        self.config_file = config_file
        self.config_dir = Path(config_file).parent

        # Default values
        self.failure_mode = FailureMode.RANDOM_CRASH
        self.failure_rate = 0.2
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.memory_usage_mb = 100
        self.slow_response_delay = 5

        # Auto-switch configuration
        self.auto_switch_enabled = True
        self.switch_interval_hours = 3
        self.last_switch_time = datetime.now()
        self.switch_count = 0

        # Load saved configuration
        self.load_config()

        # Start auto-switch thread
        self.start_auto_switch()

    def get_config_dict(self):
        """Get current configuration as dictionary"""
        return {
            "failure_mode": self.failure_mode.value,
            "failure_rate": self.failure_rate,
            "slow_response_delay": self.slow_response_delay,
            "auto_switch_enabled": self.auto_switch_enabled,
            "switch_interval_hours": self.switch_interval_hours,
            "last_switch_time": self.last_switch_time.isoformat(),
            "switch_count": self.switch_count,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "saved_at": datetime.now().isoformat()
        }

    def save_config(self):
        """Save configuration to file"""
        try:
            # Create directory if not exists
            self.config_dir.mkdir(parents=True, exist_ok=True)

            config = self.get_config_dict()

            # Write to temp file first, then rename (atomic operation)
            temp_file = f"{self.config_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(config, f, indent=2)

            # Atomic rename
            os.replace(temp_file, self.config_file)

            print(f"✅ Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            print(f"❌ Error saving configuration: {e}")
            return False

    def load_config(self):
        """Load configuration from file"""
        try:
            if not Path(self.config_file).exists():
                print(f"ℹ️  No saved configuration found at {self.config_file}")
                print(f"ℹ️  Using default configuration")
                self.save_config()  # Save default config
                return False

            with open(self.config_file, 'r') as f:
                config = json.load(f)

            # Restore configuration
            self.failure_mode = FailureMode(config.get("failure_mode", "random_crash"))
            self.failure_rate = config.get("failure_rate", 0.3)
            self.slow_response_delay = config.get("slow_response_delay", 5)
            self.auto_switch_enabled = config.get("auto_switch_enabled", True)
            self.switch_interval_hours = config.get("switch_interval_hours", 3)
            self.switch_count = config.get("switch_count", 0)
            self.request_count = config.get("request_count", 0)
            self.error_count = config.get("error_count", 0)

            # Parse last_switch_time
            last_switch_str = config.get("last_switch_time")
            if last_switch_str:
                self.last_switch_time = datetime.fromisoformat(last_switch_str)

            print(f"\n{'=' * 60}")
            print(f"📂 Configuration loaded from {self.config_file}")
            print(f"{'=' * 60}")
            print(f"Failure mode: {self.failure_mode}")
            print(f"Failure rate: {self.failure_rate}")
            print(f"Auto-switch: {'enabled' if self.auto_switch_enabled else 'disabled'}")
            print(f"Switch interval: {self.switch_interval_hours} hours")
            print(f"Switch count: {self.switch_count}")
            print(f"Total requests: {self.request_count}")
            print(f"Total errors: {self.error_count}")
            print(f"Last switch: {self.last_switch_time.isoformat()}")
            print(f"Saved at: {config.get('saved_at', 'unknown')}")
            print(f"{'=' * 60}\n")

            return True
        except Exception as e:
            print(f"❌ Error loading configuration: {e}")
            print(f"ℹ️  Using default configuration")
            return False

    def should_fail(self) -> bool:
        if self.failure_mode == FailureMode.HEALTHY:
            return False
        elif self.failure_mode == FailureMode.RANDOM_CRASH:
            return random.random() < self.failure_rate
        return True

    def get_memory_usage(self):
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # MB

    def switch_to_random_mode(self):
        """Switch to a random failure mode"""
        # Exclude HEALTHY from random selection to keep things interesting
        available_modes = [mode for mode in FailureMode if mode != FailureMode.HEALTHY]
        new_mode = random.choice(available_modes)

        old_mode = self.failure_mode
        self.failure_mode = new_mode
        self.last_switch_time = datetime.now()
        self.switch_count += 1

        # Reset some parameters
        self.memory_usage_mb = 100

        # Save configuration
        self.save_config()

        print(f"\n{'=' * 60}")
        print(f"🔄 AUTO-SWITCH #{self.switch_count}")
        print(f"{'=' * 60}")
        print(f"Previous mode: {old_mode}")
        print(f"New mode: {new_mode}")
        print(f"Switched at: {self.last_switch_time.isoformat()}")
        print(f"Next switch in: {self.switch_interval_hours} hours")
        print(f"{'=' * 60}\n")

        return old_mode, new_mode

    def auto_switch_worker(self):
        """Background worker that switches modes every N hours"""
        while self.auto_switch_enabled:
            time.sleep(60)  # Check every minute

            if not self.auto_switch_enabled:
                break

            time_since_last_switch = datetime.now() - self.last_switch_time
            if time_since_last_switch >= timedelta(hours=self.switch_interval_hours):
                self.switch_to_random_mode()

    def start_auto_switch(self):
        """Start the auto-switch background thread"""
        thread = threading.Thread(target=self.auto_switch_worker, daemon=True)
        thread.start()
        print(f"\n🚀 Auto-switch {'enabled' if self.auto_switch_enabled else 'disabled'}")
        if self.auto_switch_enabled:
            print(f"   Will change failure mode every {self.switch_interval_hours} hours")
        print(f"   Initial mode: {self.failure_mode}")
        print(f"   Started at: {self.last_switch_time.isoformat()}\n")

    def get_time_until_next_switch(self):
        """Get time remaining until next auto-switch"""
        time_since_last = datetime.now() - self.last_switch_time
        time_until_next = timedelta(hours=self.switch_interval_hours) - time_since_last
        return max(time_until_next.total_seconds(), 0)


# Get config file path from environment variable or use default
CONFIG_FILE = os.getenv("SIMULATOR_CONFIG_FILE", "./simulator_config.json")

app = FastAPI(
    title="E-Commerce Order Service",
    description="Microservice for handling order processing and inventory management",
    version="1.2.5"
)
simulator = PodSimulator(config_file=CONFIG_FILE)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()

    # Simulate slow response
    if simulator.failure_mode == FailureMode.SLOW_RESPONSE:
        await asyncio.sleep(simulator.slow_response_delay)

    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.get("/health")
async def health_check(response: Response):
    """Health check endpoint for Kubernetes probes"""
    simulator.request_count += 1

    # Auto-save every 100 requests
    if simulator.request_count % 100 == 0:
        simulator.save_config()

    try:
        # Simulate different failure modes
        if simulator.should_fail():
            simulator.error_count += 1
            if simulator.failure_mode == FailureMode.DATABASE_ERROR:
                error = RealWorldErrors.database_connection_error()
                healthcheck_logger.error(error)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "error": error["error"],
                        "message": error["message"],
                        "timestamp": datetime.now().isoformat(),
                        "service": "order-service",
                        "traceback": error["traceback"]
                    }
                )
            elif simulator.failure_mode == FailureMode.MEMORY_LEAK:
                # Simulate increasing memory usage
                simulator.memory_usage_mb += random.randint(50, 200)
                if simulator.memory_usage_mb > 1024:  # Over 1GB
                    error = RealWorldErrors.memory_error()
                    healthcheck_logger.error(error)
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail={
                            "error": error["error"],
                            "message": error["message"],
                            "memory_usage_mb": simulator.memory_usage_mb,
                            "timestamp": datetime.now().isoformat(),
                            "traceback": error["traceback"]
                        }
                    )

            elif simulator.failure_mode == FailureMode.DEPENDENCY_TIMEOUT:
                error = RealWorldErrors.dependency_timeout()
                healthcheck_logger.error(error)
                await asyncio.sleep(random.randint(30, 60))
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail={
                        "error": error["error"],
                        "message": error["message"],
                        "upstream_service": "payment-gateway",
                        "timestamp": datetime.now().isoformat(),
                        "traceback": error["traceback"]
                    }
                )

            elif simulator.failure_mode == FailureMode.CONNECTION_POOL_EXHAUSTED:
                error = RealWorldErrors.connection_pool_exhausted()
                healthcheck_logger.error(error)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": error["error"],
                        "message": error["message"],
                        "active_connections": 15,
                        "max_connections": 15,
                        "timestamp": datetime.now().isoformat(),
                        "traceback": error["traceback"]
                    }
                )

            elif simulator.failure_mode == FailureMode.OOM_ERROR:
                healthcheck_logger.error("OutOfMemoryError")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "error": "OutOfMemoryError",
                        "message": "Container killed by OOMKiller",
                        "memory_limit": "512Mi",
                        "memory_usage": "515Mi",
                        "timestamp": datetime.now().isoformat()
                    }
                )
            elif simulator.failure_mode == FailureMode.RANDOM_CRASH:
                error = RealWorldErrors.random_exception()
                healthcheck_logger.error(error)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "error": error["error"],
                        "message": error["message"],
                        "timestamp": datetime.now().isoformat(),
                        "traceback": error["traceback"]
                    }
                )
        # Healthy response
        current_memory = simulator.get_memory_usage()
        time_until_switch = simulator.get_time_until_next_switch()

        return {
            "status": "healthy",
            "service": "order-service",
            "version": "1.2.5",
            "uptime_seconds": int(time.time() - simulator.start_time),
            "metrics": {
                "total_requests": simulator.request_count,
                "error_count": simulator.error_count,
                "error_rate": round(simulator.error_count / simulator.request_count * 100,
                                    2) if simulator.request_count > 0 else 0,
                "memory_usage_mb": round(current_memory, 2),
                "cpu_percent": psutil.cpu_percent(interval=0.1)
            },
            "dependencies": {
                "database": "connected" if simulator.failure_mode != FailureMode.DATABASE_ERROR else "disconnected",
                "redis": "connected",
                "message_queue": "connected"
            },
            "auto_switch": {
                "enabled": simulator.auto_switch_enabled,
                "current_mode": simulator.failure_mode,
                "switch_count": simulator.switch_count,
                "last_switch": simulator.last_switch_time.isoformat(),
                "next_switch_in_seconds": int(time_until_switch),
                "next_switch_in_minutes": round(time_until_switch / 60, 1)
            },
            "persistence": {
                "config_file": simulator.config_file,
                "config_exists": Path(simulator.config_file).exists()
            },
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        simulator.error_count += 1
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": type(e).__name__,
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
                "traceback": traceback.format_exc()
            }
        )


@app.get("/liveness")
async def liveness_check(response: Response, request: Request):
    """
    Liveness probe - checks if service is alive and should be restarted

    Liveness should fail when:
    - Process is deadlocked or hung
    - Out of memory
    - Critical internal error that requires restart
    - Process is in unrecoverable state
    """
    start_time = time.time()
    simulator.request_count += 1

    # Get client info
    client_host = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        # OOM Error - pod should be killed and restarted
        if simulator.failure_mode == FailureMode.OOM_ERROR:
            simulator.error_count += 1
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

            result = {
                "alive": False,
                "reason": "Out of memory - requires restart",
                "failure_mode": simulator.failure_mode.value,
                "timestamp": datetime.now().isoformat()
            }

            # Log the failure
            healthcheck_logger.error(
                f"LIVENESS CHECK FAILED | "
                f"client={client_host} | "
                f"user_agent={user_agent} | "
                f"status=500 | "
                f"reason=OOM | "
                f"failure_mode={simulator.failure_mode.value} | "
                f"response_time={time.time() - start_time:.3f}s"
            )

            return result

        # Memory leak reaching critical level - pod should be restarted
        if simulator.failure_mode == FailureMode.MEMORY_LEAK:
            current_memory = simulator.get_memory_usage()
            # If memory usage exceeds 90% of typical limit (assuming 512MB limit)
            if current_memory > 460 or simulator.memory_usage_mb > 1024:
                simulator.error_count += 1
                response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

                result = {
                    "alive": False,
                    "reason": "Critical memory usage - requires restart",
                    "failure_mode": simulator.failure_mode.value,
                    "memory_usage_mb": round(current_memory, 2),
                    "simulated_memory_mb": simulator.memory_usage_mb,
                    "timestamp": datetime.now().isoformat()
                }

                # Log the failure
                healthcheck_logger.error(
                    f"LIVENESS CHECK FAILED | "
                    f"client={client_host} | "
                    f"user_agent={user_agent} | "
                    f"status=500 | "
                    f"reason=MEMORY_CRITICAL | "
                    f"memory_mb={round(current_memory, 2)} | "
                    f"simulated_memory_mb={simulator.memory_usage_mb} | "
                    f"failure_mode={simulator.failure_mode.value} | "
                    f"response_time={time.time() - start_time:.3f}s"
                )

                return result

        # Random crash with high failure rate - simulate deadlock/hung process
        if simulator.failure_mode == FailureMode.RANDOM_CRASH:
            if simulator.should_fail() and random.random() < 0.1:  # 10% of failures are critical
                simulator.error_count += 1
                response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

                result = {
                    "alive": False,
                    "reason": "Process in unrecoverable state - requires restart",
                    "failure_mode": simulator.failure_mode.value,
                    "timestamp": datetime.now().isoformat()
                }

                # Log the failure
                healthcheck_logger.error(
                    f"LIVENESS CHECK FAILED | "
                    f"client={client_host} | "
                    f"user_agent={user_agent} | "
                    f"status=500 | "
                    f"reason=UNRECOVERABLE_STATE | "
                    f"failure_mode={simulator.failure_mode.value} | "
                    f"response_time={time.time() - start_time:.3f}s"
                )

                return result

        # Slow response causing deadlock - if delay is too long
        if simulator.failure_mode == FailureMode.SLOW_RESPONSE:
            if simulator.slow_response_delay > 30:  # More than 30s is considered hung
                simulator.error_count += 1
                response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

                result = {
                    "alive": False,
                    "reason": "Process appears hung - requires restart",
                    "failure_mode": simulator.failure_mode.value,
                    "delay_seconds": simulator.slow_response_delay,
                    "timestamp": datetime.now().isoformat()
                }

                # Log the failure
                healthcheck_logger.error(
                    f"LIVENESS CHECK FAILED | "
                    f"client={client_host} | "
                    f"user_agent={user_agent} | "
                    f"status=500 | "
                    f"reason=PROCESS_HUNG | "
                    f"delay_seconds={simulator.slow_response_delay} | "
                    f"failure_mode={simulator.failure_mode.value} | "
                    f"response_time={time.time() - start_time:.3f}s"
                )

                return result

        # Connection pool exhausted for extended period
        if simulator.failure_mode == FailureMode.CONNECTION_POOL_EXHAUSTED:
            # If this has been happening for a while, it might indicate a deadlock
            if simulator.error_count > 50 and (simulator.error_count / simulator.request_count) > 0.8:
                simulator.error_count += 1
                response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

                result = {
                    "alive": False,
                    "reason": "Persistent connection pool exhaustion - requires restart",
                    "failure_mode": simulator.failure_mode.value,
                    "error_rate": round((simulator.error_count / simulator.request_count) * 100, 2),
                    "timestamp": datetime.now().isoformat()
                }

                # Log the failure
                healthcheck_logger.error(
                    f"LIVENESS CHECK FAILED | "
                    f"client={client_host} | "
                    f"user_agent={user_agent} | "
                    f"status=500 | "
                    f"reason=CONNECTION_POOL_EXHAUSTED | "
                    f"error_rate={round((simulator.error_count / simulator.request_count) * 100, 2)}% | "
                    f"failure_mode={simulator.failure_mode.value} | "
                    f"response_time={time.time() - start_time:.3f}s"
                )

                return result

        # Healthy response
        result = {
            "alive": True,
            "failure_mode": simulator.failure_mode.value,
            "uptime_seconds": int(time.time() - simulator.start_time),
            "memory_usage_mb": round(simulator.get_memory_usage(), 2),
            "timestamp": datetime.now().isoformat()
        }

        # Log successful check
        healthcheck_logger.info(
            f"LIVENESS CHECK SUCCESS | "
            f"client={client_host} | "
            f"user_agent={user_agent} | "
            f"status=200 | "
            f"failure_mode={simulator.failure_mode.value} | "
            f"uptime={int(time.time() - simulator.start_time)}s | "
            f"memory_mb={round(simulator.get_memory_usage(), 2)} | "
            f"response_time={time.time() - start_time:.3f}s"
        )

        return result

    except Exception as e:
        # Any unexpected exception in liveness probe is critical
        simulator.error_count += 1
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        result = {
            "alive": False,
            "reason": "Unexpected error in liveness probe",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

        # Log the exception
        healthcheck_logger.exception(
            f"LIVENESS CHECK EXCEPTION | "
            f"client={client_host} | "
            f"user_agent={user_agent} | "
            f"status=500 | "
            f"error={str(e)} | "
            f"response_time={time.time() - start_time:.3f}s"
        )

        return result


@app.get("/readiness")
async def readiness_check(response: Response, request: Request):
    """
    Readiness probe - checks if service can handle traffic

    Readiness should fail when:
    - Dependencies are unavailable (database, cache, etc.)
    - Service is temporarily overloaded
    - Service is starting up or shutting down
    """
    start_time = time.time()
    simulator.request_count += 1

    # Get client info
    client_host = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        # Database connection issues - not ready to serve traffic
        if simulator.failure_mode == FailureMode.DATABASE_ERROR:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            result = {
                "ready": False,
                "reason": "Database connection unavailable",
                "failure_mode": simulator.failure_mode.value,
                "timestamp": datetime.now().isoformat()
            }

            # Log the failure
            healthcheck_logger.warning(
                f"READINESS CHECK FAILED | "
                f"client={client_host} | "
                f"user_agent={user_agent} | "
                f"status=503 | "
                f"reason=DATABASE_UNAVAILABLE | "
                f"failure_mode={simulator.failure_mode.value} | "
                f"response_time={time.time() - start_time:.3f}s"
            )

            return result

        # Connection pool exhausted - not ready for more traffic
        if simulator.failure_mode == FailureMode.CONNECTION_POOL_EXHAUSTED:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

            result = {
                "ready": False,
                "reason": "Connection pool exhausted",
                "failure_mode": simulator.failure_mode.value,
                "timestamp": datetime.now().isoformat()
            }

            # Log the failure
            healthcheck_logger.warning(
                f"READINESS CHECK FAILED | "
                f"client={client_host} | "
                f"user_agent={user_agent} | "
                f"status=503 | "
                f"reason=CONNECTION_POOL_EXHAUSTED | "
                f"failure_mode={simulator.failure_mode.value} | "
                f"response_time={time.time() - start_time:.3f}s"
            )

            return result

        # Dependency timeout - external services unavailable
        if simulator.failure_mode == FailureMode.DEPENDENCY_TIMEOUT:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

            result = {
                "ready": False,
                "reason": "External dependencies timeout",
                "failure_mode": simulator.failure_mode.value,
                "timestamp": datetime.now().isoformat()
            }

            # Log the failure
            healthcheck_logger.warning(
                f"READINESS CHECK FAILED | "
                f"client={client_host} | "
                f"user_agent={user_agent} | "
                f"status=503 | "
                f"reason=DEPENDENCY_TIMEOUT | "
                f"failure_mode={simulator.failure_mode.value} | "
                f"response_time={time.time() - start_time:.3f}s"
            )

            return result

        # Memory leak approaching critical level - stop accepting new traffic
        if simulator.failure_mode == FailureMode.MEMORY_LEAK:
            current_memory = simulator.get_memory_usage()
            if current_memory > 400 or simulator.memory_usage_mb > 900:
                response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

                result = {
                    "ready": False,
                    "reason": "High memory usage - not accepting new traffic",
                    "failure_mode": simulator.failure_mode.value,
                    "memory_usage_mb": round(current_memory, 2),
                    "timestamp": datetime.now().isoformat()
                }

                # Log the failure
                healthcheck_logger.warning(
                    f"READINESS CHECK FAILED | "
                    f"client={client_host} | "
                    f"user_agent={user_agent} | "
                    f"status=503 | "
                    f"reason=HIGH_MEMORY | "
                    f"memory_mb={round(current_memory, 2)} | "
                    f"failure_mode={simulator.failure_mode.value} | "
                    f"response_time={time.time() - start_time:.3f}s"
                )

                return result

        # Slow response - service is overloaded
        if simulator.failure_mode == FailureMode.SLOW_RESPONSE:
            if simulator.slow_response_delay > 10:
                response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

                result = {
                    "ready": False,
                    "reason": "Service overloaded - slow response times",
                    "failure_mode": simulator.failure_mode.value,
                    "delay_seconds": simulator.slow_response_delay,
                    "timestamp": datetime.now().isoformat()
                }

                # Log the failure
                healthcheck_logger.warning(
                    f"READINESS CHECK FAILED | "
                    f"client={client_host} | "
                    f"user_agent={user_agent} | "
                    f"status=503 | "
                    f"reason=SERVICE_OVERLOADED | "
                    f"delay_seconds={simulator.slow_response_delay} | "
                    f"failure_mode={simulator.failure_mode.value} | "
                    f"response_time={time.time() - start_time:.3f}s"
                )

                return result

        # OOM Error - definitely not ready
        if simulator.failure_mode == FailureMode.OOM_ERROR:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

            result = {
                "ready": False,
                "reason": "Out of memory",
                "failure_mode": simulator.failure_mode.value,
                "timestamp": datetime.now().isoformat()
            }

            # Log the failure
            healthcheck_logger.warning(
                f"READINESS CHECK FAILED | "
                f"client={client_host} | "
                f"user_agent={user_agent} | "
                f"status=503 | "
                f"reason=OOM | "
                f"failure_mode={simulator.failure_mode.value} | "
                f"response_time={time.time() - start_time:.3f}s"
            )

            return result

        # Random crash with high error rate - temporarily not ready
        if simulator.failure_mode == FailureMode.RANDOM_CRASH:
            if simulator.request_count > 10:
                error_rate = simulator.error_count / simulator.request_count
                if error_rate > 0.5:  # More than 50% errors
                    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

                    result = {
                        "ready": False,
                        "reason": "High error rate - temporarily not ready",
                        "failure_mode": simulator.failure_mode.value,
                        "error_rate": round(error_rate * 100, 2),
                        "timestamp": datetime.now().isoformat()
                    }

                    # Log the failure
                    healthcheck_logger.warning(
                        f"READINESS CHECK FAILED | "
                        f"client={client_host} | "
                        f"user_agent={user_agent} | "
                        f"status=503 | "
                        f"reason=HIGH_ERROR_RATE | "
                        f"error_rate={round(error_rate * 100, 2)}% | "
                        f"failure_mode={simulator.failure_mode.value} | "
                        f"response_time={time.time() - start_time:.3f}s"
                    )

                    return result

        # Service is ready
        result = {
            "ready": True,
            "service": "order-service",
            "failure_mode": simulator.failure_mode.value,
            "timestamp": datetime.now().isoformat()
        }

        # Log successful check
        healthcheck_logger.info(
            f"READINESS CHECK SUCCESS | "
            f"client={client_host} | "
            f"user_agent={user_agent} | "
            f"status=200 | "
            f"failure_mode={simulator.failure_mode.value} | "
            f"response_time={time.time() - start_time:.3f}s"
        )

        return result

    except Exception as e:
        # Unexpected errors make service not ready
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        result = {
            "ready": False,
            "reason": "Unexpected error in readiness probe",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

        # Log the exception
        healthcheck_logger.exception(
            f"READINESS CHECK EXCEPTION | "
            f"client={client_host} | "
            f"user_agent={user_agent} | "
            f"status=503 | "
            f"error={str(e)} | "
            f"response_time={time.time() - start_time:.3f}s"
        )

        return result


@app.get("/metrics")
async def metrics():
    """Prometheus-style metrics endpoint"""
    uptime = time.time() - simulator.start_time
    error_rate = (simulator.error_count / simulator.request_count * 100) if simulator.request_count > 0 else 0

    return {
        "http_requests_total": simulator.request_count,
        "http_requests_errors_total": simulator.error_count,
        "http_request_error_rate_percent": round(error_rate, 2),
        "process_uptime_seconds": int(uptime),
        "process_memory_bytes": simulator.get_memory_usage() * 1024 * 1024,
        "process_cpu_percent": psutil.cpu_percent(interval=0.1)
    }


# Control endpoints
@app.post("/control/failure-mode/{mode}")
async def set_failure_mode(mode: FailureMode):
    """Set failure mode to simulate different error scenarios"""
    old_mode = simulator.failure_mode
    simulator.failure_mode = mode
    simulator.memory_usage_mb = 100  # Reset memory
    simulator.last_switch_time = datetime.now()  # Reset timer

    # Save configuration
    simulator.save_config()

    return {
        "message": f"Failure mode manually set to: {mode}",
        "previous_mode": old_mode,
        "current_mode": simulator.failure_mode,
        "description": {
            "healthy": "Normal operation",
            "database_error": "Simulates database connection failures",
            "memory_leak": "Simulates memory leak and OOM",
            "dependency_timeout": "Simulates external API timeouts",
            "random_crash": "Random exceptions and crashes",
            "slow_response": "Slow response times",
            "oom_error": "Out of memory error",
            "connection_pool_exhausted": "Database connection pool exhausted"
        }.get(mode, "Unknown mode"),
        "auto_switch": {
            "enabled": simulator.auto_switch_enabled,
            "timer_reset": True
        },
        "saved": True,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/control/failure-rate/{rate}")
async def set_failure_rate(rate: float):
    """Set failure rate for random_crash mode (0.0 to 1.0)"""
    if 0 <= rate <= 1:
        simulator.failure_rate = rate
        simulator.save_config()
        return {
            "message": f"Failure rate set to {rate * 100}%",
            "failure_rate": simulator.failure_rate,
            "saved": True,
            "timestamp": datetime.now().isoformat()
        }
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Rate must be between 0 and 1"}
    )


@app.post("/control/slow-response-delay/{seconds}")
async def set_slow_response_delay(seconds: int):
    """Set delay for slow_response mode"""
    if seconds > 0:
        simulator.slow_response_delay = seconds
        simulator.save_config()
        return {
            "message": f"Slow response delay set to {seconds} seconds",
            "delay": simulator.slow_response_delay,
            "saved": True,
            "timestamp": datetime.now().isoformat()
        }
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Delay must be greater than 0"}
    )


@app.post("/control/auto-switch/enable")
async def enable_auto_switch():
    """Enable automatic mode switching"""
    if not simulator.auto_switch_enabled:
        simulator.auto_switch_enabled = True
        simulator.start_auto_switch()
        simulator.save_config()
        return {
            "message": "Auto-switch enabled",
            "enabled": True,
            "interval_hours": simulator.switch_interval_hours,
            "saved": True,
            "timestamp": datetime.now().isoformat()
        }
    return {
        "message": "Auto-switch already enabled",
        "enabled": True,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/control/auto-switch/disable")
async def disable_auto_switch():
    """Disable automatic mode switching"""
    simulator.auto_switch_enabled = False
    simulator.save_config()
    return {
        "message": "Auto-switch disabled",
        "enabled": False,
        "current_mode_locked": simulator.failure_mode,
        "saved": True,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/control/auto-switch/interval/{hours}")
async def set_auto_switch_interval(hours: float):
    """Set auto-switch interval in hours"""
    if hours > 0:
        simulator.switch_interval_hours = hours
        simulator.last_switch_time = datetime.now()  # Reset timer
        simulator.save_config()
        return {
            "message": f"Auto-switch interval set to {hours} hours",
            "interval_hours": simulator.switch_interval_hours,
            "timer_reset": True,
            "next_switch_in_seconds": int(simulator.get_time_until_next_switch()),
            "saved": True,
            "timestamp": datetime.now().isoformat()
        }
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Interval must be greater than 0"}
    )


@app.post("/control/auto-switch/trigger")
async def trigger_auto_switch():
    """Manually trigger an auto-switch to random mode"""
    old_mode, new_mode = simulator.switch_to_random_mode()
    return {
        "message": "Auto-switch triggered manually",
        "previous_mode": old_mode,
        "new_mode": new_mode,
        "switch_count": simulator.switch_count,
        "saved": True,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/control/status")
async def get_control_status():
    """Get current simulator configuration"""
    time_until_switch = simulator.get_time_until_next_switch()

    return {
        "current_mode": simulator.failure_mode,
        "failure_rate": simulator.failure_rate,
        "slow_response_delay": simulator.slow_response_delay,
        "auto_switch": {
            "enabled": simulator.auto_switch_enabled,
            "interval_hours": simulator.switch_interval_hours,
            "switch_count": simulator.switch_count,
            "last_switch": simulator.last_switch_time.isoformat(),
            "next_switch_in_seconds": int(time_until_switch),
            "next_switch_in_minutes": round(time_until_switch / 60, 1),
            "next_switch_in_hours": round(time_until_switch / 3600, 2)
        },
        "statistics": {
            "uptime_seconds": int(time.time() - simulator.start_time),
            "total_requests": simulator.request_count,
            "error_count": simulator.error_count,
            "error_rate_percent": round(
                (simulator.error_count / simulator.request_count * 100) if simulator.request_count > 0 else 0,
                2
            )
        },
        "system": {
            "memory_usage_mb": round(simulator.get_memory_usage(), 2),
            "cpu_percent": psutil.cpu_percent(interval=0.1)
        },
        "persistence": {
            "config_file": simulator.config_file,
            "config_exists": Path(simulator.config_file).exists(),
            "config_readable": os.access(simulator.config_file, os.R_OK) if Path(
                simulator.config_file).exists() else False,
            "config_writable": os.access(simulator.config_dir, os.W_OK)
        },
        "timestamp": datetime.now().isoformat()
    }


@app.post("/control/save")
async def manual_save():
    """Manually save current configuration"""
    success = simulator.save_config()
    return {
        "message": "Configuration saved" if success else "Failed to save configuration",
        "success": success,
        "config_file": simulator.config_file,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/control/reload")
async def reload_config():
    """Reload configuration from file"""
    success = simulator.load_config()
    return {
        "message": "Configuration reloaded" if success else "Failed to reload configuration",
        "success": success,
        "config_file": simulator.config_file,
        "current_mode": simulator.failure_mode,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/control/reset")
async def reset_simulator():
    """Reset simulator to default state (random_crash mode)"""
    simulator.failure_mode = FailureMode.RANDOM_CRASH
    simulator.error_count = 0
    simulator.request_count = 0
    simulator.memory_usage_mb = 100
    simulator.start_time = time.time()
    simulator.last_switch_time = datetime.now()
    simulator.switch_count = 0

    simulator.save_config()

    return {
        "message": "Simulator reset to default state (random_crash mode)",
        "current_mode": simulator.failure_mode,
        "auto_switch_enabled": simulator.auto_switch_enabled,
        "saved": True,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/")
async def root():
    """API documentation"""
    time_until_switch = simulator.get_time_until_next_switch()

    return {
        "service": "E-Commerce Order Service",
        "version": "1.2.5",
        "description": "Microservice for order processing with failure simulation capabilities",
        "endpoints": {
            "health_checks": {
                "/health": "Main health check endpoint",
                "/readiness": "Readiness probe",
                "/liveness": "Liveness probe",
                "/metrics": "Prometheus metrics"
            },
            "control": {
                "GET /control/status": "Get current configuration",
                "POST /control/failure-mode/{mode}": "Set failure mode",
                "POST /control/failure-rate/{rate}": "Set failure rate (0.0-1.0)",
                "POST /control/slow-response-delay/{seconds}": "Set response delay",
                "POST /control/auto-switch/enable": "Enable auto-switch",
                "POST /control/auto-switch/disable": "Disable auto-switch",
                "POST /control/auto-switch/interval/{hours}": "Set switch interval",
                "POST /control/auto-switch/trigger": "Manually trigger switch",
                "POST /control/save": "Manually save configuration",
                "POST /control/reload": "Reload configuration from file",
                "POST /control/reset": "Reset to default state"
            }
        },
        "failure_modes": [mode.value for mode in FailureMode],
        "current_status": {
            "mode": simulator.failure_mode,
            "uptime": int(time.time() - simulator.start_time),
            "requests": simulator.request_count,
            "errors": simulator.error_count,
            "auto_switch": {
                "enabled": simulator.auto_switch_enabled,
                "interval_hours": simulator.switch_interval_hours,
                "switch_count": simulator.switch_count,
                "next_switch_in_minutes": round(time_until_switch / 60, 1)
            },
            "persistence": {
                "config_file": simulator.config_file,
                "config_exists": Path(simulator.config_file).exists()
            }
        }
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=2509,
        log_level="info",
        access_log=True
    )