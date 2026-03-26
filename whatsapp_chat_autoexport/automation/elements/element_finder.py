"""
Multi-strategy element finder for UI automation.

Provides robust element finding with:
- Multiple fallback strategies
- Automatic caching of successful strategies
- Configurable timeouts and retries
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Callable
from datetime import datetime
import time

from ...core.result import Result, Ok, Err
from ...core.errors import ElementNotFoundError, ErrorCategory
from ...config.selectors import SelectorDefinition, ElementSelectors, SelectorStrategy
from ...config.timeouts import get_timeout


@dataclass
class FindResult:
    """Result of an element find operation."""

    element: Any  # The found Appium element
    strategy: SelectorDefinition  # Which strategy succeeded
    attempts: int  # How many strategies were tried
    duration_seconds: float  # Time taken to find
    from_cache: bool = False  # Whether a cached strategy was used

    @property
    def locator(self) -> tuple[str, str]:
        """Get the locator tuple that found this element."""
        return self.strategy.to_appium_locator()


class ElementFinder:
    """
    Multi-strategy element finder with caching support.

    Tries multiple selector strategies in priority order until one
    succeeds, caching successful strategies for future use.
    """

    def __init__(
        self,
        driver: Any,  # Appium WebDriver
        cache: Optional["ElementCache"] = None,
        logger: Optional[Any] = None,
    ):
        """
        Initialize the element finder.

        Args:
            driver: Appium WebDriver instance
            cache: Optional element cache for strategy persistence
            logger: Optional logger for debug output
        """
        self.driver = driver
        self.cache = cache
        self.logger = logger

    def find(
        self,
        selectors: ElementSelectors,
        timeout: Optional[float] = None,
        wait_visible: bool = True,
        context: Optional[str] = None,
    ) -> Result[FindResult, ElementNotFoundError]:
        """
        Find an element using multiple strategies.

        Tries strategies in priority order, caching successful ones.

        Args:
            selectors: ElementSelectors with strategies to try
            timeout: Override timeout (uses strategy timeout if None)
            wait_visible: Whether to wait for element visibility
            context: Optional context string for logging/caching

        Returns:
            Result containing FindResult or ElementNotFoundError
        """
        start_time = time.time()
        strategies_tried = []
        context_key = context or selectors.name

        # Check cache first
        if self.cache:
            cached_strategy = self.cache.get(context_key)
            if cached_strategy:
                self._log_debug(f"Trying cached strategy for {context_key}")
                result = self._try_strategy(
                    cached_strategy, timeout, wait_visible
                )
                if result is not None:
                    duration = time.time() - start_time
                    return Ok(
                        FindResult(
                            element=result,
                            strategy=cached_strategy,
                            attempts=1,
                            duration_seconds=duration,
                            from_cache=True,
                        )
                    )
                else:
                    # Cache miss - invalidate and try all strategies
                    self.cache.invalidate(context_key)
                    self._log_debug(f"Cache miss for {context_key}, trying all")

        # Try strategies in priority order
        sorted_strategies = selectors.get_sorted_strategies()
        for strategy in sorted_strategies:
            strategies_tried.append(strategy.strategy.value)
            self._log_debug(
                f"Trying {strategy.strategy.value}: {strategy.value}"
            )

            strategy_timeout = timeout or strategy.timeout
            result = self._try_strategy(strategy, strategy_timeout, wait_visible)

            if result is not None:
                duration = time.time() - start_time
                self._log_debug(
                    f"Found element with {strategy.strategy.value} in {duration:.2f}s"
                )

                # Cache successful strategy
                if self.cache:
                    self.cache.set(context_key, strategy)

                return Ok(
                    FindResult(
                        element=result,
                        strategy=strategy,
                        attempts=len(strategies_tried),
                        duration_seconds=duration,
                        from_cache=False,
                    )
                )

        # All strategies failed
        duration = time.time() - start_time
        error = ElementNotFoundError(
            message=f"Could not find element: {selectors.name}",
            element_name=selectors.name,
            strategies_tried=strategies_tried,
            screen_context=context,
        )
        return Err(error)

    def find_all(
        self,
        selectors: ElementSelectors,
        timeout: Optional[float] = None,
    ) -> Result[List[Any], ElementNotFoundError]:
        """
        Find all matching elements.

        Args:
            selectors: ElementSelectors with strategies to try
            timeout: Override timeout

        Returns:
            Result containing list of elements or error
        """
        strategies_tried = []

        for strategy in selectors.get_sorted_strategies():
            strategies_tried.append(strategy.strategy.value)
            strategy_timeout = timeout or strategy.timeout

            try:
                locator_type, locator_value = strategy.to_appium_locator()
                elements = self._find_elements_with_timeout(
                    locator_type, locator_value, strategy_timeout
                )
                if elements:
                    return Ok(elements)
            except Exception as e:
                self._log_debug(f"Strategy {strategy.strategy.value} failed: {e}")
                continue

        error = ElementNotFoundError(
            message=f"Could not find any elements: {selectors.name}",
            element_name=selectors.name,
            strategies_tried=strategies_tried,
        )
        return Err(error)

    def is_present(
        self,
        selectors: ElementSelectors,
        timeout: float = 1.0,
    ) -> bool:
        """
        Check if an element is present without raising errors.

        Args:
            selectors: ElementSelectors with strategies to try
            timeout: How long to wait

        Returns:
            True if element found, False otherwise
        """
        for strategy in selectors.get_sorted_strategies():
            try:
                locator_type, locator_value = strategy.to_appium_locator()
                elements = self._find_elements_with_timeout(
                    locator_type, locator_value, timeout
                )
                if elements:
                    return True
            except Exception:
                continue
        return False

    def wait_for(
        self,
        selectors: ElementSelectors,
        condition: str = "visible",
        timeout: Optional[float] = None,
    ) -> Result[FindResult, ElementNotFoundError]:
        """
        Wait for an element with a specific condition.

        Args:
            selectors: ElementSelectors with strategies to try
            condition: One of "visible", "clickable", "present"
            timeout: Maximum wait time

        Returns:
            Result containing FindResult or error
        """
        wait_visible = condition in ("visible", "clickable")
        return self.find(selectors, timeout=timeout, wait_visible=wait_visible)

    def _try_strategy(
        self,
        strategy: SelectorDefinition,
        timeout: float,
        wait_visible: bool,
    ) -> Optional[Any]:
        """
        Try a single strategy to find an element.

        Returns the element if found, None otherwise.
        """
        try:
            locator_type, locator_value = strategy.to_appium_locator()

            if wait_visible:
                return self._find_visible_element(
                    locator_type, locator_value, timeout
                )
            else:
                return self._find_element(locator_type, locator_value, timeout)
        except Exception as e:
            self._log_debug(f"Strategy failed: {e}")
            return None

    def _find_element(
        self,
        locator_type: str,
        locator_value: str,
        timeout: float,
    ) -> Optional[Any]:
        """Find a single element with timeout."""
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.by import By

            by_type = self._get_by_type(locator_type)
            wait = WebDriverWait(self.driver, timeout)
            return wait.until(EC.presence_of_element_located((by_type, locator_value)))
        except Exception:
            return None

    def _find_visible_element(
        self,
        locator_type: str,
        locator_value: str,
        timeout: float,
    ) -> Optional[Any]:
        """Find a visible element with timeout."""
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.by import By

            by_type = self._get_by_type(locator_type)
            wait = WebDriverWait(self.driver, timeout)
            return wait.until(
                EC.visibility_of_element_located((by_type, locator_value))
            )
        except Exception:
            return None

    def _find_elements_with_timeout(
        self,
        locator_type: str,
        locator_value: str,
        timeout: float,
    ) -> List[Any]:
        """Find all matching elements with timeout."""
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            by_type = self._get_by_type(locator_type)

            def has_elements(driver):
                elements = driver.find_elements(by_type, locator_value)
                return elements if elements else False

            wait = WebDriverWait(self.driver, timeout)
            return wait.until(has_elements)
        except Exception:
            return []

    def _get_by_type(self, locator_type: str) -> str:
        """Convert locator type string to Selenium By constant."""
        from selenium.webdriver.common.by import By

        mapping = {
            "id": By.ID,
            "xpath": By.XPATH,
            "class name": By.CLASS_NAME,
            "accessibility id": By.XPATH,  # Appium handles this differently
            "css": By.CSS_SELECTOR,
            "name": By.NAME,
            "tag name": By.TAG_NAME,
        }
        return mapping.get(locator_type.lower(), By.ID)

    def _log_debug(self, message: str) -> None:
        """Log a debug message if logger is available."""
        if self.logger:
            if hasattr(self.logger, "debug_msg"):
                self.logger.debug_msg(message)
            elif hasattr(self.logger, "debug"):
                self.logger.debug(message)
