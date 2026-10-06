import time
import threading

class CircuitBreakerOpenException(Exception):
    pass

class CircuitBreaker:
    """
    Patrón Circuit Breaker para aislar fallos en conexiones remotas (SSH, SCP, BDD)
    Estados: CLOSED (Normal), OPEN (Bloqueado por fallos reiterados), HALF_OPEN (Prueba)
    """
    def __init__(self, failure_threshold: int = 3, recovery_time_seconds: float = 20.0):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time_seconds
        self.state = "CLOSED"
        self.failure_count = 0
        self.last_failure_time = 0
        self.lock = threading.Lock()

    def can_execute(self) -> bool:
        with self.lock:
            now = time.time()
            if self.state == "OPEN":
                if now - self.last_failure_time > self.recovery_time:
                    self.state = "HALF_OPEN"
                    return True
                return False
            return True

    def record_success(self):
        with self.lock:
            self.failure_count = 0
            self.state = "CLOSED"

    def record_failure(self):
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"

    def get_status(self) -> dict:
        with self.lock:
            return {
                "state": self.state,
                "failure_count": self.failure_count,
                "threshold": self.failure_threshold,
                "last_failure_seconds_ago": round(time.time() - self.last_failure_time, 1) if self.last_failure_time > 0 else None
            }

class CircuitBreakerRegistry:
    def __init__(self):
        self.breakers = {}
        self.lock = threading.Lock()

    def get_breaker(self, target_key: str) -> CircuitBreaker:
        with self.lock:
            if target_key not in self.breakers:
                self.breakers[target_key] = CircuitBreaker()
            return self.breakers[target_key]

    def get_all_status(self) -> dict:
        with self.lock:
            return {k: v.get_status() for k, v in self.breakers.items()}

circuit_registry = CircuitBreakerRegistry()
